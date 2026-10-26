import os
import time
from osbot_utils.type_safe.Type_Safe                 import Type_Safe
from osbot_utils.type_safe.primitives.core.Safe_UInt import Safe_UInt
from sgit_ai.crypto.Vault__Crypto                import Vault__Crypto
from sgit_ai.safe_types.Safe_Str__Vault_Path     import Safe_Str__Vault_Path

BARE_DATA_DIR      = os.path.join('bare', 'data')
OBJ_CAS_IMM_PREFIX = 'obj-cas-imm-'


class Vault__Object_Collision_Error(Exception):
    """Two distinct ciphertexts hashed to the same object id (48-bit truncation).

    Object ids are sha256(ciphertext)[:12]. Under true content-addressing a
    pre-existing object at an id must hold byte-identical content; if it does
    not, the truncated hash has collided, and silently overwriting would lose
    data or return the wrong object. We fail loudly instead.
    """

    def __init__(self, object_id: str):
        super().__init__(
            f'object id collision at {object_id}: existing content differs from '
            f'the content being stored (48-bit id truncation). Refusing to overwrite.')


class Vault__Object_Missing_Error(FileNotFoundError):
    """An object id was required but is not in the local store.

    Subclasses FileNotFoundError so every existing absent-object handler
    (sparse clones, cache rebuilds, lineage skips) keeps working; the message
    names the OBJECT rather than an internal file path, so a failed operation
    diagnoses as a store problem, not a stray missing file (review finding B1).
    Constructed from a single message string — the workflow runner re-raises
    step errors as type(exc)(str(exc)).
    """

    def __init__(self, message: str):
        super().__init__(message)


class Vault__Object_Corrupt_Error(Vault__Object_Missing_Error):
    """An object read from a kept pack no longer hashes to its id (the pack file changed
    on disk). A missing object to every caller that fails soft; named for fsck."""


