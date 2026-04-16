import difflib
import hashlib
import json
import os

from osbot_utils.type_safe.Type_Safe               import Type_Safe
from sgit_ai.crypto.Vault__Crypto                  import Vault__Crypto
from sgit_ai.crypto.PKI__Crypto                    import PKI__Crypto
from sgit_ai.objects.Vault__Object_Store           import Vault__Object_Store
from sgit_ai.objects.Vault__Ref_Manager            import Vault__Ref_Manager
from sgit_ai.objects.Vault__Commit                 import Vault__Commit
from sgit_ai.safe_types.Safe_Str__Diff_Mode        import Safe_Str__Diff_Mode
from sgit_ai.schemas.Schema__Diff_File             import Schema__Diff_File
from sgit_ai.schemas.Schema__Diff_Result           import Schema__Diff_Result
from sgit_ai.sync.Vault__Branch_Manager            import Vault__Branch_Manager
from sgit_ai.sync.Vault__Components                import Vault__Components
from sgit_ai.sync.Vault__Ignore                    import Vault__Ignore
from sgit_ai.crypto.Vault__Key_Manager             import Vault__Key_Manager
from sgit_ai.sync.Vault__Storage                   import Vault__Storage, SG_VAULT_DIR
from sgit_ai.sync.Vault__Sub_Tree                  import Vault__Sub_Tree

BINARY_CHECK_BYTES = 8192


