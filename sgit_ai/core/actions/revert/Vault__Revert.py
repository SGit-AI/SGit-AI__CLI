import json
import os

from osbot_utils.type_safe.Type_Safe               import Type_Safe
from sgit_ai.crypto.PKI__Crypto                    import PKI__Crypto
from sgit_ai.crypto.Vault__Crypto                  import Vault__Crypto
from sgit_ai.crypto.Vault__Key_Manager             import Vault__Key_Manager
from sgit_ai.storage.Vault__Commit                 import Vault__Commit
from sgit_ai.storage.Vault__Object_Store           import Vault__Object_Store
from sgit_ai.storage.Vault__Ref_Manager            import Vault__Ref_Manager
from sgit_ai.storage.Vault__Branch_Manager            import Vault__Branch_Manager
from sgit_ai.sync.Vault__Components                import Vault__Components
from sgit_ai.sync.Vault__Ignore                    import Vault__Ignore
from sgit_ai.storage.Vault__Storage                   import Vault__Storage, SG_VAULT_DIR
from sgit_ai.storage.Vault__Sub_Tree                  import Vault__Sub_Tree


class Vault__Revert(Type_Safe):
    crypto : Vault__Crypto

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def revert_to_head(self, directory: str, files: list = None) -> dict:
        """Revert working copy files to HEAD.

        If *files* is None or empty, revert all files.
        Returns dict with restored/deleted lists and the head commit_id.
        """
        c         = self._init_components(directory)
        commit_id = self._resolve_head_commit_id(c, directory)
        if not commit_id:
            return dict(restored=[], deleted=[], commit_id=None)
        return self._revert_to_commit(directory, c, commit_id, files)

    def revert_all_to_head(self, directory: str) -> dict:
        """Convenience: revert all files to HEAD (no file filter)."""
        return self.revert_to_head(directory, files=None)

    def revert_to_commit(self, directory: str, commit_id: str, files: list = None) -> dict:
        """Revert working copy to a specific commit."""
        c = self._init_components(directory)
        return self._revert_to_commit(directory, c, commit_id, files)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _revert_to_commit(self, directory: str, c: Vault__Components,
                          commit_id: str, files: list) -> dict:
        committed = self._flatten_commit(c, commit_id)

        # Determine which paths to process
        if files:
            target_paths = set(files)
        else:
            # All paths: union of working copy + committed
            working = self._scan_working_files(directory)
            target_paths = set(committed.keys()) | set(working.keys())

        restored = []
        deleted  = []

        for path in sorted(target_paths):
            full_path = os.path.join(directory, path)
            if path in committed:
                # Write the committed content to working copy
                content  = committed[path]
                dir_part = os.path.dirname(full_path)
                if dir_part:
                    os.makedirs(dir_part, exist_ok=True)
                with open(full_path, 'wb') as fh:
                    fh.write(content)
                restored.append(path)
            else:
                # File not in committed state — delete from working copy
                if os.path.isfile(full_path):
                    os.remove(full_path)
                    deleted.append(path)
                    self._remove_empty_parent_dirs(directory, full_path)

        return dict(restored=restored, deleted=deleted, commit_id=commit_id)

    def _resolve_head_commit_id(self, c: Vault__Components, directory: str) -> str:
        storage        = c.storage
        branch_manager = c.branch_manager
        ref_manager    = c.ref_manager
        read_key       = c.read_key

        local_config = self._read_local_config(directory, storage)
        branch_id    = str(local_config.my_branch_id)

        index_id = c.branch_index_file_id
        if not index_id:
            return None
        branch_index = branch_manager.load_branch_index(directory, index_id, read_key)
        branch_meta  = branch_manager.get_branch_by_id(branch_index, branch_id)
        if not branch_meta:
            return None

        ref_id    = str(branch_meta.head_ref_id)
        commit_id = ref_manager.read_ref(ref_id, read_key)
        return commit_id

    def _flatten_commit(self, c: Vault__Components, commit_id: str) -> dict:
        """Return flat {path: bytes} for a given commit_id."""
        pki       = c.pki
        obj_store = c.obj_store
        ref_manager = c.ref_manager
        read_key    = c.read_key

        vault_commit = Vault__Commit(crypto=self.crypto, pki=pki,
                                     object_store=obj_store, ref_manager=ref_manager)
        commit_obj = vault_commit.load_commit(commit_id, read_key)
        sub_tree   = Vault__Sub_Tree(crypto=self.crypto, obj_store=obj_store)
        flat_map   = sub_tree.flatten(str(commit_obj.tree_id), read_key)

        result = {}
        for path, entry in flat_map.items():
            blob_id = entry.get('blob_id')
            if not blob_id:
                continue
            ciphertext = obj_store.load(blob_id)
            plaintext  = self.crypto.decrypt(read_key, ciphertext)
            result[path] = plaintext
        return result

    def _scan_working_files(self, directory: str) -> dict:
        """Walk working directory, return {path: bytes}."""
        ignore = Vault__Ignore().load_gitignore(directory)
        result = {}
        for root, dirs, files in os.walk(directory):
            rel_root = os.path.relpath(root, directory).replace(os.sep, '/')
            if rel_root == '.':
                rel_root = ''
            dirs[:] = [d for d in dirs
                       if not ignore.should_ignore_dir(f'{rel_root}/{d}' if rel_root else d)]
            for filename in files:
                rel_path = f'{rel_root}/{filename}' if rel_root else filename
                if ignore.should_ignore_file(rel_path):
                    continue
                full_path = os.path.join(root, filename)
                with open(full_path, 'rb') as fh:
                    result[rel_path] = fh.read()
        return result

    def _init_components(self, directory: str) -> Vault__Components:
        vault_key_path = os.path.join(directory, SG_VAULT_DIR, 'local', 'vault_key')
        with open(vault_key_path, 'r') as fh:
            vault_key = fh.read().strip()

        keys    = self.crypto.derive_keys_from_vault_key(vault_key)
        sg_dir  = os.path.join(directory, SG_VAULT_DIR)
        storage = Vault__Storage()
        pki     = PKI__Crypto()

        obj_store      = Vault__Object_Store(vault_path=sg_dir, crypto=self.crypto)
        ref_manager    = Vault__Ref_Manager(vault_path=sg_dir,  crypto=self.crypto)
        key_manager    = Vault__Key_Manager(vault_path=sg_dir,  crypto=self.crypto, pki=pki)
        branch_manager = Vault__Branch_Manager(vault_path    = sg_dir,
                                               crypto        = self.crypto,
                                               key_manager   = key_manager,
                                               ref_manager   = ref_manager,
                                               storage       = storage)
        return Vault__Components(
            vault_key            = vault_key,
            vault_id             = keys['vault_id'],
            read_key             = keys['read_key_bytes'],
            write_key            = keys['write_key'],
            ref_file_id          = keys['ref_file_id'],
            branch_index_file_id = keys['branch_index_file_id'],
            sg_dir               = sg_dir,
            storage              = storage,
            pki                  = pki,
            obj_store            = obj_store,
            ref_manager          = ref_manager,
            key_manager          = key_manager,
            branch_manager       = branch_manager,
        )

    def _read_local_config(self, directory: str, storage: Vault__Storage):
        from sgit_ai.schemas.Schema__Local_Config import Schema__Local_Config
        config_path = storage.local_config_path(directory)
        with open(config_path, 'r') as fh:
            data = json.load(fh)
        return Schema__Local_Config.from_json(data)

    def _remove_empty_parent_dirs(self, root_dir: str, removed_file_path: str):
        """Walk up from removed file's parent, removing empty dirs up to root_dir."""
        parent = os.path.dirname(removed_file_path)
        while parent and parent != root_dir:
            if os.path.isdir(parent) and not os.listdir(parent):
                os.rmdir(parent)
                parent = os.path.dirname(parent)
            else:
                break