class Vault__Object_Store(Type_Safe):
    vault_path  : Safe_Str__Vault_Path = None
    crypto      : Vault__Crypto
    id_hex_len  : Safe_UInt            = Safe_UInt(12)     # 12 on a format-1 vault, 32 on format 2 (new objects only)
    pack_store  : object               = None              # Vault__Pack_Store when this clone keeps packs in place
    packs_probed: bool                 = False
    probed_at   : float                = 0.0               # when the probe found no table (re-probed after a second)

    def packs(self):
        """The kept-pack back-end (local/pack-store.sqlite present), opened once; None on
        an ordinary clone. Loose objects always come first: a clone's own new objects
        stay loose until pushed."""
        if not self.packs_probed or (self.pack_store is None and time.monotonic() - float(self.probed_at) > 1.0):
            self.packs_probed = True                            # a table created after the first probe (a clone in
            self.probed_at    = time.monotonic()                # progress) is seen on the next probe (F10)
            if self.vault_path:
                from sgit_ai.storage.Vault__Pack_Store import Vault__Pack_Store
                store = Vault__Pack_Store(vault_path=self.vault_path, crypto=self.crypto)
                self.pack_store = store.setup() if store.enabled() else None
        return self.pack_store

    def store(self, ciphertext: bytes) -> str:
        object_id = self._compute_id(ciphertext)
        path      = self.object_path(object_id)
        if os.path.isfile(path):
            with open(path, 'rb') as f:
                existing = f.read()
            if existing != ciphertext:
                raise Vault__Object_Collision_Error(object_id)
            return object_id                        # already stored, identical — idempotent
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'wb') as f:
            f.write(ciphertext)
        return object_id

    def store_raw(self, object_id: str, ciphertext: bytes) -> str:
        """Store a blob with a pre-determined object_id (used for change pack drain)."""
        path = self.object_path(object_id)
        if os.path.isfile(path):
            with open(path, 'rb') as f:
                existing = f.read()
            if existing != ciphertext:
                raise Vault__Object_Collision_Error(object_id)
            return object_id
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'wb') as f:
            f.write(ciphertext)
        return object_id

    def store_at(self, object_id: str, ciphertext: bytes, force: bool = False) -> str:
        # WHY: deliberately breaks the CAS invariant — used by vault move to re-encrypt in-place under a new key
        path = self.object_path(object_id)
        if not force and os.path.isfile(path):
            return object_id
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'wb') as f:
            f.write(ciphertext)
        return object_id

    def load(self, object_id: str) -> bytes:
        path = self.object_path(object_id)
        try:
            with open(path, 'rb') as f:
                return f.read()
        except FileNotFoundError:
            packs = self.packs()
            if packs is not None:
                return packs.load(object_id)                     # verified by content address on every read
            raise Vault__Object_Missing_Error(
                f'object {object_id} is not in the local store') from None

    def exists(self, object_id: str) -> bool:
        if os.path.isfile(self.object_path(object_id)):
            return True
        packs = self.packs()
        return packs is not None and packs.exists(object_id)

    def size_of(self, object_id: str) -> int:
        """The stored (ciphertext) size, loose or packed; 0 when absent."""
        path = self.object_path(object_id)
        if os.path.isfile(path):
            return os.path.getsize(path)
        packs = self.packs()
        return int((packs.size_of(object_id) if packs is not None else None) or 0)

    def object_path(self, object_id: str) -> str:
        return os.path.join(self.vault_path, BARE_DATA_DIR, object_id)

    def resolve_id(self, text: str) -> str:
        """Accept what `sgit history log` prints: the full id, the bare hex after
        obj-cas-imm- (12 or 32 chars), or a unique hex prefix of at least 4.
        Returns the full id of the one local object it names; anything else
        (no match, not hex) comes back unchanged so the caller reports it as
        before. Two or more matches raise ValueError naming them."""
        import re
        raw = str(text or '').strip()
        if not raw or self.exists(raw):
            return raw
        hex_part = raw[len(OBJ_CAS_IMM_PREFIX):] if raw.startswith(OBJ_CAS_IMM_PREFIX) else raw
        if not re.fullmatch(r'[0-9a-f]{4,32}', hex_part.lower()):
            return raw
        prefix  = OBJ_CAS_IMM_PREFIX + hex_part.lower()
        matches = [oid for oid in self.all_object_ids() if oid.startswith(prefix)]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            raise ValueError(f'{raw} is ambiguous: it matches {len(matches)} objects '
                             f'({", ".join(matches[:3])}{"…" if len(matches) > 3 else ""}); give more characters')
        return raw

    def all_object_ids(self) -> list[str]:
        data_dir = os.path.join(self.vault_path, BARE_DATA_DIR)
        loose    = set(f for f in os.listdir(data_dir) if f.startswith(OBJ_CAS_IMM_PREFIX)) if os.path.isdir(data_dir) else set()
        packs    = self.packs()
        if packs is not None:
            loose |= set(packs.all_object_ids())
        return sorted(loose)

    def loose_object_ids(self) -> list[str]:
        data_dir = os.path.join(self.vault_path, BARE_DATA_DIR)
        if not os.path.isdir(data_dir):
            return []
        return sorted(f for f in os.listdir(data_dir) if f.startswith(OBJ_CAS_IMM_PREFIX))

    def object_count(self) -> int:
        return len(self.all_object_ids())

    def total_size(self) -> int:
        total = 0
        for object_id in self.all_object_ids():
            total += self.size_of(object_id)
        return total

    def verify_integrity(self, object_id: str) -> bool:
        if not self.exists(object_id):
            return False
        try:
            ciphertext = self.load(object_id)
        except Vault__Object_Missing_Error:                              # a kept pack that changed on disk
            return False
        return self.crypto.object_id_matches(object_id, ciphertext)      # at the id's own width: mixed vaults verify

    def _compute_id(self, ciphertext: bytes) -> str:
        return self.crypto.compute_object_id(ciphertext, int(self.id_hex_len or 12))
