"""Vault__Cache_Manager — build, read, write and enumerate cache-layer objects.

Cache objects are *derived, never authoritative*: losing one is a performance
problem, never a correctness one. They live at client-computable, path-derived
locations under bare/cache/{value,pointer}/ (contract 08/12 v0).

Two rules this class exists to enforce:

  D10 — cache objects are written DIRECTLY to their derived path, following the
        ref / branch-index mutable-object pattern. They must never go through
        Vault__Object_Store, whose CAS guard raises when an existing id holds
        different bytes — which is exactly what every cache update looks like.

  §5  — the envelope always uses a RANDOM IV (crypto.encrypt), never
        encrypt_deterministic: these objects are mutable, and a deterministic IV
        would leak value-equality across paths and updates.
"""
import json
import os

from osbot_utils.type_safe.Type_Safe                    import Type_Safe
from sgit_ai.crypto.Vault__Crypto                       import Vault__Crypto
from sgit_ai.storage.Vault__Storage                     import Vault__Storage, CACHE_VALUE, CACHE_POINTER
from sgit_ai.schemas.cache.Schema__Cache_Value          import Schema__Cache_Value
from sgit_ai.schemas.cache.Schema__Cache_Pointer        import Schema__Cache_Pointer
from sgit_ai.safe_types.Enum__Cache_Kind                import Enum__Cache_Kind
from sgit_ai.safe_types.Enum__Cache_Mutability          import Enum__Cache_Mutability

CACHE_ID_PREFIX = 'cch-pid-'


class Vault__Cache_Manager(Type_Safe):
    crypto  : Vault__Crypto
    storage : Vault__Storage

    # --- id derivation -----------------------------------------------------

    def cache_id(self, read_key: bytes, vault_id: str, path: str,
                 kind: Enum__Cache_Kind,
                 mutability: Enum__Cache_Mutability = Enum__Cache_Mutability.SNW) -> str:
        """Full cache id: cch-pid-{mutability}-{HMAC(read_key, domain)[:12]}.

        `path` must be the RAW vault-relative path (a flatten() key), so every
        runtime derives the same id. The mutability label is not hashed.
        """
        if kind == Enum__Cache_Kind.VALUE:
            tail = self.crypto.derive_cache_value_file_id(read_key, vault_id, path)
        else:
            tail = self.crypto.derive_cache_pointer_file_id(read_key, vault_id, path)
        return f'{CACHE_ID_PREFIX}{mutability.value}-{tail}'

    def kind_dir_name(self, kind: Enum__Cache_Kind) -> str:
        return CACHE_VALUE if kind == Enum__Cache_Kind.VALUE else CACHE_POINTER

    def kind_for_dir_name(self, dir_name: str) -> Enum__Cache_Kind:
        """Inverse of kind_dir_name — used when parsing wire file_ids. None if unknown."""
        if dir_name == CACHE_VALUE:
            return Enum__Cache_Kind.VALUE
        if dir_name == CACHE_POINTER:
            return Enum__Cache_Kind.POINTER
        return None

    def file_id(self, kind: Enum__Cache_Kind, cache_id: str) -> str:
        """Wire file_id for the batch API."""
        return self.storage.cache_file_id(self.kind_dir_name(kind), cache_id)

    # --- object construction ----------------------------------------------

    def build_value(self, path: str, content: bytes, commit_id: str,
                    content_type: str, content_hash: str,
                    mutability: Enum__Cache_Mutability = Enum__Cache_Mutability.SNW
                    ) -> Schema__Cache_Value:
        import base64
        return Schema__Cache_Value(schema       = 'cache_value_v1',
                                   kind         = Enum__Cache_Kind.VALUE,
                                   path         = path,
                                   mutability   = mutability,
                                   commit_id    = commit_id,
                                   content_type = content_type,
                                   size         = len(content),
                                   content_hash = content_hash,
                                   value_b64    = base64.b64encode(content).decode('ascii'))

    def build_pointer(self, path: str, target_id: str, target_kind, commit_id: str,
                      content_type: str, size: int = 0, content_hash: str = None,
                      mutability: Enum__Cache_Mutability = Enum__Cache_Mutability.SNW
                      ) -> Schema__Cache_Pointer:
        return Schema__Cache_Pointer(schema       = 'cache_pointer_v1',
                                     kind         = Enum__Cache_Kind.POINTER,
                                     path         = path,
                                     mutability   = mutability,
                                     commit_id    = commit_id,
                                     content_type = content_type,
                                     size         = size,
                                     target_kind  = target_kind,
                                     target_id    = target_id,
                                     content_hash = content_hash)

    # --- encrypt / decrypt -------------------------------------------------

    def encrypt_object(self, obj, read_key: bytes) -> bytes:
        """Random-IV AES-GCM over the object's JSON (contract §5)."""
        return self.crypto.encrypt(read_key, json.dumps(obj.json()).encode())

    def decrypt_object(self, ciphertext: bytes, read_key: bytes, kind: Enum__Cache_Kind):
        data   = json.loads(self.crypto.decrypt(read_key, ciphertext))
        schema = Schema__Cache_Value if kind == Enum__Cache_Kind.VALUE else Schema__Cache_Pointer
        return schema.from_json(data)

    # --- local storage (direct write — D10) --------------------------------

    def save(self, directory: str, kind: Enum__Cache_Kind, cache_id: str,
             obj, read_key: bytes) -> str:
        """Encrypt and write the object directly to its derived path.

        Deliberately NOT routed through Vault__Object_Store: overwriting the same
        id with different bytes is the normal update path here (D10).
        """
        path = self.storage.cache_path(directory, self.kind_dir_name(kind), cache_id)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'wb') as f:
            f.write(self.encrypt_object(obj, read_key))
        return path

    def load(self, directory: str, kind: Enum__Cache_Kind, cache_id: str, read_key: bytes):
        path = self.storage.cache_path(directory, self.kind_dir_name(kind), cache_id)
        if not os.path.isfile(path):
            return None
        with open(path, 'rb') as f:
            return self.decrypt_object(f.read(), read_key, kind)

    def exists(self, directory: str, kind: Enum__Cache_Kind, cache_id: str) -> bool:
        return os.path.isfile(self.storage.cache_path(directory, self.kind_dir_name(kind), cache_id))

    def delete(self, directory: str, kind: Enum__Cache_Kind, cache_id: str) -> bool:
        path = self.storage.cache_path(directory, self.kind_dir_name(kind), cache_id)
        if os.path.isfile(path):
            os.remove(path)
            return True
        return False

    def list_ids(self, directory: str, kind: Enum__Cache_Kind) -> list:
        """Local cache ids of one kind. Absence of the folder is normal (old vaults)."""
        dir_path = self.storage.cache_path(directory, self.kind_dir_name(kind), '')
        dir_path = os.path.dirname(os.path.join(dir_path, '_'))
        if not os.path.isdir(dir_path):
            return []
        return sorted(n for n in os.listdir(dir_path) if n.startswith(CACHE_ID_PREFIX))

    def list_all(self, directory: str) -> list:
        """[(kind, cache_id)] across both kinds — the folder-as-registry read (D5)."""
        out = []
        for kind in (Enum__Cache_Kind.VALUE, Enum__Cache_Kind.POINTER):
            out.extend((kind, cid) for cid in self.list_ids(directory, kind))
        return out
