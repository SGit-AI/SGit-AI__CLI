"""Vault__Verified_Write — id-verify fetched objects before they touch disk.

SP-1 / invariant I7: every content-addressed object (obj-cas-imm-*) can be
checked with no key and no trust in the host — its id IS sha256(ciphertext).
A reader must never write an object it has not verified, and a single bad
object must fail soft (skipped, counted) rather than abort the run. All
download paths (clone, fetch, pull, mirror) write through this class; the
write path is also contained by Vault__Path_Guard, since the file_id names
the on-disk location.
"""
import os
from   osbot_utils.type_safe.Type_Safe      import Type_Safe
from   sgit_ai.crypto.Vault__Crypto         import Vault__Crypto
from   sgit_ai.storage.Vault__Path_Guard    import Vault__Path_Guard, Vault__Unsafe_Path_Error


class Vault__Verified_Write(Type_Safe):
    crypto : Vault__Crypto = None

    def is_content_addressed(self, file_id: str) -> bool:
        object_name = file_id.rsplit('/', 1)[-1]
        return object_name.startswith('obj-cas-imm-')

    def verify(self, file_id: str, data: bytes, read_key: bytes = None) -> bool:
        """True when data hashes to the id it claims — or when the id is not
        content-addressed (refs/indexes/keys carry no self-verifying name).

        Post-move fallback: `sgit vault move` re-encrypts every object in place
        under the new key while KEEPING the old ids (store_at deliberately
        breaks the CAS invariant), so in a moved vault sha256(ciphertext)[:12]
        legitimately differs from the id. When the caller holds the read key, a
        mismatched object is accepted iff it still AES-GCM-authenticates under
        that key — a host without the key cannot forge that. A keyless caller
        (mirror) gets the strict content-address check only.
        """
        if not self.is_content_addressed(file_id):
            return True
        if self.crypto is None:
            self.crypto = Vault__Crypto()
        object_name = file_id.rsplit('/', 1)[-1]
        if self.crypto.compute_object_id(data or b'') == object_name:
            return True
        if read_key:
            try:
                self.crypto.decrypt(read_key, data)
                return True
            except Exception:
                return False
        return False

    def save(self, base_dir: str, file_id: str, data: bytes, read_key: bytes = None) -> bool:
        """Verify-then-write. Returns False — writing NOTHING — when the bytes
        do not hash to a content-addressed id or the path escapes base_dir."""
        if not self.verify(file_id, data, read_key=read_key):
            return False
        try:
            local_path = Vault__Path_Guard().safe_join(base_dir, file_id)
        except Vault__Unsafe_Path_Error:
            return False
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        with open(local_path, 'wb') as f:
            f.write(data)
        return True
