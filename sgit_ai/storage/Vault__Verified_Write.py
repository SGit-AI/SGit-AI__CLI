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

    # verdicts
    VERIFIED = 'verified'        # content-address matched, or not content-addressed
    REFUSED  = 'refused'         # not written

    def classify(self, file_id: str, data: bytes, read_key: bytes = None) -> str:
        """VERIFIED or REFUSED, without writing. Strict: the content address is
        the only thing that decides, for keyed and keyless callers alike.

        There is deliberately NO "but it decrypts under my key" fallback. One
        existed while `sgit vault move` re-encrypted objects in place keeping
        their old ids — which left no object in a moved vault hashing to its own
        id, so the check had to be relaxed for those vaults. That relaxation was
        the hole: two AUTHENTIC objects swapped between their ids both decrypt,
        so a hostile host could substitute content undetectably (review finding
        A1). Move now rewrites the ids, so a moved vault verifies strictly like
        any other and the fallback has nothing left to excuse.

        A vault moved by an older sgit (before move rewrote ids) still carries
        the old un-addressed ids; such objects are REFUSED, and the caller
        reports the remedy (re-run `sgit vault move` to normalise the store).
        """
        if not self.is_content_addressed(file_id):
            return self.VERIFIED
        if self.crypto is None:
            self.crypto = Vault__Crypto()
        object_name = file_id.rsplit('/', 1)[-1]
        if self.crypto.compute_object_id(data or b'') == object_name:
            return self.VERIFIED
        return self.REFUSED

    def verify(self, file_id: str, data: bytes, read_key: bytes = None) -> bool:
        """True when the object may be written."""
        return self.classify(file_id, data, read_key=read_key) != self.REFUSED

    def save(self, base_dir: str, file_id: str, data: bytes, read_key: bytes = None) -> str:
        """Verify-then-write. Returns VERIFIED when written, REFUSED (writing
        NOTHING) when the bytes do not match a content-addressed id or the path
        escapes base_dir."""
        verdict = self.classify(file_id, data, read_key=read_key)
        if verdict == self.REFUSED:
            return self.REFUSED
        try:
            local_path = Vault__Path_Guard().safe_join(base_dir, file_id)
        except Vault__Unsafe_Path_Error:
            return self.REFUSED
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        with open(local_path, 'wb') as f:
            f.write(data)
        return verdict
