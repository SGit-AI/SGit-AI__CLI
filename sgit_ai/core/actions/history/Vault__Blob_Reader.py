"""Vault__Blob_Reader — a flat entry's plaintext, the one place renames, blame, grep, the
pickaxe and the pruned diff read file content (design__04 §5.3).

The local store first (a pack-store clone reads by offset); else, when a remote is
configured and not `offline`, the blob is fetched and kept only if it hashes to its
id (Vault__Verified_Write, as `sgit cat` does); else None, counted as missing. A
decryption error propagates: a wrong key fails loudly. Plaintext is memoised in
memory only (an LRU of `memo_bytes`), never on disk."""
from   collections                                     import OrderedDict
from   osbot_utils.type_safe.Type_Safe                 import Type_Safe
from   osbot_utils.type_safe.primitives.core.Safe_UInt import Safe_UInt
from   sgit_ai.crypto.Vault__Crypto                    import Vault__Crypto
from   sgit_ai.safe_types.Safe_Str__Vault_Id           import Safe_Str__Vault_Id
from   sgit_ai.safe_types.Safe_Str__Vault_Path         import Safe_Str__Vault_Path
from   sgit_ai.storage.Vault__Object_Store             import Vault__Object_Store

MEMO_BYTES = 64 * 1024 * 1024


class Vault__Blob_Reader(Type_Safe):
    crypto        : Vault__Crypto
    obj_store     : Vault__Object_Store
    read_key      : bytes
    vault_id      : Safe_Str__Vault_Id   = None
    sg_dir        : Safe_Str__Vault_Path = None
    api           : object = None                      # set only when the clone has a remote (the _on_demand_api rule)
    offline       : bool = False
    memo_bytes    : Safe_UInt = MEMO_BYTES
    blobs_read    : Safe_UInt
    blobs_fetched : Safe_UInt
    blobs_missing : Safe_UInt
    memo          : object = None                      # OrderedDict blob id -> plaintext
    memo_size     : Safe_UInt

    def content(self, entry: dict):
        """The plaintext of a flat entry, or None when its blob is neither local nor fetchable."""
        blob_id = str((entry or {}).get('blob_id') or '')
        if not blob_id:
            return None
        if self.memo is None:
            self.memo = OrderedDict()
        if blob_id in self.memo:
            self.memo.move_to_end(blob_id)
            return self.memo[blob_id]
        if not self.obj_store.exists(blob_id) and not self.fetch(blob_id, bool(entry.get('large'))):
            self.blobs_missing += 1
            return None
        plaintext = self.crypto.decrypt(self.read_key, self.obj_store.load(blob_id))
        self.blobs_read += 1
        self.remember(blob_id, plaintext)
        return plaintext

    def fetch(self, blob_id: str, large: bool = False) -> bool:
        if self.api is None or self.offline:
            return False
        file_id = f'bare/data/{blob_id}'
        try:
            data = self.api.read_large(str(self.vault_id), file_id) if large else self.api.read(str(self.vault_id), file_id)
        except Exception:                                                   # unreachable: counted as missing
            return False
        return self.save(file_id, data)

    def prefetch(self, entries: list) -> None:
        """One batch read for every listed blob that is not local (blame and grep call it
        before walking, so a sparse clone makes a few requests, not one per file)."""
        if self.api is None or self.offline:
            return
        missing = sorted({str(e['blob_id']) for e in entries if e and e.get('blob_id') and not e.get('large')
                          and not self.obj_store.exists(str(e['blob_id']))})
        if not missing:
            return
        try:
            found = self.api.batch_read(str(self.vault_id), [f'bare/data/{b}' for b in missing]) or {}
        except Exception:
            return
        for file_id, data in found.items():
            self.save(file_id, data)

    def save(self, file_id: str, data) -> bool:
        from sgit_ai.storage.Vault__Verified_Write import Vault__Verified_Write
        from sgit_ai.core.Vault__Errors           import Vault__Integrity_Error
        if not data:
            return False
        if Vault__Verified_Write(crypto=self.crypto).save(str(self.sg_dir), file_id, data,
                                                          read_key=self.read_key) == Vault__Verified_Write.REFUSED:
            raise Vault__Integrity_Error(f'integrity check refused vault data: {file_id} does not hash to its id; '
                                         f'the host served corrupt or substituted content')
        self.blobs_fetched += 1
        return True

    def remember(self, blob_id: str, plaintext: bytes) -> None:
        if len(plaintext) > int(self.memo_bytes):
            return
        self.memo[blob_id] = plaintext
        self.memo_size     = int(self.memo_size) + len(plaintext)
        while int(self.memo_size) > int(self.memo_bytes):
            _, dropped     = self.memo.popitem(last=False)
            self.memo_size = int(self.memo_size) - len(dropped)
