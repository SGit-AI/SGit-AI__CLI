import json
import os
from osbot_utils.type_safe.Type_Safe                import Type_Safe
from sg_send_cli.crypto.Vault__Crypto               import Vault__Crypto
from sg_send_cli.objects.Vault__Object_Store        import Vault__Object_Store
from sg_send_cli.objects.Vault__Ref_Manager         import Vault__Ref_Manager
from sg_send_cli.schemas.Schema__Object_Commit      import Schema__Object_Commit
from sg_send_cli.schemas.Schema__Object_Tree        import Schema__Object_Tree

from sg_send_cli.sync.Vault__Storage          import SG_VAULT_DIR, VAULT_KEY_FILE
TOKEN_FILE     = 'token'
TREE_FILE      = 'tree.json'
SETTINGS_FILE  = 'settings.json'


class Vault__Bare(Type_Safe):
    crypto : Vault__Crypto

    def is_bare(self, directory: str) -> bool:
        sg_vault_dir       = os.path.join(directory, SG_VAULT_DIR)
        vault_key_new_path = os.path.join(sg_vault_dir, 'local', VAULT_KEY_FILE)
        vault_key_old_path = os.path.join(sg_vault_dir, 'VAULT-KEY')
        refs_head          = os.path.join(sg_vault_dir, 'refs', 'head')
        has_vault_key      = os.path.isfile(vault_key_new_path) or os.path.isfile(vault_key_old_path)
        return os.path.isdir(sg_vault_dir) and os.path.isfile(refs_head) and not has_vault_key

    def checkout(self, directory: str, vault_key: str):
        keys         = self.crypto.derive_keys_from_vault_key(vault_key)
        read_key     = keys['read_key_bytes']
        sg_vault_dir = os.path.join(directory, SG_VAULT_DIR)
        object_store = Vault__Object_Store(vault_path=sg_vault_dir, crypto=self.crypto)
        ref_manager  = Vault__Ref_Manager(vault_path=sg_vault_dir)

        tree = self._load_tree(ref_manager, object_store, read_key)

        for entry in tree.entries:
            blob_data = object_store.load(str(entry.blob_id))
            plaintext = self.crypto.decrypt(read_key, blob_data)
            full_path = os.path.join(directory, str(entry.path))
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            with open(full_path, 'wb') as f:
                f.write(plaintext)

        local_dir = os.path.join(sg_vault_dir, 'local')
        os.makedirs(local_dir, exist_ok=True)
        with open(os.path.join(local_dir, VAULT_KEY_FILE), 'w') as f:
            f.write(vault_key)

    def clean(self, directory: str):
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
        for legacy_file in ['VAULT-KEY', TOKEN_FILE]:
            path = os.path.join(sg_vault_dir, legacy_file)
            if os.path.isfile(path):
                os.remove(path)

    def read_file(self, directory: str, vault_key: str, file_path: str) -> bytes:
        keys         = self.crypto.derive_keys_from_vault_key(vault_key)
        read_key     = keys['read_key_bytes']
        sg_vault_dir = os.path.join(directory, SG_VAULT_DIR)
        object_store = Vault__Object_Store(vault_path=sg_vault_dir, crypto=self.crypto)
        ref_manager  = Vault__Ref_Manager(vault_path=sg_vault_dir)

        tree  = self._load_tree(ref_manager, object_store, read_key)
        entry = next((e for e in tree.entries if e.path == file_path), None)
        if not entry:
            raise RuntimeError(f'File not found in vault: {file_path}')
        blob_data = object_store.load(str(entry.blob_id))
        return self.crypto.decrypt(read_key, blob_data)

    def list_files(self, directory: str, vault_key: str) -> list:
        keys         = self.crypto.derive_keys_from_vault_key(vault_key)
        read_key     = keys['read_key_bytes']
        sg_vault_dir = os.path.join(directory, SG_VAULT_DIR)
        object_store = Vault__Object_Store(vault_path=sg_vault_dir, crypto=self.crypto)
        ref_manager  = Vault__Ref_Manager(vault_path=sg_vault_dir)

        tree = self._load_tree(ref_manager, object_store, read_key)
        return [dict(path=str(e.path), size=int(e.size), blob_id=str(e.blob_id)) for e in tree.entries]

    # --- Internal helpers ---

    def _load_tree(self, ref_manager: Vault__Ref_Manager, object_store: Vault__Object_Store, read_key: bytes) -> Schema__Object_Tree:
        commit_id = ref_manager.read_head()
        if not commit_id:
            raise RuntimeError('Vault has no commits (no HEAD ref)')
        commit_data = self.crypto.decrypt(read_key, object_store.load(commit_id))
        commit      = Schema__Object_Commit.from_json(json.loads(commit_data))
        tree_data   = self.crypto.decrypt(read_key, object_store.load(str(commit.tree_id)))
        return Schema__Object_Tree.from_json(json.loads(tree_data))

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
            if os.path.join(directory, os.path.relpath(root, directory).split(os.sep)[0]) == sg_vault_dir:
                continue
            if root.startswith(sg_vault_dir):
                continue
            if not os.listdir(root):
                os.rmdir(root)
