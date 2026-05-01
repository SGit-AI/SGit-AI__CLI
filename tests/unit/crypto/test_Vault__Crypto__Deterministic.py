# Tests for deterministic-encryption primitives in Vault__Crypto (closes M1, M2, M3).
import base64
import hashlib
import hmac

from sgit_ai.crypto.Vault__Crypto import Vault__Crypto, GCM_IV_BYTES


KEY_1 = bytes.fromhex('0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef')
KEY_2 = bytes.fromhex('fedcba9876543210fedcba9876543210fedcba9876543210fedcba9876543210')
META_KEY = bytes.fromhex('aabbccdd00112233aabbccdd00112233aabbccdd00112233aabbccdd00112233')

PLAINTEXT_BYTES = b'hello vault determinism'
PLAINTEXT_STR   = 'readme.txt'

# Pre-computed browser-interop vectors (SHA-256 HMAC-IV, AES-256-GCM):
#   KEY_1 + PLAINTEXT_BYTES  → IV dc89bcc0835a5e778b894f51
INTEROP_VECTOR_HEX = (
    'dc89bcc0835a5e778b894f51'            # 12-byte IV
    '58283384a975ddbeeddd7e4d574980284d3f92f4472a4df70412c4bef3c46259e628c3d1e87ac8'
)
#   META_KEY + b'readme.txt'  → base64 ciphertext
INTEROP_META_B64 = 'GmIHCWmLl1A1qC5lcVCZ+gc0HgWtx8wRzLU89bN0tDT3giNBohg='


