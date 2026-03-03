import pytest
from sg_send_cli.crypto.Vault__Crypto import Vault__Crypto, PBKDF2_ITERATIONS, AES_KEY_BYTES, GCM_IV_BYTES


class Test_Vault__Crypto:

    def setup_method(self):
        self.crypto = Vault__Crypto()

    # --- PBKDF2 key derivation ---

    def test_derive_key_from_passphrase__deterministic(self):
        passphrase = b'test-passphrase-123'
        salt       = bytes.fromhex('000102030405060708090a0b0c0d0e0f')
        key        = self.crypto.derive_key_from_passphrase(passphrase, salt)
        assert key.hex() == 'b30143c284de844e974e6bdbbb7fabcc61166ac0702370f5418f11ef6f2b9282'

    def test_derive_key_from_passphrase__length(self):
        key = self.crypto.derive_key_from_passphrase(b'pass', self.crypto.generate_salt())
        assert len(key) == AES_KEY_BYTES

    def test_derive_key_from_passphrase__different_salt_different_key(self):
        passphrase = b'same-passphrase'
        key1 = self.crypto.derive_key_from_passphrase(passphrase, b'\x00' * 16)
        key2 = self.crypto.derive_key_from_passphrase(passphrase, b'\x01' * 16)
        assert key1 != key2

    # --- AES-256-GCM encrypt/decrypt ---

    def test_encrypt_decrypt_round_trip(self):
        key       = bytes.fromhex('0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef')
        plaintext = b'Hello, SG/Send vault!'
        encrypted = self.crypto.encrypt(key, plaintext)
        decrypted = self.crypto.decrypt(key, encrypted)
        assert decrypted == plaintext

    def test_encrypt__interop_vector(self):
        key       = bytes.fromhex('0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef')
        iv        = bytes.fromhex('000102030405060708090a0b')
        plaintext = b'Hello, SG/Send vault!'
        encrypted = self.crypto.encrypt(key, plaintext, iv=iv)
        expected  = '000102030405060708090a0bc961f67169cb025bdde49a7619db82b629b978cafa29fa540d74c6db9d190eee1c34a49ee0'
        assert encrypted.hex() == expected

    def test_decrypt__interop_vector(self):
        key  = bytes.fromhex('0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef')
        data = bytes.fromhex('000102030405060708090a0bc961f67169cb025bdde49a7619db82b629b978cafa29fa540d74c6db9d190eee1c34a49ee0')
        decrypted = self.crypto.decrypt(key, data)
        assert decrypted == b'Hello, SG/Send vault!'

    def test_encrypt__iv_prepended(self):
        key       = bytes.fromhex('0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef')
        plaintext = b'test'
        encrypted = self.crypto.encrypt(key, plaintext)
        assert len(encrypted) > GCM_IV_BYTES

    def test_decrypt__wrong_key_fails(self):
        key1 = bytes.fromhex('0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef')
        key2 = bytes.fromhex('fedcba9876543210fedcba9876543210fedcba9876543210fedcba9876543210')
        encrypted = self.crypto.encrypt(key1, b'secret data')
        with pytest.raises(Exception):
            self.crypto.decrypt(key2, encrypted)

    def test_encrypt__empty_plaintext(self):
        key       = bytes.fromhex('0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef')
        encrypted = self.crypto.encrypt(key, b'')
        decrypted = self.crypto.decrypt(key, encrypted)
        assert decrypted == b''

    def test_encrypt__large_plaintext(self):
        key       = bytes.fromhex('0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef')
        plaintext = b'A' * 1024 * 1024
        encrypted = self.crypto.encrypt(key, plaintext)
        decrypted = self.crypto.decrypt(key, encrypted)
        assert decrypted == plaintext

    # --- HKDF file key derivation ---

    def test_derive_file_key__interop_vector(self):
        vault_key    = bytes.fromhex('abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789')
        file_context = b'documents/readme.txt'
        file_key     = self.crypto.derive_file_key(vault_key, file_context)
        assert file_key.hex() == 'ca8412924aa22f624a2703a90b880bad6ef661bb5b83c81ce1b1019b4ddf49c1'

    def test_derive_file_key__length(self):
        vault_key = bytes(32)
        file_key  = self.crypto.derive_file_key(vault_key, b'test.txt')
        assert len(file_key) == AES_KEY_BYTES

    def test_derive_file_key__different_context_different_key(self):
        vault_key = bytes(32)
        key1 = self.crypto.derive_file_key(vault_key, b'file1.txt')
        key2 = self.crypto.derive_file_key(vault_key, b'file2.txt')
        assert key1 != key2

    # --- SHA-256 hashing ---

    def test_hash_data__interop_vector(self):
        data   = b'test file content for hashing'
        digest = self.crypto.hash_data(data)
        assert digest == '034527873967b8661d44a2bc0701690bb761c30abbd3cba8502df40f6dc7ccf3'

    def test_hash_data__empty(self):
        digest = self.crypto.hash_data(b'')
        assert digest == 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'

    def test_hash_data__length(self):
        digest = self.crypto.hash_data(b'anything')
        assert len(digest) == 64

    # --- Random generation ---

    def test_generate_salt__length(self):
        salt = self.crypto.generate_salt()
        assert len(salt) == 16

    def test_generate_salt__unique(self):
        salt1 = self.crypto.generate_salt()
        salt2 = self.crypto.generate_salt()
        assert salt1 != salt2

    def test_generate_iv__length(self):
        iv = self.crypto.generate_iv()
        assert len(iv) == GCM_IV_BYTES

    def test_generate_iv__unique(self):
        iv1 = self.crypto.generate_iv()
        iv2 = self.crypto.generate_iv()
        assert iv1 != iv2

    # --- Full pipeline test ---

    def test_full_encrypt_decrypt_pipeline(self):
        passphrase   = b'my-vault-passphrase'
        salt         = self.crypto.generate_salt()
        vault_key    = self.crypto.derive_key_from_passphrase(passphrase, salt)
        file_context = b'notes/secret.txt'
        file_key     = self.crypto.derive_file_key(vault_key, file_context)
        plaintext    = b'This is my secret note content.'
        encrypted    = self.crypto.encrypt(file_key, plaintext)
        decrypted    = self.crypto.decrypt(file_key, encrypted)
        assert decrypted == plaintext
        assert self.crypto.hash_data(decrypted) == self.crypto.hash_data(plaintext)
