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
    VERIFIED      = 'verified'        # content-address matched, or not content-addressed
    AUTHENTICATED = 'authenticated'   # CAS MISMATCH, but decrypts under the read key (fallback)
    REFUSED       = 'refused'         # not written

    def classify(self, file_id: str, data: bytes, read_key: bytes = None) -> str:
        """One of VERIFIED / AUTHENTICATED / REFUSED, without writing.

        The AUTHENTICATED verdict is the review's A1 concern made visible: the
        object's bytes do NOT hash to its content address, but they decrypt
        under the read key, so the fallback would accept them. That is expected
        ONLY for a vault re-keyed in place by `sgit vault move` (which keeps old
        ids); on any other vault it means the host served substituted objects,
        and the caller MUST surface it. A keyless caller passes read_key=None
        and never gets AUTHENTICATED — only VERIFIED or REFUSED (mirror, SP-3).
        """
        if not self.is_content_addressed(file_id):
            return self.VERIFIED
        if self.crypto is None:
            self.crypto = Vault__Crypto()
        object_name = file_id.rsplit('/', 1)[-1]
        if self.crypto.compute_object_id(data or b'') == object_name:
            return self.VERIFIED
        if read_key:
            try:
                self.crypto.decrypt(read_key, data)
                return self.AUTHENTICATED
            except Exception:
                return self.REFUSED
        return self.REFUSED

    def verify(self, file_id: str, data: bytes, read_key: bytes = None) -> bool:
        """True when the object may be written (VERIFIED or AUTHENTICATED)."""
        return self.classify(file_id, data, read_key=read_key) != self.REFUSED

    def save(self, base_dir: str, file_id: str, data: bytes, read_key: bytes = None) -> str:
        """Verify-then-write. Returns the verdict: VERIFIED / AUTHENTICATED when
        written, REFUSED (writing NOTHING) when the bytes do not match a
        content-addressed id and do not authenticate, or the path escapes
        base_dir. Truthy for callers that only care whether it was written."""
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
