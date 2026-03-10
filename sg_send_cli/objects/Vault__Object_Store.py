import os
from osbot_utils.type_safe.Type_Safe     import Type_Safe
from sg_send_cli.crypto.Vault__Crypto    import Vault__Crypto

OBJECTS_DIR = 'objects'


class Vault__Object_Store(Type_Safe):
    vault_path : str
    crypto     : Vault__Crypto

    def store(self, ciphertext: bytes) -> str:
        object_id   = self.crypto.compute_object_id(ciphertext)
        path        = self.object_path(object_id)
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
        prefix = object_id[:2]
        suffix = object_id[2:]
        return os.path.join(self.vault_path, OBJECTS_DIR, prefix, suffix)

    def all_object_ids(self) -> list:
        objects_dir = os.path.join(self.vault_path, OBJECTS_DIR)
        result      = []
        if not os.path.isdir(objects_dir):
            return result
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
        ciphertext    = self.load(object_id)
        computed_id   = self.crypto.compute_object_id(ciphertext)
        return computed_id == object_id
