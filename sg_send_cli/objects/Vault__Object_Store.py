import os
from osbot_utils.type_safe.Type_Safe                 import Type_Safe
from sg_send_cli.crypto.Vault__Crypto                import Vault__Crypto
from sg_send_cli.safe_types.Safe_Str__Vault_Path     import Safe_Str__Vault_Path

OBJECTS_DIR    = 'objects'
BARE_DATA_DIR  = os.path.join('bare', 'data')
OBJ_PREFIX     = 'obj-'


class Vault__Object_Store(Type_Safe):
    vault_path : Safe_Str__Vault_Path = None
    crypto     : Vault__Crypto
    use_v2     : bool                 = False

    def store(self, ciphertext: bytes) -> str:
        object_id   = self._compute_id(ciphertext)
        path        = self.object_path(object_id)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'wb') as f:
            f.write(ciphertext)
        return object_id

    def load(self, object_id: str) -> bytes:
        path = self.object_path(object_id)
        if not os.path.isfile(path):
            path = self._fallback_path(object_id)
        with open(path, 'rb') as f:
            return f.read()

    def exists(self, object_id: str) -> bool:
        if os.path.isfile(self.object_path(object_id)):
            return True
        return os.path.isfile(self._fallback_path(object_id))

    def object_path(self, object_id: str) -> str:
        if self.use_v2:
            bare_id = object_id if object_id.startswith(OBJ_PREFIX) else OBJ_PREFIX + object_id
            return os.path.join(self.vault_path, BARE_DATA_DIR, bare_id)
        else:
            raw_id = object_id[len(OBJ_PREFIX):] if object_id.startswith(OBJ_PREFIX) else object_id
            prefix = raw_id[:2]
            suffix = raw_id[2:]
            return os.path.join(self.vault_path, OBJECTS_DIR, prefix, suffix)

    def all_object_ids(self) -> list:
        result = []
        if self.use_v2:
            data_dir = os.path.join(self.vault_path, BARE_DATA_DIR)
            if os.path.isdir(data_dir):
                for name in sorted(os.listdir(data_dir)):
                    if name.startswith(OBJ_PREFIX):
                        result.append(name)
        else:
            objects_dir = os.path.join(self.vault_path, OBJECTS_DIR)
            if os.path.isdir(objects_dir):
                for prefix in sorted(os.listdir(objects_dir)):
                    prefix_dir = os.path.join(objects_dir, prefix)
                    if not os.path.isdir(prefix_dir) or len(prefix) != 2:
                        continue
                    for suffix in sorted(os.listdir(prefix_dir)):
                        result.append(prefix + suffix)
        return result

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
        raw_hash = self.crypto.compute_object_id(ciphertext)
        if self.use_v2:
            return OBJ_PREFIX + raw_hash
        return raw_hash

    def _fallback_path(self, object_id: str) -> str:
        raw_id = object_id[len(OBJ_PREFIX):] if object_id.startswith(OBJ_PREFIX) else object_id
        if self.use_v2:
            return os.path.join(self.vault_path, OBJECTS_DIR, raw_id[:2], raw_id[2:])
        else:
            return os.path.join(self.vault_path, BARE_DATA_DIR, OBJ_PREFIX + raw_id)
