import os
from sg_send_cli.api.Vault__Backend              import Vault__Backend
from sg_send_cli.safe_types.Safe_Str__Vault_Path import Safe_Str__Vault_Path


class Vault__Backend__Local(Vault__Backend):
    """Local folder backend — stores vault files in a directory on disk.

    Used for local-only vaults, testing, and vault export/import.
    The root_path should point to a directory that acts as the vault store.
    """
    root_path : Safe_Str__Vault_Path = None

    def read(self, file_id: str) -> bytes:
        path = os.path.join(str(self.root_path), file_id)
        if not os.path.isfile(path):
            raise FileNotFoundError(f'Not found: {file_id}')
        with open(path, 'rb') as f:
            return f.read()

    def write(self, file_id: str, data: bytes) -> dict:
        path = os.path.join(str(self.root_path), file_id)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'wb') as f:
            f.write(data)
        return dict(status='ok', file_id=file_id)

    def delete(self, file_id: str) -> dict:
        path = os.path.join(str(self.root_path), file_id)
        if os.path.isfile(path):
            os.remove(path)
        return dict(status='ok', file_id=file_id)

    def list_files(self, prefix: str = '') -> list:
        root = str(self.root_path)
        if prefix:
            search_dir = os.path.join(root, prefix)
        else:
            search_dir = root

        if not os.path.isdir(search_dir):
            return []

        result = []
        for dirpath, dirnames, filenames in os.walk(search_dir):
            for filename in filenames:
                full_path = os.path.join(dirpath, filename)
                rel_path  = os.path.relpath(full_path, root).replace(os.sep, '/')
                result.append(rel_path)
        return sorted(result)

    def exists(self, file_id: str) -> bool:
        path = os.path.join(str(self.root_path), file_id)
        return os.path.isfile(path)
