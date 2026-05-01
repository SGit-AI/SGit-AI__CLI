"""M7 closer — write_file blob is encrypted on disk.

Mutation M7: replace `crypto.encrypt(read_key, file_content)` with `file_content`
(identity — no encryption).  This test opens the raw blob file in bare/data/ and
asserts the plaintext is NOT present, catching an encryption-skip regression.
"""
import os

from sgit_ai.api.Vault__API__In_Memory  import Vault__API__In_Memory
from sgit_ai.crypto.Vault__Crypto       import Vault__Crypto
from sgit_ai.sync.Vault__Sync           import Vault__Sync
from tests.unit.sync.vault_test_env     import Vault__Test_Env


KNOWN_PLAINTEXT = b'super secret content that must never appear in the blob store'


class Test_Vault__Sync__Write_File__Encryption:
    """Assert that blobs written by write_file are encrypted (not stored as plaintext)."""

    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_single_vault(files={'seed.txt': 'seed'})

    def setup_method(self):
        self.env       = self._env.restore()
        self.sync      = self.env.sync
        self.directory = self.env.vault_dir

    def teardown_method(self):
        self.env.cleanup()

    def test_write_file_blob_is_not_plaintext(self):
        """The raw blob on disk must not contain the plaintext bytes (M7 closer)."""
        result = self.sync.write_file(self.directory, 'secret.txt', KNOWN_PLAINTEXT)
        blob_id = result['blob_id']
        assert blob_id.startswith('obj-cas-imm-'), f'Unexpected blob_id: {blob_id!r}'

        blob_path = os.path.join(self.directory, '.sg_vault', 'bare', 'data', blob_id)
        assert os.path.isfile(blob_path), f'Blob not found on disk at: {blob_path}'

        with open(blob_path, 'rb') as fh:
            raw_bytes = fh.read()

        # Core assertion: plaintext must NOT appear verbatim in the stored blob.
        assert KNOWN_PLAINTEXT not in raw_bytes, (
            'ENCRYPTION BYPASS DETECTED: plaintext found verbatim in bare/data/ blob. '
            f'blob_id={blob_id}'
        )

    def test_write_file_blob_is_longer_than_plaintext(self):
        """AES-256-GCM adds at least 12 (IV) + 16 (tag) bytes over the plaintext."""
        plaintext = b'measure me'
        result    = self.sync.write_file(self.directory, 'measure.txt', plaintext)
        blob_id   = result['blob_id']

        blob_path = os.path.join(self.directory, '.sg_vault', 'bare', 'data', blob_id)
        with open(blob_path, 'rb') as fh:
            raw_bytes = fh.read()

        min_overhead = 12 + 16  # GCM IV + GCM tag
        assert len(raw_bytes) >= len(plaintext) + min_overhead, (
            f'Blob size {len(raw_bytes)} is too small for AES-256-GCM output '
            f'(plaintext={len(plaintext)}, min_overhead={min_overhead})'
        )

    def test_write_file_blob_decrypts_to_plaintext(self):
        """The blob must be decryptable back to the original plaintext using the vault key."""
        plaintext = b'round-trip verification for M7'
        result    = self.sync.write_file(self.directory, 'roundtrip.txt', plaintext)
        blob_id   = result['blob_id']

        blob_path = os.path.join(self.directory, '.sg_vault', 'bare', 'data', blob_id)
        with open(blob_path, 'rb') as fh:
            raw_bytes = fh.read()

        # Derive the same read_key the sync used
        crypto    = self.env.crypto
        vault_key = self.env.vault_key
        keys      = crypto.derive_keys_from_vault_key(vault_key)
        read_key  = keys['read_key_bytes']

        decrypted = crypto.decrypt(read_key, raw_bytes)
        assert decrypted == plaintext, (
            'Decrypted blob does not match original plaintext — crypto round-trip broken.'
        )

    def test_write_file_different_content_different_blob(self):
        """Two distinct plaintexts must produce two distinct blobs (sanity check)."""
        r1 = self.sync.write_file(self.directory, 'f1.txt', b'alpha content')
        r2 = self.sync.write_file(self.directory, 'f2.txt', b'beta content')
        assert r1['blob_id'] != r2['blob_id'], (
            'Different plaintext produced the same blob_id — something is wrong.'
        )