class Test_Vault__Crypto__Deterministic:

    def setup_method(self):
        self.crypto = Vault__Crypto()

    # ------------------------------------------------------------------
    # encrypt_deterministic — determinism
    # ------------------------------------------------------------------

    def test_determinism__same_key_same_plaintext_same_ciphertext(self):
        """Same plaintext + same key must produce identical ciphertext (M3 guard)."""
        ct1 = self.crypto.encrypt_deterministic(KEY_1, PLAINTEXT_BYTES)
        ct2 = self.crypto.encrypt_deterministic(KEY_1, PLAINTEXT_BYTES)
        assert ct1 == ct2

    def test_determinism__three_calls_are_identical(self):
        ct1 = self.crypto.encrypt_deterministic(KEY_1, PLAINTEXT_BYTES)
        ct2 = self.crypto.encrypt_deterministic(KEY_1, PLAINTEXT_BYTES)
        ct3 = self.crypto.encrypt_deterministic(KEY_1, PLAINTEXT_BYTES)
        assert ct1 == ct2 == ct3

    # ------------------------------------------------------------------
    # encrypt_deterministic — cross-vault divergence (closes M1, M2)
    # ------------------------------------------------------------------

    def test_cross_vault_divergence__different_keys_different_ciphertext(self):
        """Different keys with same plaintext must produce different ciphertext.

        Closes M1 (dropping HMAC key) and M2 (hard-coding HMAC key): either
        mutation makes the IV key-independent, causing ciphertexts to collide.
        """
        ct1 = self.crypto.encrypt_deterministic(KEY_1, PLAINTEXT_BYTES)
        ct2 = self.crypto.encrypt_deterministic(KEY_2, PLAINTEXT_BYTES)
        assert ct1 != ct2

    def test_cross_vault_divergence__ivs_differ_between_keys(self):
        """The first 12 bytes (IV) must differ when the key differs."""
        ct1 = self.crypto.encrypt_deterministic(KEY_1, PLAINTEXT_BYTES)
        ct2 = self.crypto.encrypt_deterministic(KEY_2, PLAINTEXT_BYTES)
        assert ct1[:GCM_IV_BYTES] != ct2[:GCM_IV_BYTES]

    # ------------------------------------------------------------------
    # encrypt_deterministic — round-trip
    # ------------------------------------------------------------------

    def test_round_trip__decrypt_recovers_plaintext(self):
        """decrypt(encrypt_deterministic(p, k), k) == p"""
        ct = self.crypto.encrypt_deterministic(KEY_1, PLAINTEXT_BYTES)
        assert self.crypto.decrypt(KEY_1, ct) == PLAINTEXT_BYTES

    def test_round_trip__empty_plaintext(self):
        ct = self.crypto.encrypt_deterministic(KEY_1, b'')
        assert self.crypto.decrypt(KEY_1, ct) == b''

    def test_round_trip__large_plaintext(self):
        large = b'A' * 65536
        ct = self.crypto.encrypt_deterministic(KEY_1, large)
        assert self.crypto.decrypt(KEY_1, ct) == large

    # ------------------------------------------------------------------
    # encrypt_deterministic — IV derivation property (closes M3)
    # ------------------------------------------------------------------

    def test_iv_derivation__equals_hmac_sha256_prefix(self):
        """IV must be exactly HMAC-SHA256(key, plaintext)[:12].

        Closes M3: replacing HMAC-IV with os.urandom(12) breaks this assertion
        because the random IV will not equal the HMAC-derived value.
        """
        ct            = self.crypto.encrypt_deterministic(KEY_1, PLAINTEXT_BYTES)
        actual_iv     = ct[:GCM_IV_BYTES]
        expected_iv   = hmac.new(KEY_1, PLAINTEXT_BYTES, hashlib.sha256).digest()[:GCM_IV_BYTES]
        assert actual_iv == expected_iv

    def test_iv_derivation__uses_key_as_hmac_key(self):
        """HMAC must use the encryption key — not a constant or just the plaintext."""
        iv1 = self.crypto.encrypt_deterministic(KEY_1, PLAINTEXT_BYTES)[:GCM_IV_BYTES]
        iv2 = self.crypto.encrypt_deterministic(KEY_2, PLAINTEXT_BYTES)[:GCM_IV_BYTES]
        # IV from HMAC(KEY_1, pt) must differ from HMAC(KEY_2, pt)
        expected_iv1 = hmac.new(KEY_1, PLAINTEXT_BYTES, hashlib.sha256).digest()[:GCM_IV_BYTES]
        expected_iv2 = hmac.new(KEY_2, PLAINTEXT_BYTES, hashlib.sha256).digest()[:GCM_IV_BYTES]
        assert iv1 == expected_iv1
        assert iv2 == expected_iv2
        assert expected_iv1 != expected_iv2

    # ------------------------------------------------------------------
    # encrypt_deterministic — browser interop vector
    # ------------------------------------------------------------------

    def test_browser_interop_vector__exact_hex_output(self):
        """Fixed input → fixed expected output matches Web Crypto API byte-for-byte."""
        ct = self.crypto.encrypt_deterministic(KEY_1, PLAINTEXT_BYTES)
        assert ct.hex() == INTEROP_VECTOR_HEX

    def test_browser_interop_vector__iv_matches_expected(self):
        expected_iv = bytes.fromhex('dc89bcc0835a5e778b894f51')
        ct          = self.crypto.encrypt_deterministic(KEY_1, PLAINTEXT_BYTES)
        assert ct[:GCM_IV_BYTES] == expected_iv

    # ------------------------------------------------------------------
    # encrypt_metadata_deterministic — determinism
    # ------------------------------------------------------------------

    def test_metadata_determinism__same_key_same_plaintext_same_ciphertext(self):
        """encrypt_metadata_deterministic is deterministic for the same inputs."""
        b64_1 = self.crypto.encrypt_metadata_deterministic(META_KEY, PLAINTEXT_STR)
        b64_2 = self.crypto.encrypt_metadata_deterministic(META_KEY, PLAINTEXT_STR)
        assert b64_1 == b64_2

    # ------------------------------------------------------------------
    # encrypt_metadata_deterministic — cross-vault divergence (closes M1, M2)
    # ------------------------------------------------------------------

    def test_metadata_cross_vault_divergence__different_keys(self):
        """Different keys → different metadata ciphertext (same M1/M2 guard)."""
        b64_k1 = self.crypto.encrypt_metadata_deterministic(KEY_1, PLAINTEXT_STR)
        b64_k2 = self.crypto.encrypt_metadata_deterministic(KEY_2, PLAINTEXT_STR)
        assert b64_k1 != b64_k2

    # ------------------------------------------------------------------
    # encrypt_metadata_deterministic — round-trip
    # ------------------------------------------------------------------

    def test_metadata_round_trip__decrypt_recovers_plaintext(self):
        """decrypt_metadata(encrypt_metadata_deterministic(p, k), k) == p"""
        b64 = self.crypto.encrypt_metadata_deterministic(META_KEY, PLAINTEXT_STR)
        assert self.crypto.decrypt_metadata(META_KEY, b64) == PLAINTEXT_STR

    def test_metadata_round_trip__unicode_plaintext(self):
        text = 'données/fichier café.txt'
        b64  = self.crypto.encrypt_metadata_deterministic(META_KEY, text)
        assert self.crypto.decrypt_metadata(META_KEY, b64) == text

    # ------------------------------------------------------------------
    # encrypt_metadata_deterministic — IV derivation property (closes M3)
    # ------------------------------------------------------------------

    def test_metadata_iv_derivation__equals_hmac_sha256_prefix(self):
        """Metadata IV must also be HMAC-SHA256(key, utf8(plaintext))[:12]."""
        b64            = self.crypto.encrypt_metadata_deterministic(META_KEY, PLAINTEXT_STR)
        raw            = base64.b64decode(b64)
        actual_iv      = raw[:GCM_IV_BYTES]
        expected_iv    = hmac.new(META_KEY, PLAINTEXT_STR.encode('utf-8'),
                                   hashlib.sha256).digest()[:GCM_IV_BYTES]
        assert actual_iv == expected_iv

    # ------------------------------------------------------------------
    # encrypt_metadata_deterministic — browser interop vector
    # ------------------------------------------------------------------

    def test_metadata_browser_interop_vector__exact_b64_output(self):
        """Fixed input → fixed base64 output matches Web Crypto API byte-for-byte."""
        b64 = self.crypto.encrypt_metadata_deterministic(META_KEY, PLAINTEXT_STR)
        assert b64 == INTEROP_META_B64

    def test_metadata_browser_interop_vector__decode_and_decrypt(self):
        """The interop ciphertext can be decrypted back to the expected plaintext."""
        assert self.crypto.decrypt_metadata(META_KEY, INTEROP_META_B64) == PLAINTEXT_STR
