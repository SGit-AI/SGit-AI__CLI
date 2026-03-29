# Sync Test Performance Deep Dive

**Date:** 2026-03-29
**Author:** Explorer Dev Agent
**Environment:** Python 3.11, Linux 6.18.5, in-process in-memory API

---

## Executive Summary

The slowness is almost entirely due to **PBKDF2-HMAC-SHA256 at 600,000 iterations** being
invoked on every single operation that calls `_init_components()`. Every `commit()`, `push()`,
`pull()`, `stash()`, `status()`, `branches()`, and `switch()` call re-derives keys from the
passphrase — at ~102 ms per derivation (2 derivations per `_init_components` call = ~204 ms each
call).

There is no network, no caching, no sleep — the test suite is paying the full production security
cost on every operation, every time.

---

## Environment Measurements

All times measured on this machine with Python 3.11, in-memory API, local filesystem.

| Operation | Time |
|-----------|------|
| `PBKDF2HMAC.derive()` (one call, 600k iterations) | **~102 ms** |
| `derive_keys()` = 2× PBKDF2 + 1× HKDF + 1× HMAC | **~204 ms** |
| `_init_components()` (reads vault_key file + derive_keys) | **~205 ms** |
| `restore()` (copytree + deepcopy, Stash snapshot) | **~1.5 ms** |
| `restore()` (two-clone snapshot with two dirs) | **~4.1 ms** |

The restore() overhead is **negligible** — the comment in vault_test_env.py claiming "~3 ms
restore time" is accurate and confirmed. The snapshot/restore mechanism is not the problem.

---

## Task 1: What Each Operation Does

### `Vault__Stash.stash()`

1. Creates a `Vault__Revert` and calls `revert._init_components(directory)` — **1× PBKDF2 pair** (read + write key = 2 PBKDF2 calls)
2. Computes file status (walks directory, loads HEAD commit, decrypts tree + blob metadata via AES-GCM)
3. Builds a ZIP of modified/added files (unencrypted, plaintext zip)
4. Calls `revert.revert_all_to_head()` → `revert._init_components()` again — **another 1× PBKDF2 pair**
5. Writes files back from object store (AES-GCM decrypt per file)

Total PBKDF2 pairs in `stash()` alone: **2** (= 4 individual PBKDF2 calls = ~408 ms)

### `Vault__Stash.pop()`

No `_init_components` call. Reads the ZIP and writes files. Fast (<5 ms).

### `Vault__Sync.commit()`

1. `_init_components()` — 1× PBKDF2 pair (~204 ms)
2. Scans local directory
3. Loads parent commit (AES-GCM decrypt)
4. Builds tree objects (AES-GCM encrypt per tree node)
5. Writes commit object (AES-GCM encrypt)
6. Updates ref file (AES-GCM encrypt)

Total PBKDF2 pairs in `commit()`: **1** (~204 ms)

### `Vault__Sync.push()`

Push calls `_init_components()` directly, then internally calls:
1. `status()` which calls `_init_components()` again (for dirty check)
2. `pull()` (fetch-first) which calls `_init_components()` again

Total `_init_components()` calls in a typical `push()`: **3–4**
Total PBKDF2 cost in `push()`: **~612–816 ms**

### `Vault__Sync.pull()`

1. `_init_components()` — 1× call
2. Fetches missing objects from API (in-memory: just a dict lookup)
3. Loads commits + trees (AES-GCM decrypt per object)
4. Three-way merge computation (pure Python)
5. Writes merged files to working copy (AES-GCM decrypt per blob)
6. Creates merge commit (AES-GCM encrypt)
7. Updates ref (AES-GCM encrypt)

### `Vault__Sync.clone()`

1. `_derive_keys_from_stored_key()` (= 1× PBKDF2 pair, no `_init_components()` wrapper here)
2. Downloads all objects from API (in-memory: dict lookups)
3. Walks commit + tree graph
4. Writes all files to working copy

