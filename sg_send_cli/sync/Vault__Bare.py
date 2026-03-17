import json
import os
from osbot_utils.type_safe.Type_Safe                import Type_Safe
from sg_send_cli.crypto.Vault__Crypto               import Vault__Crypto
from sg_send_cli.objects.Vault__Object_Store        import Vault__Object_Store
from sg_send_cli.objects.Vault__Ref_Manager         import Vault__Ref_Manager
from sg_send_cli.schemas.Schema__Object_Commit      import Schema__Object_Commit
from sg_send_cli.sync.Vault__Sub_Tree               import Vault__Sub_Tree

from sg_send_cli.sync.Vault__Storage          import SG_VAULT_DIR, VAULT_KEY_FILE
TOKEN_FILE     = 'token'


class Vault__Bare(Type_Safe):
    crypto : Vault__Crypto

    def is_bare(self, directory: str) -> bool:
        """A bare vault has the bare/ structure but no vault key in local/."""
        sg_vault_dir       = os.path.join(directory, SG_VAULT_DIR)
        vault_key_path     = os.path.join(sg_vault_dir, 'local', VAULT_KEY_FILE)
        refs_dir           = os.path.join(sg_vault_dir, 'bare', 'refs')
        has_vault_key      = os.path.isfile(vault_key_path)
        has_refs           = os.path.isdir(refs_dir) and any(
                                f.startswith('ref-pid-') for f in os.listdir(refs_dir))
        return os.path.isdir(sg_vault_dir) and has_refs and not has_vault_key

    def checkout(self, directory: str, vault_key: str):
        """Extract working copy from HEAD tree using sub-tree checkout."""
        keys         = self.crypto.derive_keys_from_vault_key(vault_key)
        read_key     = keys['read_key_bytes']
        sg_vault_dir = os.path.join(directory, SG_VAULT_DIR)
        object_store = Vault__Object_Store(vault_path=sg_vault_dir, crypto=self.crypto)
        ref_manager  = Vault__Ref_Manager(vault_path=sg_vault_dir, crypto=self.crypto)
        sub_tree     = Vault__Sub_Tree(crypto=self.crypto, obj_store=object_store)

        tree_id = self._get_head_tree_id(ref_manager, object_store, read_key, keys['ref_file_id'])
        sub_tree.checkout(directory, tree_id, read_key)

        local_dir = os.path.join(sg_vault_dir, 'local')
        os.makedirs(local_dir, exist_ok=True)
        with open(os.path.join(local_dir, VAULT_KEY_FILE), 'w') as f:
            f.write(vault_key)

    def clean(self, directory: str):
        """Remove working copy files and vault key, preserving bare/ structure."""
        sg_vault_dir = os.path.join(directory, SG_VAULT_DIR)

        tree_entries = self._list_working_copy_files(directory, sg_vault_dir)

        for rel_path in tree_entries:
            full_path = os.path.join(directory, rel_path)
            if os.path.isfile(full_path):
                os.remove(full_path)

        self._remove_empty_dirs(directory, sg_vault_dir)

        local_dir = os.path.join(sg_vault_dir, 'local')
        if os.path.isdir(local_dir):
            for convenience_file in [VAULT_KEY_FILE, TOKEN_FILE]:
                path = os.path.join(local_dir, convenience_file)
                if os.path.isfile(path):
                    os.remove(path)

    def read_file(self, directory: str, vault_key: str, file_path: str) -> bytes:
        """Read a single file from the vault by path (supports nested paths)."""
        keys         = self.crypto.derive_keys_from_vault_key(vault_key)
        read_key     = keys['read_key_bytes']
        sg_vault_dir = os.path.join(directory, SG_VAULT_DIR)
        object_store = Vault__Object_Store(vault_path=sg_vault_dir, crypto=self.crypto)
        ref_manager  = Vault__Ref_Manager(vault_path=sg_vault_dir, crypto=self.crypto)
        sub_tree     = Vault__Sub_Tree(crypto=self.crypto, obj_store=object_store)

        tree_id    = self._get_head_tree_id(ref_manager, object_store, read_key, keys['ref_file_id'])
        flat_entries = sub_tree.flatten(tree_id, read_key)
        entry      = flat_entries.get(file_path)
        if not entry:
            raise RuntimeError(f'File not found in vault: {file_path}')
        blob_data = object_store.load(str(entry.blob_id))
        return self.crypto.decrypt(read_key, blob_data)

    def list_files(self, directory: str, vault_key: str) -> list:
        """List all files in the vault (flattened from sub-trees)."""
        keys         = self.crypto.derive_keys_from_vault_key(vault_key)
        read_key     = keys['read_key_bytes']
        sg_vault_dir = os.path.join(directory, SG_VAULT_DIR)
        object_store = Vault__Object_Store(vault_path=sg_vault_dir, crypto=self.crypto)
        ref_manager  = Vault__Ref_Manager(vault_path=sg_vault_dir, crypto=self.crypto)
        sub_tree     = Vault__Sub_Tree(crypto=self.crypto, obj_store=object_store)

        tree_id      = self._get_head_tree_id(ref_manager, object_store, read_key, keys['ref_file_id'])
        flat_entries = sub_tree.flatten(tree_id, read_key)
        return [dict(path=path, size=int(entry.size), blob_id=str(entry.blob_id))
                for path, entry in sorted(flat_entries.items())]

    # --- Internal helpers ---

    def _get_head_tree_id(self, ref_manager, object_store, read_key, ref_file_id):
        """Resolve HEAD ref → commit → tree_id."""
        commit_id = ref_manager.read_ref(ref_file_id, read_key)
        if not commit_id:
            raise RuntimeError('Vault has no commits (no HEAD ref)')
        commit_data = self.crypto.decrypt(read_key, object_store.load(commit_id))
        commit      = Schema__Object_Commit.from_json(json.loads(commit_data))
        return str(commit.tree_id)

    def _list_working_copy_files(self, directory: str, sg_vault_dir: str) -> list:
        result = []
        for root, dirs, files in os.walk(directory):
            dirs[:] = [d for d in dirs if os.path.join(root, d) != sg_vault_dir and not d.startswith('.')]
            for filename in files:
                if filename.startswith('.'):
                    continue
                full_path = os.path.join(root, filename)
                rel_path  = os.path.relpath(full_path, directory).replace(os.sep, '/')
                result.append(rel_path)
        return result

    def _remove_empty_dirs(self, directory: str, sg_vault_dir: str):
        for root, dirs, files in os.walk(directory, topdown=False):
            if root == directory:
                continue
            if root.startswith(sg_vault_dir):
                continue
            if not os.listdir(root):
                os.rmdir(root)
