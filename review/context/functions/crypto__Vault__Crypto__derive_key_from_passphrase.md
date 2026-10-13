## `derive_key_from_passphrase` in sgit_ai/crypto/Vault__Crypto.py (L284-L285)

```python
# L284-L285
def derive_key_from_passphrase(self, passphrase: bytes, salt: bytes) -> bytes:
    return _pbkdf2_cached(passphrase, salt)
```

**Purpose:** The Type_Safe-class façade over the module-level cached PBKDF2 so callers never touch `_pbkdf2_cached` directly.

**Inputs & Assumptions:** `passphrase` (bytes), `salt` (bytes); both must be hashable bytes (lru_cache requirement). Callers `.encode()` first (L140, L144, `Secrets__Store.py:L17`).

**Outputs & Effects:** 32 bytes; populates the cache (see `_pbkdf2_cached`).

**Cross-Function Dependencies:**
- Callee `_pbkdf2_cached` (internal, L26-L32).
- Callers: `derive_read_key` L140, `derive_write_key` L144, `Secrets__Store.derive_master_key` (`sgit_ai/secrets/Secrets__Store.py:L17`). The credential-store master key therefore shares the same cache as vault keys.
- Tests: `test_Vault__Crypto.py::test_derive_key_from_passphrase__*`, `test_Vault__Crypto__Hardening.py::Test_Vault__Crypto__PBKDF2_Edge_Cases` (empty passphrase, 1-byte salt accepted).

**Open Questions:** none.
