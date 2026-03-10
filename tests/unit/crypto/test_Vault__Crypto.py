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


class Test_Vault__Crypto__Vault_Key_Derivation:
    """Cross-language test vectors from the deterministic vault pointer spec.
    These vectors MUST match the JavaScript SGVaultCrypto implementation."""

    def setup_method(self):
        self.crypto = Vault__Crypto()

    # --- parse_vault_key ---

    def test_parse_vault_key__simple(self):
        passphrase, vault_id = self.crypto.parse_vault_key('my-secret-passphrase:a1b2c3d4')
        assert passphrase == 'my-secret-passphrase'
        assert vault_id   == 'a1b2c3d4'

    def test_parse_vault_key__passphrase_with_colons(self):
        passphrase, vault_id = self.crypto.parse_vault_key('pass:with:colons:deadbeef')
        assert passphrase == 'pass:with:colons'
        assert vault_id   == 'deadbeef'

    def test_parse_vault_key__invalid_no_colon(self):
        with pytest.raises(ValueError):
            self.crypto.parse_vault_key('nocolonhere')

    def test_parse_vault_key__invalid_empty_passphrase(self):
        with pytest.raises(ValueError):
            self.crypto.parse_vault_key(':a1b2c3d4')

    def test_parse_vault_key__invalid_empty_vault_id(self):
        with pytest.raises(ValueError):
            self.crypto.parse_vault_key('passphrase:')

    # --- Cross-language test vector 1 ---

    def test_vector_1__read_key(self):
        read_key = self.crypto.derive_read_key('my-secret-passphrase', 'a1b2c3d4')
        assert read_key.hex() == 'a9cbcf15b4719384a732594405f138a2a42895fe56710dcfbd1324369f735124'

    def test_vector_1__write_key(self):
        write_key = self.crypto.derive_write_key('my-secret-passphrase', 'a1b2c3d4')
        assert write_key.hex() == '3181d6650958b51fd00f913f6290eca22e6b09da661c8e831fc89fe659df378e'

    def test_vector_1__tree_file_id(self):
        read_key     = bytes.fromhex('a9cbcf15b4719384a732594405f138a2a42895fe56710dcfbd1324369f735124')
        tree_file_id = self.crypto.derive_tree_file_id(read_key, 'a1b2c3d4')
        assert tree_file_id == '4bc7e18f0779'

    def test_vector_1__settings_file_id(self):
        read_key         = bytes.fromhex('a9cbcf15b4719384a732594405f138a2a42895fe56710dcfbd1324369f735124')
        settings_file_id = self.crypto.derive_settings_file_id(read_key, 'a1b2c3d4')
        assert settings_file_id == '591414eaaa88'

    def test_vector_1__derive_keys_all_at_once(self):
        keys = self.crypto.derive_keys('my-secret-passphrase', 'a1b2c3d4')
        assert keys['read_key']         == 'a9cbcf15b4719384a732594405f138a2a42895fe56710dcfbd1324369f735124'
        assert keys['write_key']        == '3181d6650958b51fd00f913f6290eca22e6b09da661c8e831fc89fe659df378e'
        assert keys['tree_file_id']     == '4bc7e18f0779'
        assert keys['settings_file_id'] == '591414eaaa88'
        assert keys['passphrase']       == 'my-secret-passphrase'
        assert keys['vault_id']         == 'a1b2c3d4'

    def test_vector_1__derive_keys_from_vault_key(self):
        keys = self.crypto.derive_keys_from_vault_key('my-secret-passphrase:a1b2c3d4')
        assert keys['read_key']         == 'a9cbcf15b4719384a732594405f138a2a42895fe56710dcfbd1324369f735124'
        assert keys['write_key']        == '3181d6650958b51fd00f913f6290eca22e6b09da661c8e831fc89fe659df378e'
        assert keys['tree_file_id']     == '4bc7e18f0779'
        assert keys['settings_file_id'] == '591414eaaa88'

    # --- Cross-language test vector 2 ---

    def test_vector_2__read_key(self):
        read_key = self.crypto.derive_read_key('pass:with:colons', 'deadbeef')
        assert read_key.hex() == 'a903fc429b2806e6c05ba0d21271d982f451bd3c78e4899a8ee6e0fbed3d9b3f'

    def test_vector_2__write_key(self):
        write_key = self.crypto.derive_write_key('pass:with:colons', 'deadbeef')
        assert write_key.hex() == '3da59de516555d963eaf4c5d3179893acd9045bb0df69f3c89c0bed915a77f96'

    def test_vector_2__tree_file_id(self):
        read_key     = bytes.fromhex('a903fc429b2806e6c05ba0d21271d982f451bd3c78e4899a8ee6e0fbed3d9b3f')
        tree_file_id = self.crypto.derive_tree_file_id(read_key, 'deadbeef')
        assert tree_file_id == '220ae644906a'

    def test_vector_2__settings_file_id(self):
        read_key         = bytes.fromhex('a903fc429b2806e6c05ba0d21271d982f451bd3c78e4899a8ee6e0fbed3d9b3f')
        settings_file_id = self.crypto.derive_settings_file_id(read_key, 'deadbeef')
        assert settings_file_id == '5398a4d71d8d'

    def test_vector_2__derive_keys_from_vault_key(self):
        keys = self.crypto.derive_keys_from_vault_key('pass:with:colons:deadbeef')
        assert keys['read_key']         == 'a903fc429b2806e6c05ba0d21271d982f451bd3c78e4899a8ee6e0fbed3d9b3f'
        assert keys['write_key']        == '3da59de516555d963eaf4c5d3179893acd9045bb0df69f3c89c0bed915a77f96'
        assert keys['tree_file_id']     == '220ae644906a'
        assert keys['settings_file_id'] == '5398a4d71d8d'

    # --- Key independence ---

    def test_read_key_and_write_key_are_independent(self):
        read_key  = self.crypto.derive_read_key('test-pass', 'abcd1234')
        write_key = self.crypto.derive_write_key('test-pass', 'abcd1234')
        assert read_key != write_key

    def test_different_vault_id_different_keys(self):
        keys1 = self.crypto.derive_keys('same-pass', 'aaaaaaaa')
        keys2 = self.crypto.derive_keys('same-pass', 'bbbbbbbb')
        assert keys1['read_key']     != keys2['read_key']
        assert keys1['write_key']    != keys2['write_key']
        assert keys1['tree_file_id'] != keys2['tree_file_id']

    def test_different_passphrase_different_keys(self):
        keys1 = self.crypto.derive_keys('pass-one', 'abcd1234')
        keys2 = self.crypto.derive_keys('pass-two', 'abcd1234')
        assert keys1['read_key']     != keys2['read_key']
        assert keys1['write_key']    != keys2['write_key']
        assert keys1['tree_file_id'] != keys2['tree_file_id']

    # --- Encrypt/decrypt round trip with derived keys ---

    def test_encrypt_decrypt_with_derived_read_key(self):
        keys      = self.crypto.derive_keys('my-secret-passphrase', 'a1b2c3d4')
        read_key  = keys['read_key_bytes']
        plaintext = b'{"vault_name": "Test Vault", "version": 1}'
        encrypted = self.crypto.encrypt(read_key, plaintext)
        decrypted = self.crypto.decrypt(read_key, encrypted)
        assert decrypted == plaintext

    # --- compute_object_id ---

    def test_compute_object_id__returns_12_hex_chars(self):
        ciphertext = b'test ciphertext data'
        object_id  = self.crypto.compute_object_id(ciphertext)
        assert len(object_id) == 12
        assert all(c in '0123456789abcdef' for c in object_id)

    def test_compute_object_id__deterministic(self):
        ciphertext = b'deterministic test'
        id_1 = self.crypto.compute_object_id(ciphertext)
        id_2 = self.crypto.compute_object_id(ciphertext)
        assert id_1 == id_2

    def test_compute_object_id__different_data_different_ids(self):
        id_1 = self.crypto.compute_object_id(b'data one')
        id_2 = self.crypto.compute_object_id(b'data two')
        assert id_1 != id_2

    def test_compute_object_id__is_sha256_prefix(self):
        import hashlib
        ciphertext = b'sha256 prefix test'
        expected   = hashlib.sha256(ciphertext).hexdigest()[:12]
        actual     = self.crypto.compute_object_id(ciphertext)
        assert actual == expected

    def test_compute_object_id__same_plaintext_different_ciphertext(self):
        key       = self.crypto.derive_read_key('test-pass', 'abcd1234')
        plaintext = b'identical content'
        ct_1      = self.crypto.encrypt(key, plaintext)
        ct_2      = self.crypto.encrypt(key, plaintext)
        id_1      = self.crypto.compute_object_id(ct_1)
        id_2      = self.crypto.compute_object_id(ct_2)
        assert id_1 != id_2

    # --- derive_ref_file_id ---

    def test_derive_ref_file_id__returns_12_hex_chars(self):
        key     = self.crypto.derive_read_key('test-pass', 'abcd1234')
        ref_id  = self.crypto.derive_ref_file_id(key, 'abcd1234')
        assert len(ref_id) == 12
        assert all(c in '0123456789abcdef' for c in ref_id)

    def test_derive_ref_file_id__deterministic(self):
        key  = self.crypto.derive_read_key('test-pass', 'abcd1234')
        id_1 = self.crypto.derive_ref_file_id(key, 'abcd1234')
        id_2 = self.crypto.derive_ref_file_id(key, 'abcd1234')
        assert id_1 == id_2

    def test_derive_ref_file_id__differs_from_tree_file_id(self):
        key     = self.crypto.derive_read_key('test-pass', 'abcd1234')
        ref_id  = self.crypto.derive_ref_file_id(key, 'abcd1234')
        tree_id = self.crypto.derive_tree_file_id(key, 'abcd1234')
        assert ref_id != tree_id

    def test_derive_ref_file_id__differs_from_settings_file_id(self):
        key          = self.crypto.derive_read_key('test-pass', 'abcd1234')
        ref_id       = self.crypto.derive_ref_file_id(key, 'abcd1234')
        settings_id  = self.crypto.derive_settings_file_id(key, 'abcd1234')
        assert ref_id != settings_id

    def test_derive_keys__includes_ref_file_id(self):
        keys = self.crypto.derive_keys('test-pass', 'abcd1234')
        assert 'ref_file_id' in keys
        assert len(keys['ref_file_id']) == 12

    def test_derive_keys__ref_file_id_matches_direct(self):
        keys       = self.crypto.derive_keys('test-pass', 'abcd1234')
        direct_id  = self.crypto.derive_ref_file_id(keys['read_key_bytes'], 'abcd1234')
        assert keys['ref_file_id'] == direct_id