class Vault__Diff(Type_Safe):
    crypto : Vault__Crypto

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def diff_vs_head(self, directory: str) -> Schema__Diff_Result:
        """Compare working copy vs last local commit (HEAD)."""
        c = self._init_components(directory)
        committed_files = self._read_head_files(c)
        working_files   = self._scan_working_files(directory, c)
        diff_files      = self.diff_files(working_files, committed_files)
        return self._build_result(directory, 'head', '', diff_files)

    def diff_vs_remote(self, directory: str) -> Schema__Diff_Result:
        """Compare working copy vs named branch HEAD."""
        c = self._init_components(directory)
        committed_files = self._read_named_branch_files(c, directory)
        working_files   = self._scan_working_files(directory, c)
        diff_files      = self.diff_files(working_files, committed_files)
        return self._build_result(directory, 'remote', '', diff_files)

    def diff_vs_commit(self, directory: str, commit_id: str) -> Schema__Diff_Result:
        """Compare working copy vs a specific commit."""
        c = self._init_components(directory)
        committed_files = self._read_commit_files(c, commit_id)
        working_files   = self._scan_working_files(directory, c)
        diff_files      = self.diff_files(working_files, committed_files)
        return self._build_result(directory, 'commit', commit_id, diff_files)

    def diff_commits(self, directory: str, commit_a: str, commit_b: str) -> Schema__Diff_Result:
        """Compare two specific commits directly (commit_a = before, commit_b = after)."""
        c        = self._init_components(directory)
        files_a  = self._read_commit_files(c, commit_a)
        files_b  = self._read_commit_files(c, commit_b)
        diff_files = self.diff_files(files_a, files_b)
        result = self._build_result(directory, 'commits', commit_a, diff_files)
        result.commit_id_b = commit_b
        return result

    def show_commit(self, directory: str, commit_id: str) -> tuple:
        """Return (commit_info dict, Schema__Diff_Result) for a specific commit vs its parent.

        commit_info keys: commit_id, timestamp_ms, message, parent_id, branch_id
        If the commit has no parent, diffs against an empty tree.
        """
        import datetime
        c            = self._init_components(directory)
        pki          = c.pki
        obj_store    = c.obj_store
        ref_manager  = c.ref_manager
        read_key     = c.read_key

        vault_commit = Vault__Commit(crypto=self.crypto, pki=pki,
                                     object_store=obj_store, ref_manager=ref_manager)
        commit_obj   = vault_commit.load_commit(commit_id, read_key)

        # Decrypt commit message
        message = ''
        if commit_obj.message_enc:
            try:
                message = self.crypto.decrypt_metadata(read_key, str(commit_obj.message_enc))
            except Exception:
                message = '(encrypted — could not decrypt)'

        ts_ms     = int(commit_obj.timestamp_ms) if commit_obj.timestamp_ms else 0
        ts_str    = datetime.datetime.fromtimestamp(ts_ms / 1000,
                                                     tz=datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
        parent_id = str(commit_obj.parents[0]) if commit_obj.parents else None

        commit_info = dict(commit_id  = commit_id,
                           timestamp  = ts_str,
                           timestamp_ms = ts_ms,
                           message    = message,
                           parent_id  = parent_id,
                           branch_id  = str(commit_obj.branch_id) if commit_obj.branch_id else '')

        files_before = self._read_commit_files(c, parent_id) if parent_id else {}
        files_after  = self._read_commit_files(c, commit_id)
        diff_files   = self.diff_files(files_before, files_after)
        result       = self._build_result(directory, 'commits', parent_id or '', diff_files)
        result.commit_id_b = commit_id

        return commit_info, result

    def diff_files(self, working_files: dict, committed_files: dict) -> list:
        """Core diff logic: compare two {path: bytes} dicts.

        Returns list[Schema__Diff_File].
        """
        all_paths = set(working_files.keys()) | set(committed_files.keys())
        result    = []
        for path in sorted(all_paths):
            before = committed_files.get(path)
            after  = working_files.get(path)
            result.append(self.diff_single_file(path, before, after))
        return result

    def diff_single_file(self, path: str, before, after) -> Schema__Diff_File:
        """Diff one file. before/after are bytes or None."""
        if before is None and after is None:
            return Schema__Diff_File(path=path, status='unchanged')

        if before is None:
            # added
            return Schema__Diff_File(
                path        = path,
                status      = 'added',
                is_binary   = self._is_binary(after),
                size_before = 0,
                size_after  = len(after),
                hash_before = None,
                hash_after  = self._sha256(after),
                diff_text   = None,
            )

        if after is None:
            # deleted
            return Schema__Diff_File(
                path        = path,
                status      = 'deleted',
                is_binary   = self._is_binary(before),
                size_before = len(before),
                size_after  = 0,
                hash_before = self._sha256(before),
                hash_after  = None,
                diff_text   = None,
            )

        # both exist — check if changed
        hash_before = self._sha256(before)
        hash_after  = self._sha256(after)

        if hash_before == hash_after:
            return Schema__Diff_File(
                path        = path,
                status      = 'unchanged',
                is_binary   = self._is_binary(before),
                size_before = len(before),
                size_after  = len(after),
                hash_before = hash_before,
                hash_after  = hash_after,
                diff_text   = None,
            )

        # modified
        is_binary = self._is_binary(before) or self._is_binary(after)
        diff_text = None
        if not is_binary:
            diff_text = self._unified_diff(path, before, after)

        return Schema__Diff_File(
            path        = path,
            status      = 'modified',
            is_binary   = is_binary,
            size_before = len(before),
            size_after  = len(after),
            hash_before = hash_before,
            hash_after  = hash_after,
            diff_text   = diff_text,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _is_binary(self, data: bytes) -> bool:
        return b'\x00' in data[:BINARY_CHECK_BYTES]

    def _sha256(self, data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    def _unified_diff(self, path: str, before: bytes, after: bytes) -> str:
        before_text = before.decode('utf-8', errors='replace').splitlines(keepends=True)
        after_text  = after.decode('utf-8',  errors='replace').splitlines(keepends=True)
        lines = list(difflib.unified_diff(
            before_text,
            after_text,
            fromfile=f'a/{path}',
            tofile=f'b/{path}',
        ))
        return ''.join(lines)

    def _build_result(self, directory: str, mode: str, commit_id: str,
                      diff_file_list: list) -> Schema__Diff_Result:
        added    = sum(1 for f in diff_file_list if f.status == 'added')
        modified = sum(1 for f in diff_file_list if f.status == 'modified')
        deleted  = sum(1 for f in diff_file_list if f.status == 'deleted')
        return Schema__Diff_Result(
            directory      = directory,
            mode           = mode,
            commit_id      = commit_id or None,
            files          = diff_file_list,
            added_count    = added,
            modified_count = modified,
            deleted_count  = deleted,
        )

    def _init_components(self, directory: str) -> Vault__Components:
        vault_key_path = os.path.join(directory, SG_VAULT_DIR, 'local', 'vault_key')
        with open(vault_key_path, 'r') as f:
            vault_key = f.read().strip()

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
        with open(config_path, 'r') as f:
            data = json.load(f)
        return Schema__Local_Config.from_json(data)

    def _flatten_commit(self, c: Vault__Components, commit_id: str) -> dict:
        """Return flat {path: bytes} for a given commit_id."""
        pki          = c.pki
        obj_store    = c.obj_store
        ref_manager  = c.ref_manager
        read_key     = c.read_key

        vault_commit = Vault__Commit(crypto=self.crypto, pki=pki,
                                     object_store=obj_store, ref_manager=ref_manager)
        commit_obj   = vault_commit.load_commit(commit_id, read_key)
        sub_tree     = Vault__Sub_Tree(crypto=self.crypto, obj_store=obj_store)
        flat_map     = sub_tree.flatten(str(commit_obj.tree_id), read_key)

        result = {}
        for path, entry in flat_map.items():
            blob_id    = entry.get('blob_id')
            if not blob_id:
                continue
            ciphertext = obj_store.load(blob_id)
            plaintext  = self.crypto.decrypt(read_key, ciphertext)
            result[path] = plaintext
        return result

    def _read_head_files(self, c: Vault__Components) -> dict:
        """Return flat {path: bytes} for clone branch HEAD."""
        storage        = c.storage
        branch_manager = c.branch_manager
        ref_manager    = c.ref_manager
        read_key       = c.read_key

        # Need directory from sg_dir
        sg_dir    = c.sg_dir
        directory = os.path.dirname(sg_dir)

        local_config = self._read_local_config(directory, storage)
        branch_id    = str(local_config.my_branch_id)

        index_id = c.branch_index_file_id
        if not index_id:
            return {}
        branch_index = branch_manager.load_branch_index(directory, index_id, read_key)
        branch_meta  = branch_manager.get_branch_by_id(branch_index, branch_id)
        if not branch_meta:
            return {}

        ref_id    = str(branch_meta.head_ref_id)
        commit_id = ref_manager.read_ref(ref_id, read_key)
        if not commit_id:
            return {}

        return self._flatten_commit(c, commit_id)

    def _read_named_branch_files(self, c: Vault__Components, directory: str) -> dict:
        """Return flat {path: bytes} for named branch HEAD (e.g., 'current')."""
        branch_manager = c.branch_manager
        ref_manager    = c.ref_manager
        read_key       = c.read_key

        index_id = c.branch_index_file_id
        if not index_id:
            return {}
        branch_index = branch_manager.load_branch_index(directory, index_id, read_key)
        named_meta   = branch_manager.get_branch_by_name(branch_index, 'current')
        if not named_meta:
            return {}

        ref_id    = str(named_meta.head_ref_id)
        commit_id = ref_manager.read_ref(ref_id, read_key)
        if not commit_id:
            return {}

        return self._flatten_commit(c, commit_id)

    def _read_commit_files(self, c: Vault__Components, commit_id: str) -> dict:
        """Return flat {path: bytes} for a specific commit_id."""
        if not commit_id:
            return {}
        return self._flatten_commit(c, commit_id)

    def _scan_working_files(self, directory: str, c: Vault__Components) -> dict:
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
                with open(full_path, 'rb') as f:
                    result[rel_path] = f.read()
        return result
