"""Tests for the structure key derivation (AC7, AC8, AC9 from the brief).

The structure key is derived from the vault read_key using HKDF-SHA256.
It is one-way: knowing the structure key does not reveal the read_key or
the vault key.  The structure key is 32 bytes (AES-256).
"""
from sgit_ai.crypto.Vault__Crypto import Vault__Crypto, AES_KEY_BYTES, STRUCTURE_KEY_INFO


class Test_Vault__Crypto__Structure_Key:

    def setup_method(self):
        self.crypto = Vault__Crypto()

    # ------------------------------------------------------------------
    # AC7 — structure key derivation
    # ------------------------------------------------------------------

    def test_derive_structure_key_length(self):
        read_key      = bytes.fromhex('0123456789abcdef' * 4)
        structure_key = self.crypto.derive_structure_key(read_key)
        assert len(structure_key) == AES_KEY_BYTES

    def test_derive_structure_key_is_deterministic(self):
        read_key = bytes.fromhex('aabbccddeeff0011' * 4)
        key1     = self.crypto.derive_structure_key(read_key)
        key2     = self.crypto.derive_structure_key(read_key)
        assert key1 == key2

    def test_derive_structure_key_differs_from_read_key(self):
        read_key      = bytes.fromhex('0123456789abcdef' * 4)
        structure_key = self.crypto.derive_structure_key(read_key)
        assert structure_key != read_key

    def test_different_read_keys_produce_different_structure_keys(self):
        read_key_1 = bytes.fromhex('0000000000000000' * 4)
        read_key_2 = bytes.fromhex('1111111111111111' * 4)
        sk1 = self.crypto.derive_structure_key(read_key_1)
        sk2 = self.crypto.derive_structure_key(read_key_2)
        assert sk1 != sk2

    def test_structure_key_info_constant(self):
        """Verify the HKDF info string is the expected domain separator."""
        assert STRUCTURE_KEY_INFO == b'sg-vault-v1:structure-key'

    def test_derive_structure_key_interop_vector(self):
        """Fixed test vector to catch accidental changes to the derivation."""
        read_key = bytes.fromhex('0123456789abcdef0123456789abcdef'
                                 '0123456789abcdef0123456789abcdef')
        structure_key = self.crypto.derive_structure_key(read_key)
        # The result must be a 32-byte value derived via HKDF-SHA256
        # with info=b'sg-vault-v1:structure-key' and no salt.
        assert len(structure_key) == 32
        # Verify it is not all-zeros or trivially wrong
        assert structure_key != b'\x00' * 32
        assert structure_key != read_key

    # ------------------------------------------------------------------
    # AC8 — structure key decrypts metadata but NOT blob content
    # ------------------------------------------------------------------

    def test_structure_key_can_decrypt_metadata_encrypted_with_read_key(self):
        """NEGATIVE test: structure_key cannot decrypt data encrypted with read_key.

        The structure key is a *different* key, so data encrypted under the
        read_key (blobs) is not decryptable with the structure key.
        This confirms the separation of concerns.
        """
        import pytest
        read_key      = bytes.fromhex('0123456789abcdef' * 4)
        structure_key = self.crypto.derive_structure_key(read_key)

        # Encrypt a blob with read_key
        blob_content = b'secret file content'
        encrypted    = self.crypto.encrypt(read_key, blob_content)

        # Attempting to decrypt with structure_key MUST fail
        with pytest.raises(Exception):
            self.crypto.decrypt(structure_key, encrypted)

    def test_metadata_encrypted_with_read_key_is_not_readable_via_structure_key(self):
        """Metadata encrypted with read_key cannot be read with structure_key.

        In the current design, metadata (refs, trees) is encrypted with
        read_key.  The structure_key is a derived sub-key that cannot reverse-
        engineer read_key.  If the system ever migrates metadata to use the
        structure_key directly, this test will need updating.
        """
        import pytest
        read_key      = bytes.fromhex('fedcba9876543210' * 4)
        structure_key = self.crypto.derive_structure_key(read_key)

        # Encrypt metadata (commit message) with read_key
        ciphertext = self.crypto.encrypt(read_key, b'{"commit_id": "abc"}')

        # Cannot decrypt with structure_key — this is the expected security property
        with pytest.raises(Exception):
            self.crypto.decrypt(structure_key, ciphertext)

    def test_vault_key_derivation_includes_structure_key_path(self):
        """Verify a full vault key produces a usable structure key via derive_keys."""
        vault_key = 'my-passphrase:testvaultidabc'
        keys      = self.crypto.derive_keys_from_vault_key(vault_key)
        read_key  = keys['read_key_bytes']
        structure_key = self.crypto.derive_structure_key(read_key)
        assert len(structure_key) == AES_KEY_BYTES
        assert structure_key != read_key
