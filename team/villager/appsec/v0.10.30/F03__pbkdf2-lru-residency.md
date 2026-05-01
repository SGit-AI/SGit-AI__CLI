# F03 — PBKDF2 LRU Cache: Long-Lived Key Material in Memory

**Severity:** MEDIUM (CLI) → HIGH (long-running agent process)
**Class:** Memory residency / shared-process side channel
**Disposition:** REAL-FIX-NEEDED for agent contexts; DOCUMENT-ONLY for CLI
**File:** `sgit_ai/crypto/Vault__Crypto.py:26-32`

## 1. The Construction

```python
@functools.lru_cache(maxsize=256)
def _pbkdf2_cached(passphrase: bytes, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=AES_KEY_BYTES,
                     salt=salt, iterations=PBKDF2_ITERATIONS)
    return kdf.derive(passphrase)
```

- Module-level (not instance-level), so the cache is shared across **all**
  `Vault__Crypto` instances in the same Python process.
- Stores up to 256 entries: `((passphrase_bytes, salt_bytes), derived_key_bytes)`.
- All three values are kept as `bytes` objects, immutable and not zeroable
  in CPython without C extensions.

## 2. Why This Cache Exists

`derive_keys()` calls `derive_read_key` and `derive_write_key`, each of
which runs PBKDF2 with 600,000 iterations. Without the cache, every
`_init_components` call costs ~1.2s of CPU. With it, repeat calls within
a single process are instant. Necessary for the v0.10.30 batch operations.

## 3. The Risk

### CLI mode
A `sgit` invocation runs for seconds, then exits. The cache lives, then
the process and its heap are released to the OS. **Risk: low** — same
order of magnitude as any other CPython program holding a passphrase.

### Agent mode (NEW with v0.10.30)
An agent (e.g., the agent-friendly `write`/`cat`/`fetch` commands wired
into a long-running tool harness) imports `Vault__Crypto` once and runs
operations across many vaults over hours. After:

1. Operating on vault A with passphrase P_A
2. Rekeying A (P_A → P_A')
3. Probing share token T → derives keys
4. Operating on vault B with P_B

**All four passphrase + read_key + write_key tuples remain in `_pbkdf2_cached`
indefinitely.** A second tenant in the same process (multi-tenant agent
host) or a memory-dump adversary recovers all of them.

`functools.lru_cache` is an LRU — the oldest entry is evicted only after
256 distinct keys are inserted. A single-tenant agent will rarely hit 256.

## 4. Concrete Mitigations

**Option A (preferred):** Replace `functools.lru_cache` with a
`Vault__Crypto`-instance-level cache that is cleared on a `forget_keys()`
method invoked at command exit, after rekey, after probe failure, and
after sensitive boundary crossings.

**Option B:** Reduce `maxsize` to a small number (e.g., 4) and add a
`Vault__Crypto.clear_kdf_cache()` callable. Wire into `rekey_wipe`,
`probe_token` failure path, `delete_on_remote` completion.

**Option C (most paranoid):** Drop the cache entirely; pay 1.2s per
operation. Probably overkill for v0.10.30; revisit if multi-tenant agent
becomes a real deployment target.

## 5. Why CPython `bytes` Cannot Be Zeroed

`bytes` is immutable. `del cached_dict[key]` removes the dict entry but
the underlying `PyBytesObject` lives until refcount → 0, then sits in the
freed-arena until the OS reclaims the page. There is no portable `mlock`
+ overwrite primitive in pure Python. `cryptography` library has internal
zeroisation for derived keys *during* `derive()`, but the returned `bytes`
object is not protected.

This is a Python-language-level limitation. Mitigations:
1. Minimise *number of long-lived bytes objects* holding key material.
2. Avoid copying keys (every `.hex()`/`.encode()` round-trip creates a new
   PyBytesObject).
3. For agent contexts: use a separate process per tenant (OS-level
   isolation > heap zeroisation).

## 6. Code-Reading Findings: Other Long-Lived Key Bytes

| Location | Holds | Lifetime |
|----------|-------|----------|
| `Vault__Crypto._pbkdf2_cached` | passphrase, salt, derived_key | process |
| `Vault__Components.read_key`/`write_key` | per-call, instance-bound | until GC |
| `Vault__Sync._init_components` returns dict | passphrase, vault_id | until caller drops ref |
| `clone_mode.json` on disk | `read_key_hex` | persistent on disk (F07) |
| `vault_key` file on disk | `passphrase:vault_id` | persistent on disk |

Note: `derive_keys()` returns a dict containing both `passphrase` (str) AND
`read_key`/`write_key` (hex str) AND `read_key_bytes`/`write_key_bytes`. So
each `_init_components` call creates **5 fresh objects holding key
material**. That's expected in Python; the issue is they all flow through
LRU and may live long.

## 7. Test Coverage

**No tests** verify cache size, eviction, or absence of stale entries. No
mutation in the cache logic would be detected by current tests.

Suggested tests for QA Phase 3:
- `test_pbkdf2_cache_size_bounded` — derive 300 different keys, assert
  `_pbkdf2_cached.cache_info().currsize <= 256`.
- `test_pbkdf2_cache_clear_after_rekey` — currently would fail; document
  as known gap or add `clear_kdf_cache()` call to rekey path.

## 8. Disposition

- **Document:** for CLI users, the cache is acceptable.
- **Real fix needed:** for agent contexts, add `Vault__Crypto.clear_kdf_cache()`
  and call it after rekey/probe/delete-on-remote. Small PR.
- **Escalate to Architect:** if multi-tenant agent host is a v0.11.x target,
  a proper "passphrase scope" abstraction is needed (instance-level cache
  with explicit lifetime management).
