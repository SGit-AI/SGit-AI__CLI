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
from sgit_ai.schemas.cache.Schema__Cache_Tombstones     import Schema__Cache_Tombstone, Schema__Cache_Tombstones
from sgit_ai.safe_types.Enum__Cache_Kind                import Enum__Cache_Kind
from sgit_ai.safe_types.Enum__Cache_Mutability          import Enum__Cache_Mutability

CACHE_ID_PREFIX       = 'cch-pid-'
CACHE_VALUE_THRESHOLD = 4 * 1024              # contract Q2 — steer >4 KB to a pointer
CACHE_VALUE_HARD_CAP  = 1024 * 1024           # a value object must fit the server's
                                              # batch body budget (4 MB, Lambda ~6 MB);
                                              # bigger content is what pointers are for
TOMBSTONES_FILE       = 'cache_tombstones.json'


class Vault__Cache_Blob_Missing_Error(FileNotFoundError):
    """A cache rebuild needed a blob that is not in the local object store —
    the normal state of a sparse clone. Callers skip the object (push/repair)
    or explain the situation (CLI), rather than crashing or aborting the run."""


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

    def rebuild_for_path(self, kind: Enum__Cache_Kind, path: str, commit_id: str,
                         tree_id: str, flat: dict, obj_store, sub_tree, read_key: bytes,
                         mutability: Enum__Cache_Mutability = Enum__Cache_Mutability.SNW,
                         blob_fetcher: callable = None):
        """Rebuild a cache object for `path` from the given head, or None if the
        path no longer exists there — or can no longer be represented (a value
        whose content grew past CACHE_VALUE_HARD_CAP cannot fit a batch write,
        so it is treated as gone; the user re-declares it with --pointer).

        Single source of truth shared by the push reconcile and `cache repair`,
        so the two can never drift in what a "current" cache object looks like.

        `blob_fetcher(blob_id) -> ciphertext|None` covers sparse clones whose
        object store lacks the blob; without one (or when it returns None), a
        missing blob raises Vault__Cache_Blob_Missing_Error, which callers
        treat as "skip this object", never as "delete it".
        """
        from sgit_ai.safe_types.Enum__Cache_Target_Kind import Enum__Cache_Target_Kind

        if kind == Enum__Cache_Kind.VALUE:
            entry = flat.get(path)
            if not entry or not entry.get('blob_id'):
                return None
            try:
                ciphertext = obj_store.load(entry['blob_id'])
            except FileNotFoundError:
                ciphertext = blob_fetcher(entry['blob_id']) if blob_fetcher else None
            if not ciphertext:
                raise Vault__Cache_Blob_Missing_Error(
                    f"blob {entry['blob_id']} for '{path}' is not available locally")
            plaintext = self.crypto.decrypt(read_key, ciphertext)
            if len(plaintext) > CACHE_VALUE_HARD_CAP:
                return None
            return self.build_value(path         = path,
                                    content      = plaintext,
                                    commit_id    = commit_id,
                                    content_type = entry.get('content_type', '') or '',
                                    content_hash = entry.get('content_hash', '') or '',
                                    mutability   = mutability)

        target_kind, target_id = sub_tree.resolve_path_target(tree_id, path, read_key)
        if not target_id:
            return None
        entry = flat.get(path) or {}
        return self.build_pointer(path         = path,
                                  target_id    = target_id,
                                  target_kind  = (Enum__Cache_Target_Kind.BLOB
                                                  if target_kind == 'blob'
                                                  else Enum__Cache_Target_Kind.TREE),
                                  commit_id    = commit_id,
                                  content_type = entry.get('content_type', '') or '',
                                  size         = entry.get('size', 0) or 0,
                                  content_hash = (entry.get('content_hash') or None
                                                  if target_kind == 'blob' else None),
                                  mutability   = mutability)

    # --- encrypt / decrypt -------------------------------------------------

    def encrypt_object(self, obj, read_key: bytes) -> bytes:
        """Random-IV AES-GCM over the object's JSON (contract §5)."""
        return self.crypto.encrypt(read_key, json.dumps(obj.json()).encode())

    def decrypt_object(self, ciphertext: bytes, read_key: bytes, kind: Enum__Cache_Kind):
        data   = json.loads(self.crypto.decrypt(read_key, ciphertext))
        schema = Schema__Cache_Value if kind == Enum__Cache_Kind.VALUE else Schema__Cache_Pointer
        return schema.from_json(data)

    def classify_ciphertext(self, ciphertext: bytes, read_key: bytes,
                            kind: Enum__Cache_Kind) -> tuple:
        """(object_or_None, status) with status in 'ok'|'undecryptable'|'unparseable'.

        The distinction matters to repair: 'undecryptable' is garbage or a
        foreign key — safe to clean up everywhere. 'unparseable' DECRYPTED under
        our read_key (AES-GCM authenticated, so it was written by a key holder)
        but does not fit this build's schema — most likely a newer client's
        format. Deleting those from the server would destroy another client's
        valid data, so callers must skip them instead (review 08/14 M2).
        """
        try:
            plaintext = self.crypto.decrypt(read_key, ciphertext)
        except Exception:
            return None, 'undecryptable'
        try:
            data   = json.loads(plaintext)
            schema = Schema__Cache_Value if kind == Enum__Cache_Kind.VALUE else Schema__Cache_Pointer
            return schema.from_json(data), 'ok'
        except Exception:
            return None, 'unparseable'

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
        """Load and decrypt a cache object, or None if it is absent OR unreadable.

        Unreadable is deliberately not an error: cache objects are derived and
        non-authoritative, so a corrupt / foreign-key / truncated object is
        operationally the same as a missing one — both are `cache repair`'s job.
        Raising here would let one bad object abort a whole push reconcile.
        """
        path = self.storage.cache_path(directory, self.kind_dir_name(kind), cache_id)
        if not os.path.isfile(path):
            return None
        try:
            with open(path, 'rb') as f:
                return self.decrypt_object(f.read(), read_key, kind)
        except Exception:
            return None

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

    # --- tombstones (removal intent — survives until the remote copy is gone) --

    def tombstones_path(self, directory: str) -> str:
        return os.path.join(self.storage.local_dir(directory), TOMBSTONES_FILE)

    def load_tombstones(self, directory: str) -> Schema__Cache_Tombstones:
        path = self.tombstones_path(directory)
        if not os.path.isfile(path):
            return Schema__Cache_Tombstones()
        try:
            with open(path, 'r') as f:
                return Schema__Cache_Tombstones.from_json(json.load(f))
        except Exception:
            return Schema__Cache_Tombstones()

    def save_tombstones(self, directory: str, tombstones: Schema__Cache_Tombstones) -> None:
        path = self.tombstones_path(directory)
        if not tombstones.removed:
            if os.path.isfile(path):
                os.remove(path)
            return
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w') as f:
            json.dump(tombstones.json(), f)

    def add_tombstone(self, directory: str, kind: Enum__Cache_Kind,
                      cache_id: str, path: str) -> None:
        tombstones = self.load_tombstones(directory)
        if any(t.kind == kind and str(t.cache_id) == cache_id for t in tombstones.removed):
            return
        tombstones.removed.append(Schema__Cache_Tombstone(kind=kind, cache_id=cache_id,
                                                          path=path))
        self.save_tombstones(directory, tombstones)

    def tombstoned_ids(self, directory: str) -> set:
        """{(kind, cache_id)} the user has removed but the server may still hold."""
        return set((t.kind, str(t.cache_id))
                   for t in self.load_tombstones(directory).removed)

    def clear_tombstones(self, directory: str, ids: set) -> None:
        tombstones = self.load_tombstones(directory)
        keep       = [t for t in tombstones.removed
                      if (t.kind, str(t.cache_id)) not in ids]
        tombstones.removed.clear()
        tombstones.removed.extend(keep)
        self.save_tombstones(directory, tombstones)

    # --- D4: one object per path -------------------------------------------

    def resolve_duplicates(self, loaded: list, flat: dict, head_commit: str) -> list:
        """Given [(kind, cache_id, object_or_None)], return the [(kind, cache_id,
        path)] to DROP so each path keeps exactly one object (D4).

        Keep preference, in order: an object already fresh against the head; the
        kind natural to the target (pointer for a folder, value for a file); the
        snw mutability (the only one the CLI can declare — keeping muw here would
        strand local fast-path readers, which probe snw); stable id order last.
        Shared by the push reconcile and `cache repair` so cross-client duplicate
        declarations converge no matter which command sees them first.
        """
        by_path = {}
        for kind, cache_id, obj in loaded:
            if obj is None:
                continue
            by_path.setdefault(str(obj.path), []).append((kind, cache_id, obj))

        drop = []
        for path, group in by_path.items():
            if len(group) < 2:
                continue
            natural = (Enum__Cache_Kind.VALUE if path in flat else Enum__Cache_Kind.POINTER)
            snw_tag = f'-{Enum__Cache_Mutability.SNW.value}-'
            keep    = min(group, key=lambda g: (0 if str(g[2].commit_id) == head_commit else 1,
                                                0 if g[0] == natural else 1,
                                                0 if snw_tag in g[1] else 1,
                                                g[1]))
            for kind, cache_id, _ in group:
                if (kind, cache_id) != (keep[0], keep[1]):
                    drop.append((kind, cache_id, path))
        return drop
