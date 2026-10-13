## `clear_kdf_cache` in sgit_ai/crypto/Vault__Crypto.py (L280-L282)

```python
# L280-L282
def clear_kdf_cache(self) -> None:
    _pbkdf2_cached.cache_clear()
```

**Purpose:** Flushes the process-wide PBKDF2 LRU so derived keys (and the passphrases that key the cache) stop living in memory (docstring L281).

**Inputs & Assumptions:** none; acts on module state.

**Outputs & Effects:** `cache_info().currsize == 0` afterwards (`tests/qa/crypto/test_Vault__Crypto__KDF_Cache.py::test_clear_kdf_cache__currsize_zero_after_clear`). Later derivations recompute (`::test_clear_kdf_cache__functional`).

**Cross-Function Dependencies:**
- Callee `functools._lru_cache_wrapper.cache_clear` (external, stdlib).
- Callers: `Vault__Sync__Lifecycle.delete_on_remote` (`sgit_ai/core/actions/lifecycle/Vault__Sync__Lifecycle.py:L22`, after the server delete) and `Vault__Sync__Lifecycle.rekey_wipe` (L62, after `secure_rmtree`). No other command (clone, push, pull, info, the credential store) clears it; the normal end-of-command path relies on process exit. TM-R16 records this as accepted.
- Shared state: the cache, with `_pbkdf2_cached` and `derive_key_from_passphrase`.

**Open Questions:** none.
