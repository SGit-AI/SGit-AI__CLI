import os
from osbot_utils.type_safe.Type_Safe import Type_Safe

REFS_DIR  = 'refs'
HEAD_FILE = 'head'


class Vault__Ref_Manager(Type_Safe):
    vault_path : str

    def read_head(self) -> str:
        path = self._head_path()
        if not os.path.isfile(path):
            return None
        with open(path, 'r') as f:
            commit_id = f.read().strip()
        return commit_id if commit_id else None

    def write_head(self, commit_id: str) -> None:
        path = self._head_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w') as f:
            f.write(commit_id)

    def is_initialized(self) -> bool:
        return os.path.isfile(self._head_path())

    def _head_path(self) -> str:
        return os.path.join(self.vault_path, REFS_DIR, HEAD_FILE)