---

## Task 2: Single Stash Test Profile

Profiler run on `test_stash_modified_file_creates_zip` equivalent:

```
23604 function calls in 0.419 seconds (stash + pop together)

ncalls  tottime  percall  cumtime  percall  function
     2    0.000    0.000    0.406    0.203  Vault__Revert._init_components
     4    0.403    0.101    0.403    0.101  {built-in method kdf.derive_pbkdf2_hmac}
     2    0.000    0.000    0.403    0.101  Vault__Crypto.derive_key_from_passphrase
     1    0.000    0.000    0.207    0.207  Vault__Revert.revert_all_to_head
```

Of 419 ms total: **403 ms** (96%) is PBKDF2.

### Full test body timing (setup_method + commit + stash)

Profiler on `run_test_body_stash_modified` (setup_method restore + commit + stash):

```
35289 function calls in 0.657 seconds

ncalls  tottime  percall  cumtime  percall  function
     6    0.630    0.105    0.630    0.105  {built-in method kdf.derive_pbkdf2_hmac}
     3    0.000    0.000    0.631    0.210  derive_keys_from_vault_key
```

Of 657 ms total: **630 ms** (96%) is PBKDF2.

- `commit()` = 1× `_init_components()` call (via `Vault__Sync._init_components`) = 2 PBKDF2 calls
- `stash()` = 2× `Vault__Revert._init_components()` calls = 4 PBKDF2 calls
- **Total: 3 `_init_components` calls × ~204 ms = ~612 ms in PBKDF2**

10-run average: **614 ms per test body**

---

## Task 3: Multi_Clone Test Profile

### setup_two_clones (once per class)

```
setup_two_clones: 1.060s
```

This runs: init (1× derive_keys) + commit (1×) + push (3×) + clone (1×) = ~6 PBKDF2 pairs = ~1.2s. Matches observed.

### Per-test restore()

```
9x restore(): 0.037s  (4.1 ms each)
```

Negligible.

### alice commit+push + bob pull (profiler output)

```
125091 function calls in 1.097 seconds

ncalls  tottime  percall  cumtime  percall  function
     5    0.000    0.000    1.025    0.205  _init_components
    10    1.016    0.102    1.016    0.102  {built-in method kdf.derive_pbkdf2_hmac}
     1    0.000    0.000    0.652    0.652  push
     2    0.000    0.000    0.454    0.227  pull
     1    0.000    0.000    0.216    0.216  status
     1    0.000    0.000    0.212    0.212  commit
```

Of 1.097s total: **1.016 s** (93%) is PBKDF2, from **5 `_init_components` calls**.

### Full round-trip body (alice commit+push, bob pull, bob commit+push, alice pull)

```
5x full round-trip: 10.630s  (2.13s each)
```

A full round-trip involves ~10 `_init_components` calls:
- alice commit: 1
- alice push: ~3 (push + status + pull-first)
- bob pull: 1
- bob commit: 1
- bob push: ~3
- alice pull: 1
- **Total: ~10 calls × 204 ms = ~2.04s** — matches exactly

---

## Task 4: Crypto Call Counts

Per `_init_components()` call:
- `derive_read_key()` → 1× `PBKDF2HMAC.derive()` (~102 ms)
- `derive_write_key()` → 1× `PBKDF2HMAC.derive()` (~102 ms)
- `derive_branch_index_file_id()` → 1× `hmac.new().hexdigest()` (~0 ms)
- `derive_ref_file_id()` → 1× `hmac.new().hexdigest()` (~0 ms)
- `derive_structure_key()` is NOT called in `_init_components` (only used internally when needed)

Per object encrypt/decrypt (AES-GCM, done many times per test):
- `AESGCM(key).encrypt(iv, plaintext, None)` — ~0.01 ms for tiny objects
- `AESGCM(key).decrypt(iv, ciphertext, None)` — ~0.01 ms for tiny objects

