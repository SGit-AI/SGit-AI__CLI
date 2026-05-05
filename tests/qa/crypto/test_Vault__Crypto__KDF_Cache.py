"""
Tests for Vault__Crypto.clear_kdf_cache() — AppSec finding F03 / mutation M5.

Three tests required by brief 12:
  1. Functional: clear empties the cache; subsequent derivations still work.
  2. Cache-bound: cache_info().currsize == 0 immediately after clear.
  3. M5 mutation closer: maxsize is 256 (not 0), so cache grows after derivations.
"""
from sgit_ai.crypto.Vault__Crypto import (
    Vault__Crypto,
    _pbkdf2_cached,
    AES_KEY_BYTES,
)


class Test_Vault__Crypto__KDF_Cache:

    def setup_method(self):
        self.crypto = Vault__Crypto()
        # Start each test with a clean slate so tests are order-independent.
        _pbkdf2_cached.cache_clear()

    # ------------------------------------------------------------------
    # Test 1 — functional: clear empties cache; subsequent derive works
    # ------------------------------------------------------------------

    def test_clear_kdf_cache__functional(self):
        """clear_kdf_cache() wipes the cache and derivations still succeed."""
        passphrase = b'test-passphrase'
        salt       = b'sg-vault-v1:testid'

        # Warm up the cache with one derivation.
        key_before = self.crypto.derive_key_from_passphrase(passphrase, salt)
        assert _pbkdf2_cached.cache_info().currsize >= 1

        # Clear it.
        self.crypto.clear_kdf_cache()

        # Subsequent derivation must still produce the correct key.
        key_after = self.crypto.derive_key_from_passphrase(passphrase, salt)
        assert key_after == key_before
        assert len(key_after) == AES_KEY_BYTES

    # ------------------------------------------------------------------
    # Test 2 — cache-bound: currsize == 0 immediately after clear
    # ------------------------------------------------------------------

    def test_clear_kdf_cache__currsize_zero_after_clear(self):
        """cache_info().currsize is exactly 0 after clear_kdf_cache()."""
        # Derive several distinct keys so the cache is non-empty.
        for i in range(5):
            self.crypto.derive_key_from_passphrase(
                f'passphrase-{i}'.encode(),
                f'salt-{i}'.encode(),
            )

        assert _pbkdf2_cached.cache_info().currsize >= 5

        self.crypto.clear_kdf_cache()

        assert _pbkdf2_cached.cache_info().currsize == 0

    # ------------------------------------------------------------------
    # Test 3 — M5 mutation closer: maxsize == 256 (cache is enabled)
    # ------------------------------------------------------------------

    def test_pbkdf2_cache_size_bounded(self):
        """The LRU cache is enabled (maxsize=256) and grows after derivations.

        This closes mutation M5: if someone sets maxsize=0 the cache never
        stores any entry (currsize stays 0 and hits stay 0).  With the real
        maxsize=256, after N unique derivations currsize == N (for N <= 256)
        and cache_info().hits grows on repeated calls for the same inputs.
        """
        _pbkdf2_cached.cache_clear()

        # Derive 10 unique entries.
        n = 10
        for i in range(n):
            self.crypto.derive_key_from_passphrase(
                f'pw-{i}'.encode(),
                f'salt-{i}'.encode(),
            )

        info = _pbkdf2_cached.cache_info()
        # maxsize must be 256 — not 0 (which would disable caching).
        assert info.maxsize == 256
        # With maxsize=0 the cache is disabled; currsize would stay 0.
        assert info.currsize == n

        # Repeated derivation of an already-cached entry must hit the cache.
        self.crypto.derive_key_from_passphrase(b'pw-0', b'salt-0')
        hits_after = _pbkdf2_cached.cache_info().hits
        assert hits_after >= 1
