import os
from osbot_utils.type_safe.Type_Safe                 import Type_Safe
from sgit_ai.crypto.Vault__Crypto                import Vault__Crypto
from sgit_ai.safe_types.Safe_Str__Vault_Path     import Safe_Str__Vault_Path

BARE_DATA_DIR      = os.path.join('bare', 'data')
OBJ_CAS_IMM_PREFIX = 'obj-cas-imm-'


class Vault__Object_Store(Type_Safe):
    vault_path : Safe_Str__Vault_Path = None
    crypto     : Vault__Crypto

    def store(self, ciphertext: bytes) -> str:
        object_id   = self._compute_id(ciphertext)
        path        = self.object_path(object_id)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'wb') as f:
            f.write(ciphertext)
        return object_id

    def store_raw(self, object_id: str, ciphertext: bytes) -> str:
        """Store a blob with a pre-determined object_id (used for change pack drain)."""
        path = self.object_path(object_id)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'wb') as f:
            f.write(ciphertext)
        return object_id

    def load(self, object_id: str) -> bytes:
        path = self.object_path(object_id)
        with open(path, 'rb') as f:
            return f.read()

    def exists(self, object_id: str) -> bool:
        return os.path.isfile(self.object_path(object_id))

    def object_path(self, object_id: str) -> str:
        return os.path.join(self.vault_path, BARE_DATA_DIR, object_id)

    def all_object_ids(self) -> list[str]:
        data_dir = os.path.join(self.vault_path, BARE_DATA_DIR)
        if not os.path.isdir(data_dir):
            return []
        return sorted(f for f in os.listdir(data_dir) if f.startswith(OBJ_CAS_IMM_PREFIX))

    def object_count(self) -> int:
        return len(self.all_object_ids())

    def total_size(self) -> int:
        total = 0
        for object_id in self.all_object_ids():
            total += os.path.getsize(self.object_path(object_id))
        return total

    def verify_integrity(self, object_id: str) -> bool:
        if not self.exists(object_id):
            return False
        ciphertext  = self.load(object_id)
        computed_id = self._compute_id(ciphertext)
        return computed_id == object_id

    def _compute_id(self, ciphertext: bytes) -> str:
        return self.crypto.compute_object_id(ciphertext)