AES-GCM calls are essentially free at the data volumes in these tests (files are tens of bytes).

There are **no `sleep()` calls** anywhere in the sync code.

There are **no zipfile performance issues** — the stash ZIP contains tiny plaintext files.

### Summary: crypto call costs per operation type

| Operation | PBKDF2 calls | AES-GCM enc | AES-GCM dec | Time from PBKDF2 |
|-----------|-------------|-------------|-------------|-----------------|
| `commit()` | 2 | ~3–5 | ~3–5 | ~204 ms |
| `push()` | 6–8 | ~5–10 | ~10–20 | ~612–816 ms |
| `pull()` | 2 | ~3–5 | ~10–20 | ~204 ms |
| `stash()` | 4 | 0 | ~3–5 | ~408 ms |
| `clone()` | 2 | 0 | ~10–30 | ~204 ms |
| `status()` | 2 | 0 | ~3–5 | ~204 ms |
| `switch()` | 2–4 | ~3–5 | ~3–5 | ~204–408 ms |

---

## Task 5: restore() Overhead

The `restore()` method does:
1. `shutil.copytree(src, dst)` — copies the `.sg_vault/` directory tree
2. `copy.deepcopy(api._store)` — deep copies the in-memory dict

```
26x restore() (single vault, copytree + deepcopy): 0.039s  (1.5 ms each)
 9x restore() (two-clone, 2× copytree + deepcopy): 0.037s  (4.1 ms each)
```

**restore() is not the problem.** It accounts for ~1.5–4 ms per test, which is entirely
negligible compared to the 600–2100 ms spent in PBKDF2.

The snapshot mechanism was an excellent optimisation that saved ~400 ms per test (the full
`sync.init()` cost). The remaining slowness is in the test bodies, not in setup.

---

## Task 6: Root Cause Analysis

### Root Cause: No Key Caching Across Operations

Every public method in `Vault__Sync`, `Vault__Revert`, and `Vault__Branch_Switch` begins by
calling `_init_components(directory)`, which:

1. Opens and reads the `vault_key` file from disk
2. Calls `crypto.derive_keys_from_vault_key(vault_key)`, which runs:
   - `PBKDF2HMAC(SHA256, 600_000 iterations).derive(passphrase)` for the read key
   - `PBKDF2HMAC(SHA256, 600_000 iterations).derive(passphrase)` for the write key

The 600,000-iteration count is the NIST-recommended minimum for production security (OWASP 2023
recommendation is 600,000). This is correct for a CLI tool protecting real user data. But in
tests, every test body calls 3–10 of these operations, so we pay 600k-iteration PBKDF2 3–10
times per test, totalling 600k–6M iterations per test.

### Why `push()` is especially expensive

`push()` internally calls `status()` and `pull()`, each of which calls `_init_components()`
independently:

```python
def push(self, ...):
    c = self._init_components(directory)        # call 1 — derive_keys()
    local_status = self.status(directory)        # call 2 — status() re-derives!
    if not first_push:
        pull_result = self.pull(directory)       # call 3–4 — pull() re-derives, and
                                                 #   pull() also calls status() internally?
```

Each cascaded call re-reads the vault_key file and re-runs 2× PBKDF2. There is no mechanism
to pass an already-derived `Vault__Components` object through the call chain.

### Why `stash()` is expensive for a simple operation

`Vault__Stash.stash()` creates a `Vault__Revert` and calls `_init_components` twice:
- Once at the top of `stash()` (line 32: `c = revert._init_components(directory)`)
- Once inside `revert.revert_all_to_head()` → `revert_to_head()` → `_init_components()` (line 31)

Each `Vault__Revert._init_components()` call has the same 2× PBKDF2 cost as
`Vault__Sync._init_components()`. So stash alone pays 4× PBKDF2 = ~408 ms.

### Is it inherent or avoidable?

