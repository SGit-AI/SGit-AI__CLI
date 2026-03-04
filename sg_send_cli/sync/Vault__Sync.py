import json
import os
from   datetime                        import datetime, timezone
from   osbot_utils.type_safe.Type_Safe import Type_Safe
from   sg_send_cli.crypto.Vault__Crypto import Vault__Crypto
from   sg_send_cli.api.Vault__API       import Vault__API

SG_VAULT_DIR  = '.sg_vault'
HEAD_FILE     = 'HEAD'
TREE_FILE     = 'tree.json'
SETTINGS_FILE = 'settings.json'


class Vault__Sync(Type_Safe):
    crypto : Vault__Crypto
    api    : Vault__API

    def clone(self, vault_key: str, directory: str = None) -> str:
        keys       = self.crypto.derive_keys_from_vault_key(vault_key)
        vault_id   = keys['vault_id']
        read_key   = keys['read_key_bytes']

        if directory is None:
            directory = vault_id
        os.makedirs(directory, exist_ok=True)

        settings = self._download_and_decrypt(vault_id, keys['settings_file_id'], read_key)
        tree     = self._download_and_decrypt(vault_id, keys['tree_file_id'], read_key)

        settings_data = json.loads(settings)
        tree_data     = json.loads(tree)

        file_map = self._flatten_tree(tree_data.get('tree', {}))
        for file_path, file_info in file_map.items():
            file_id        = file_info['file_id']
            encrypted_data = self.api.read(vault_id, file_id)
            plaintext      = self.crypto.decrypt(read_key, encrypted_data)
            full_path      = os.path.join(directory, file_path)
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            with open(full_path, 'wb') as f:
                f.write(plaintext)

        sg_vault_dir = os.path.join(directory, SG_VAULT_DIR)
        os.makedirs(sg_vault_dir, exist_ok=True)
        with open(os.path.join(sg_vault_dir, HEAD_FILE), 'w') as f:
            f.write(vault_key)
        with open(os.path.join(sg_vault_dir, TREE_FILE), 'w') as f:
            json.dump(tree_data, f, indent=2)
        with open(os.path.join(sg_vault_dir, SETTINGS_FILE), 'w') as f:
            json.dump(settings_data, f, indent=2)

        return directory

    def pull(self, directory: str = '.') -> dict:
        vault_key = self._read_head(directory)
        keys      = self.crypto.derive_keys_from_vault_key(vault_key)
        vault_id  = keys['vault_id']
        read_key  = keys['read_key_bytes']

        settings      = self._download_and_decrypt(vault_id, keys['settings_file_id'], read_key)
        tree          = self._download_and_decrypt(vault_id, keys['tree_file_id'], read_key)
        settings_data = json.loads(settings)
        tree_data     = json.loads(tree)

        old_tree_data = self._read_local_tree(directory)
        old_file_map  = self._flatten_tree(old_tree_data.get('tree', {}))
        new_file_map  = self._flatten_tree(tree_data.get('tree', {}))

        old_paths = set(old_file_map.keys())
        new_paths = set(new_file_map.keys())

        added    = new_paths - old_paths
        deleted  = old_paths - new_paths
        modified = set()
        for path in old_paths & new_paths:
            if old_file_map[path].get('file_id') != new_file_map[path].get('file_id'):
                modified.add(path)

        for path in added | modified:
            file_id        = new_file_map[path]['file_id']
            encrypted_data = self.api.read(vault_id, file_id)
            plaintext      = self.crypto.decrypt(read_key, encrypted_data)
            full_path      = os.path.join(directory, path)
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            with open(full_path, 'wb') as f:
                f.write(plaintext)

        for path in deleted:
            full_path = os.path.join(directory, path)
            if os.path.exists(full_path):
                os.remove(full_path)

        sg_vault_dir = os.path.join(directory, SG_VAULT_DIR)
        with open(os.path.join(sg_vault_dir, TREE_FILE), 'w') as f:
            json.dump(tree_data, f, indent=2)
        with open(os.path.join(sg_vault_dir, SETTINGS_FILE), 'w') as f:
            json.dump(settings_data, f, indent=2)

        return dict(added=sorted(added), modified=sorted(modified), deleted=sorted(deleted))

    def push(self, directory: str = '.') -> dict:
        vault_key = self._read_head(directory)
        keys      = self.crypto.derive_keys_from_vault_key(vault_key)
        vault_id  = keys['vault_id']
        read_key  = keys['read_key_bytes']
        write_key = keys['write_key']

        old_tree_data = self._read_local_tree(directory)
        old_file_map  = self._flatten_tree(old_tree_data.get('tree', {}))
        new_file_map  = self._scan_local_directory(directory)

        old_paths = set(old_file_map.keys())
        new_paths = set(new_file_map.keys())

        added    = new_paths - old_paths
        deleted  = old_paths - new_paths
        common   = old_paths & new_paths
        modified = set()

        for path in common:
            local_file = os.path.join(directory, path)
            with open(local_file, 'rb') as f:
                content = f.read()
            if len(content) != old_file_map[path].get('size', -1):
                modified.add(path)

        uploaded = {}
        for path in added | modified:
            local_file = os.path.join(directory, path)
            with open(local_file, 'rb') as f:
                content = f.read()
            file_id   = os.urandom(6).hex()
            encrypted = self.crypto.encrypt(read_key, content)
            self.api.write(vault_id, file_id, write_key, encrypted)
            uploaded[path] = dict(file_id=file_id, size=len(content))

        for path in deleted:
            file_id = old_file_map[path]['file_id']
            self.api.delete(vault_id, file_id, write_key)

        new_tree_data = self._build_tree_json(old_tree_data, old_file_map, uploaded, deleted)

        tree_json     = json.dumps(new_tree_data).encode()
        encrypted_tree = self.crypto.encrypt(read_key, tree_json)
        self.api.write(vault_id, keys['tree_file_id'], write_key, encrypted_tree)

        settings_data = self._read_local_settings(directory)
        settings_json  = json.dumps(settings_data).encode()
        encrypted_settings = self.crypto.encrypt(read_key, settings_json)
        self.api.write(vault_id, keys['settings_file_id'], write_key, encrypted_settings)

        sg_vault_dir = os.path.join(directory, SG_VAULT_DIR)
        with open(os.path.join(sg_vault_dir, TREE_FILE), 'w') as f:
            json.dump(new_tree_data, f, indent=2)

        return dict(added=list(added), modified=list(modified), deleted=list(deleted))

    def status(self, directory: str = '.') -> dict:
        old_tree_data = self._read_local_tree(directory)
        old_file_map  = self._flatten_tree(old_tree_data.get('tree', {}))
        new_file_map  = self._scan_local_directory(directory)

        old_paths = set(old_file_map.keys())
        new_paths = set(new_file_map.keys())

        added    = sorted(new_paths - old_paths)
        deleted  = sorted(old_paths - new_paths)
        common   = old_paths & new_paths
        modified = []

        for path in sorted(common):
            local_file = os.path.join(directory, path)
            with open(local_file, 'rb') as f:
                content = f.read()
            if len(content) != old_file_map[path].get('size', -1):
                modified.append(path)

        return dict(added=added, modified=modified, deleted=deleted,
                    clean=not added and not modified and not deleted)

    def remote_status(self, directory: str = '.') -> dict:
        vault_key = self._read_head(directory)
        keys      = self.crypto.derive_keys_from_vault_key(vault_key)
        vault_id  = keys['vault_id']
        read_key  = keys['read_key_bytes']

        remote_tree_raw  = self._download_and_decrypt(vault_id, keys['tree_file_id'], read_key)
        remote_tree_data = json.loads(remote_tree_raw)
        remote_file_map  = self._flatten_tree(remote_tree_data.get('tree', {}))

        local_tree_data  = self._read_local_tree(directory)
        local_file_map   = self._flatten_tree(local_tree_data.get('tree', {}))

        remote_paths = set(remote_file_map.keys())
        local_paths  = set(local_file_map.keys())

        remote_added    = sorted(remote_paths - local_paths)
        remote_deleted  = sorted(local_paths - remote_paths)
        remote_modified = []
        for path in sorted(remote_paths & local_paths):
            if remote_file_map[path].get('file_id') != local_file_map[path].get('file_id'):
                remote_modified.append(path)

        local_status = self.status(directory)

        return dict(remote_version = remote_tree_data.get('version'),
                    local_version  = local_tree_data.get('version'),
                    remote_added   = remote_added,
                    remote_modified= remote_modified,
                    remote_deleted = remote_deleted,
                    local_added    = local_status['added'],
                    local_modified = local_status['modified'],
                    local_deleted  = local_status['deleted'])

    # --- internal helpers ---

    def _download_and_decrypt(self, vault_id: str, file_id: str, read_key: bytes) -> bytes:
        encrypted = self.api.read(vault_id, file_id)
        return self.crypto.decrypt(read_key, encrypted)

    def _read_head(self, directory: str) -> str:
        head_path = os.path.join(directory, SG_VAULT_DIR, HEAD_FILE)
        with open(head_path, 'r') as f:
            return f.read().strip()

    def _read_local_tree(self, directory: str) -> dict:
        tree_path = os.path.join(directory, SG_VAULT_DIR, TREE_FILE)
        with open(tree_path, 'r') as f:
            return json.load(f)

    def _read_local_settings(self, directory: str) -> dict:
        settings_path = os.path.join(directory, SG_VAULT_DIR, SETTINGS_FILE)
        with open(settings_path, 'r') as f:
            return json.load(f)

    def _flatten_tree(self, tree: dict, prefix: str = '') -> dict:
        result = {}
        for name, node in tree.items():
            if name == '/':
                result.update(self._flatten_tree(node.get('children', {}), prefix))
            elif node.get('type') == 'folder':
                child_prefix = f'{prefix}{name}/' if prefix else f'{name}/'
                result.update(self._flatten_tree(node.get('children', {}), child_prefix))
            elif node.get('type') == 'file':
                path = f'{prefix}{name}'
                result[path] = node
        return result

    def _scan_local_directory(self, directory: str) -> dict:
        result = {}
        for root, dirs, files in os.walk(directory):
            dirs[:] = [d for d in dirs if d != SG_VAULT_DIR and not d.startswith('.')]
            for filename in files:
                if filename.startswith('.'):
                    continue
                full_path = os.path.join(root, filename)
                rel_path  = os.path.relpath(full_path, directory)
                rel_path  = rel_path.replace(os.sep, '/')
                result[rel_path] = dict(size=os.path.getsize(full_path))
        return result

    def _build_tree_json(self, old_tree_data: dict, old_file_map: dict,
                         uploaded: dict, deleted: set) -> dict:
        now = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.000Z')
        all_files = {}
        for path, info in old_file_map.items():
            if path not in deleted:
                all_files[path] = info
        for path, info in uploaded.items():
            all_files[path] = dict(type    = 'file',
                                   file_id = info['file_id'],
                                   size    = info['size'],
                                   uploaded= now)

        tree = {'/': {'type': 'folder', 'children': {}}}
        for path, info in sorted(all_files.items()):
            parts   = path.split('/')
            current = tree['/']['children']
            for part in parts[:-1]:
                if part not in current:
                    current[part] = {'type': 'folder', 'children': {}}
                current = current[part]['children']
            current[parts[-1]] = info

        version = old_tree_data.get('version', 0) + 1
        return dict(version=version, updated=now, tree=tree)
