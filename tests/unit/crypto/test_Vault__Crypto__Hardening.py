import pytest
from sg_send_cli.crypto.Vault__Crypto import Vault__Crypto, GCM_IV_BYTES, GCM_TAG_BYTES, AES_KEY_BYTES, PBKDF2_ITERATIONS


class Test_Vault__Crypto__Tampering:

    def setup_method(self):
        self.crypto = Vault__Crypto()
        self.key    = bytes.fromhex('0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef')

    def test_decrypt__corrupted_iv_fails(self):
        encrypted = self.crypto.encrypt(self.key, b'secret data')
        corrupted = bytes([encrypted[0] ^ 0xFF]) + encrypted[1:]
        with pytest.raises(Exception):
            self.crypto.decrypt(self.key, corrupted)

    def test_decrypt__truncated_ciphertext_fails(self):
        encrypted = self.crypto.encrypt(self.key, b'secret data')
        truncated = encrypted[:GCM_IV_BYTES + 5]
        with pytest.raises(Exception):
            self.crypto.decrypt(self.key, truncated)

    def test_decrypt__modified_tag_fails(self):
        encrypted  = self.crypto.encrypt(self.key, b'secret data')
        as_list    = bytearray(encrypted)
        as_list[-1] ^= 0xFF
        with pytest.raises(Exception):
            self.crypto.decrypt(self.key, bytes(as_list))

    def test_decrypt__modified_ciphertext_body_fails(self):
        encrypted = self.crypto.encrypt(self.key, b'secret data')
        middle    = GCM_IV_BYTES + 2
        corrupted = encrypted[:middle] + bytes([encrypted[middle] ^ 0xFF]) + encrypted[middle + 1:]
        with pytest.raises(Exception):
            self.crypto.decrypt(self.key, corrupted)

    def test_decrypt__empty_data_fails(self):
        with pytest.raises(Exception):
            self.crypto.decrypt(self.key, b'')

    def test_decrypt__iv_only_no_ciphertext_fails(self):
        with pytest.raises(Exception):
            self.crypto.decrypt(self.key, b'\x00' * GCM_IV_BYTES)

    def test_encrypt__different_iv_per_call(self):
        encrypted1 = self.crypto.encrypt(self.key, b'same plaintext')
        encrypted2 = self.crypto.encrypt(self.key, b'same plaintext')
        iv1 = encrypted1[:GCM_IV_BYTES]
        iv2 = encrypted2[:GCM_IV_BYTES]
        assert iv1 != iv2

    def test_encrypt__deterministic_with_same_iv(self):
        iv = b'\x00' * GCM_IV_BYTES
        encrypted1 = self.crypto.encrypt(self.key, b'same', iv=iv)
        encrypted2 = self.crypto.encrypt(self.key, b'same', iv=iv)
        assert encrypted1 == encrypted2

    def test_ciphertext_length__includes_iv_and_tag(self):
        plaintext = b'hello'
        encrypted = self.crypto.encrypt(self.key, plaintext)
        expected  = GCM_IV_BYTES + len(plaintext) + GCM_TAG_BYTES
        assert len(encrypted) == expected


class Test_Vault__Crypto__PBKDF2_Edge_Cases:

    def setup_method(self):
        self.crypto = Vault__Crypto()

    def test_pbkdf2_iterations_constant(self):
        assert PBKDF2_ITERATIONS == 600_000

    def test_aes_key_bytes_constant(self):
        assert AES_KEY_BYTES == 32

    def test_pbkdf2__empty_passphrase(self):
        key = self.crypto.derive_key_from_passphrase(b'', b'some-salt-value1')
        assert len(key) == AES_KEY_BYTES
        assert key != b'\x00' * AES_KEY_BYTES

    def test_pbkdf2__very_long_passphrase(self):
        passphrase = b'A' * 10000
        key = self.crypto.derive_key_from_passphrase(passphrase, b'some-salt-value1')
        assert len(key) == AES_KEY_BYTES

    def test_pbkdf2__unicode_passphrase(self):
        key = self.crypto.derive_key_from_passphrase('café résumé'.encode('utf-8'), b'some-salt-value1')
        assert len(key) == AES_KEY_BYTES

    def test_pbkdf2__single_byte_salt(self):
        key = self.crypto.derive_key_from_passphrase(b'pass', b'\x00')
        assert len(key) == AES_KEY_BYTES


class Test_Vault__Crypto__HKDF_Edge_Cases:

    def setup_method(self):
        self.crypto = Vault__Crypto()

    def test_hkdf__empty_context(self):
        vault_key = bytes(32)
        file_key  = self.crypto.derive_file_key(vault_key, b'')
        assert len(file_key) == AES_KEY_BYTES

    def test_hkdf__very_long_context(self):
        vault_key = bytes(32)
        file_key  = self.crypto.derive_file_key(vault_key, b'A' * 10000)
        assert len(file_key) == AES_KEY_BYTES

    def test_hkdf__binary_context(self):
        vault_key = bytes(32)
        file_key  = self.crypto.derive_file_key(vault_key, bytes(range(256)))
        assert len(file_key) == AES_KEY_BYTES

    def test_hkdf__same_key_different_from_raw(self):
        vault_key = bytes(32)
        file_key  = self.crypto.derive_file_key(vault_key, b'test')
        assert file_key != vault_key