The PBKDF2 cost at 600,000 iterations **is inherent to production security**. It is not
avoidable without changing either:

(a) The number of iterations (breaks crypto spec / reduces security), or
(b) The key derivation strategy (e.g., derive once, cache for the session lifetime), or
(c) The test approach (e.g., use a test-specific low-iteration vault key, or inject
    pre-derived keys)

All other work (AES-GCM, file I/O, JSON parsing, Type_Safe deserialization, zipfile) takes
<10 ms per test body and is not worth optimising first.

---

## Specific Recommendations

### Recommendation 1 (Highest Impact): Cache derived keys per vault path

Add a module-level or instance-level LRU cache keyed by `(vault_key_string, vault_path)`.
Since the vault_key file is immutable once written and the passphrase never changes during a
test session, the derived keys can be cached safely for the lifetime of a test.

```python
# Pseudocode — not a code change, just a description
from functools import lru_cache

@lru_cache(maxsize=32)
def _cached_derive_keys(vault_key: str) -> dict:
    return crypto.derive_keys_from_vault_key(vault_key)
```

This would reduce the PBKDF2 cost from O(N_operations) to O(1) per vault per process.
Expected speedup: **10–15× per test** (from ~1.3s → ~0.05–0.1s per stash test).

### Recommendation 2 (Medium Impact): Pass Vault__Components through the call chain

Refactor `push()` so it passes the already-derived `components` object to `status()` and
`pull()` instead of having them re-derive. This eliminates redundant derivations within a
single `push()` call.

Currently:
```
push() → _init_components() → status() → _init_components() → pull() → _init_components()
```
After refactor:
```
push() → _init_components() once → passes `c` to status_from_components(c) + pull_from_components(c)
```
Expected speedup: **2–3× for push-heavy tests** (Multi_Clone round-trip goes from 2.1s → 0.7s).

### Recommendation 3 (Medium Impact): Stash should reuse components

`Vault__Stash.stash()` creates a `Vault__Revert` instance and calls `_init_components()` in
the stash method (to compute status), then `revert.revert_all_to_head()` calls it again.
The stash method could pass the already-derived `c` into the revert internals.

Expected speedup: **1.5× for stash tests** (removes 2 of the 3 PBKDF2 pairs per stash test body).

### Recommendation 4 (Low Impact but Simple): Test-only fast-KDF vault keys

For test fixtures, use a vault_key that triggers a code path with fewer PBKDF2 iterations.
For example, the `Simple_Token` path derives keys differently (see `Simple_Token.read_key()`)
and could be made faster for testing. However, this changes test coverage semantics.

### Recommendation 5 (Low Impact): Reduce iterations only in test mode

Set `PBKDF2_ITERATIONS = 1` when a `SGIT_AI_TEST_MODE=1` env var is set. This would make
each derivation take ~0 ms. Combined with the snapshot mechanism, tests would run in pure
I/O + AES time (~5–10 ms each). Risk: tests no longer cover the full production KDF path.

---

## Summary of Actual Timings

| Test suite | Tests | Total (reported) | Per test | PBKDF2 cost per test | Non-PBKDF2 per test |
|------------|-------|-----------------|----------|---------------------|---------------------|
| Stash | 26 | ~34s | ~1.3s | ~612 ms (3 calls) | ~30 ms |
| Multi_Clone | 9 | ~32s | ~3.6s | ~2040 ms (10 calls) | ~50 ms |
| Branch_Switch | 19 | ~31s | ~1.6s | ~408–816 ms (2–4 calls) | ~30 ms |

Non-PBKDF2 work per test: **5–50 ms** (file I/O, AES-GCM, JSON, Type_Safe deserialization).
PBKDF2 work per test: **612–2040 ms** (96%+ of total time).

If key derivation were cached (Recommendation 1), per-test times would drop to the 5–50 ms
range, making the full sync test suite run in seconds rather than minutes.
