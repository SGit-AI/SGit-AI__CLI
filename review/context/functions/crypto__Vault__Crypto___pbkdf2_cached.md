## `_pbkdf2_cached` in sgit_ai/crypto/Vault__Crypto.py (L26-L32)

```python
# L26-L32
@functools.lru_cache(maxsize=256)
def _pbkdf2_cached(passphrase: bytes, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(algorithm  = hashes.SHA256(),
                     length     = AES_KEY_BYTES,
                     salt       = salt,
                     iterations = PBKDF2_ITERATIONS)
    return kdf.derive(passphrase)
```

**Purpose:** The single PBKDF2-SHA256 (600 000 iterations, L13) that turns a passphrase and a salt into a 32-byte key. Every read key, write key (L138-L144) and the credential-store master key (`sgit_ai/secrets/Secrets__Store.py:L15-L17`) comes from here. It is the only module-level function in the slice (CLAUDE.md "no module-level functions") and exists at module level so the `lru_cache` is process-wide rather than per `Vault__Crypto` instance.

**Inputs & Assumptions:**
- `passphrase` (bytes): the secret. Trust: **untrusted** in strength (TM-R16); comes from argv, `vault_key` file, env var or `getpass` through `derive_read_key`/`derive_write_key` (L138-L144) and `Secrets__Store.derive_master_key`.
- `salt` (bytes): domain string `sg-vault-v1:<vault_id>`, `sg-vault-v1:write:<vault_id>` or `sg-send-secrets-v1:master`. Trust: trusted (built by callers from constants; `vault_id` is validated to `^[a-z0-9]{4,24}$` only on the `parse_vault_key` path, L130).
- Implicit: the module-level LRU cache state (functools), shared by every thread and every `Vault__Crypto` instance in the process.
- Precondition: both arguments hashable (bytes). Established by the callers' `.encode()` at L140, L144 and `Secrets__Store.py:L17`.

**Outputs & Effects:**
- Returns 32 bytes (`AES_KEY_BYTES`, L14).
- State write: on a cache miss the pair `(passphrase, salt)` becomes a cache key and the derived key its value; up to 256 entries live in process memory (L26) until `cache_clear()` (L282) or exit. The passphrase bytes are retained as part of the key tuple, not only the derived key.
- Postcondition: a second call with the same arguments returns the same object without recomputation (`tests/qa/crypto/test_Vault__Crypto__KDF_Cache.py::test_pbkdf2_cache_size_bounded`).

**Block-by-Block:**

```python
# L26
@functools.lru_cache(maxsize=256)
```
- **What:** Memoises the derivation.
- **Why here:** 600 000 iterations cost ~190 ms per call (`tests/_helpers/vault_test_env.py:L30-L37`); a command derives read and write key and may re-derive several times (`CLI__Vault.py:L1764-L1766` comment).
- **Assumes:** holding derived keys and passphrases in process memory for the life of the process is acceptable. Documented as accepted at TM-R16; cleared on two paths only (see Cross-Function).
- **Establishes:** per-process key cache.
- **Depended on by:** `derive_key_from_passphrase` (L284-L285), `clear_kdf_cache` (L280-L282).

```python
# L28-L32
kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=AES_KEY_BYTES, salt=salt, iterations=PBKDF2_ITERATIONS)
return kdf.derive(passphrase)
```
- **What:** The derivation.
- **Assumes:** parameters match the browser (CLAUDE.md "Crypto Interop Requirement"). Established by `tests/unit/crypto/test_Vault__Crypto.py::test_vector_1__read_key` and `::test_vector_2__read_key` (fixed vectors) and `test_Vault__Crypto__Hardening.py::test_pbkdf2_iterations_constant`.

**Cross-Function Dependencies:**
- Callee `PBKDF2HMAC.derive` (external-black-box, `cryptography`): the KDF itself.
- Callers: `Vault__Crypto.derive_key_from_passphrase` (L284-L285) only; through it `derive_read_key`/`derive_write_key` and `Secrets__Store.derive_master_key`. Tests call it directly (`test_Vault__Crypto__KDF_Cache.py`).
- Shared state: the cache. Cleared only by `Vault__Sync__Lifecycle.delete_on_remote` (`sgit_ai/core/actions/lifecycle/Vault__Sync__Lifecycle.py:L22`) and `rekey_wipe` (L62). No other command clears it; `sgit vault info` relies on it staying warm (`CLI__Vault.py:L1764-L1766`).
- Invariant coupling: the unit suite's fixed `TEST_VAULT_KEY` (`vault_test_env.py:L37`) exists because of this cache; a mutation test (`tests/mutation/mutations.py:L87-L92`) guards `maxsize=256`.

**Open Questions:**
- unclear; whether any long-lived process (the dev server plugin under `sgit_ai/plugins/dev/`) keeps a `Vault__Crypto` alive across many vaults, which is where a 256-entry cache of passphrases would accumulate. Not in this slice.
