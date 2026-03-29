# Test Suite Optimisation Debrief

**Date:** 2026-03-29
**Suite:** `tests/unit/` — 1 425 tests, all passing
**Net result:** 8 m 3 s → 1 m 8 s sequential (−86%) · 5 m 36 s → 1 m 9 s CI (−80%)

---

## Starting Point

Before any optimisation work the test suite was slow enough to be a friction point. A full
`pytest tests/unit/` run took **8 minutes 3 seconds** locally and **5 minutes 36 seconds** on
CI. The suite had ~1 400 tests and was growing.

The profiling work that preceded this session identified the cost was almost entirely in
two places:

- **`sync/` directory:** 181 s — 69% of total wall time
- **`cli/` directory:** 32 s — 12% of total

Everything else — safe_types, schemas, api, objects, pki, secrets — was negligible by
comparison.

---

## Round 1 — Class-Level Vault Snapshots (commit `45f1af1`)

### The problem

The most expensive sync tests ran a full `init → commit → push → [clone]` sequence inside
**every single test method**. `setup_method` (or a `_VaultFixture.__init__` helper) built a
fresh vault from scratch for each of the 26, 15, or 9 tests in a class. Each such setup cost
~200–400 ms, and for multi-clone tests the full round-trip cost 0.5–7 s per test body.

### The fix

A new helper, `Vault__Test_Env` (`tests/unit/sync/vault_test_env.py`), introduced the
**snapshot-and-restore** pattern:

1. In `setup_class`, build the vault once. Capture the filesystem state via
   `shutil.copytree` and the in-memory API store via `copy.deepcopy(api._store)`.
2. In each test, call `env.restore()` — which does a directory copy and a dict copy (~3 ms)
   — instead of rebuilding from scratch (~200–400 ms).

This was applied to:
- `test_Vault__Sync__Multi_Clone` — 9 tests saving ~3–7 s each
- `test_Vault__Sync__Clone`, `test_Vault__Sync__Push`, `test_Vault__Sync__Remote_Failure`
- `test_Vault__Stash`, `test_Vault__Branch_Switch`
- `test_CLI__PKI` — RSA-4096 key pairs generated once in `setup_class`, key directory
  copied per test

### Result

| | Before | After | Delta |
|---|---|---|---|
| sync/ | 6 m 19 s | 5 m 20 s | −59 s |
| TOTAL | 8 m 3 s | 7 m 13 s | **−50 s (−10%)** |
| CI | 5 m 36 s | 4 m 45 s | **−51 s (−15%)** |

---

## Round 2 — Broader Snapshot Coverage + Secrets / Crypto Fixtures (commit `51fc947`)

### The problem

Round 1 covered the highest-profile tests but left many sync files, the secrets tests, and
the crypto RSA tests untouched.

### The fix

Three separate changes:

**sync/:** Applied the `Vault__Test_Env` snapshot pattern to 7 more files:
`test_Vault__Batch`, `test_Vault__Sync__Pull`, `test_Vault__Sync__Commit`,
`test_Vault__Dump`, `test_Vault__Revert`, `test_Vault__GC`, `test_Vault__Sync__Uninit`.

**crypto/:** Four RSA-4096 + EC key pairs generated at **module level** in
`test_PKI__Crypto.py` and shared by all tests that only needed "a valid key" rather than a
freshly generated one.

**secrets/:** The PBKDF2 master key derived once at module level in both
`test_Secrets__Store.py` and `test_Secrets__Store__Edge_Cases.py`, monkey-patched per test
rather than re-derived each time.

### Result

| | Round 1 | Round 2 | Delta |
|---|---|---|---|
| crypto/ | 22 s 861 ms | 13 s 18 ms | −9.8 s |
| secrets/ | 13 s 901 ms | 1 s 634 ms | **−12.3 s (−88%)** |
| sync/ | 5 m 20 s | 4 m 32 s | −48 s |
| TOTAL | 7 m 13 s | 5 m 57 s | **−76 s (−18%)** |
| CI | 4 m 45 s | 3 m 48 s | **−57 s** |

Secrets took an 88% reduction from one module-level derivation. Crypto dropped 43%.

---

## Round 3 — Expanded Snapshot (and a lesson learned) (commit `9d63cb0`)

### The attempt

Extended the snapshot pattern to three more sync files (`Bare`, `Diff`, `Helpers`) and three
objects files (`Inspector__Coverage`, `Object_Store`, `Commit`). Also added a pre-generated
RSA key fixture to `PKI__Key_Store`.

### What went wrong

The snapshot pattern is only beneficial when the vault setup it replaces is expensive. For
`Bare`, `Diff`, and `Helpers`, the per-test setup only called `sync.init()` with no push or
commit — a cheap operation (~50 ms). The `Vault__Test_Env.setup_single_vault()` helper
performs an `init + commit + push`, so using it as the snapshot baseline added a `push()` call
that was **more expensive** than the init it replaced.

Result: sync/ regressed by **+25 s**.

### Result

| | Round 2 | Round 3 | Delta |
|---|---|---|---|
| objects/ | 14 s 512 ms | 2 s 950 ms | **−11.6 s** |
| pki/ | 6 s | 441 ms | **−5.6 s** |
| sync/ | 4 m 32 s | 4 m 57 s | **+25 s ✗** |
| TOTAL | 5 m 57 s | 6 m | **+3 s** |

**Lesson:** The snapshot pattern only helps when the operation being replaced is a full push-
capable vault lifecycle. Lightweight `init()`-only tests should not use `setup_single_vault()`.

---

## Round 4 — Revert + pytest-xdist (commit `25c4bc6`)

### The fix

Two changes:

1. **Reverted the three problematic Round 3 sync files** (`Bare`, `Diff`, `Helpers`) back to
   their per-test init pattern, recovering the +25 s regression.

2. **Added `pytest-xdist`** (`pytest-xdist = ">=3.0"`) to the dev dependencies. Running
   `pytest -n auto` distributes tests across all available CPU cores. With ~4 workers locally
   this gave a **3.4× speedup** for the parallel run.

   `addopts` in `pyproject.toml` was deliberately **not** set to `-n auto` because the CI
   shared action (`owasp-sbot/OSBot-GitHub-Actions/pytest__run-tests@dev`) did not install
   dev extras, so `pytest-xdist` was unavailable in CI. Including it in `addopts` would have
   broken CI (which it did in run #27, failing in 18 s).

### Result

| | Round 3 | Round 4 (seq) | Round 4 (parallel) |
|---|---|---|---|
| sync/ | 4 m 57 s | 4 m 33 s | — |
| TOTAL | 6 m | 5 m 38 s | **~60 s** |
| CI | 3 m 54 s | 4 m 9 s | N/A |

Sequential improved slightly (revert recovered the regression). Parallel achieved ~60 s
locally — an 88% reduction vs baseline — but was not yet available in CI.

---

## Round 5 — PBKDF2 LRU Cache + Local CI Action (commits `eae32f9`, `dc46abd`)

This was the turning point.

### Deep profiling findings

After Rounds 1–4 reduced the suite from 8 m to 5 m 38 s, the sync/ directory still
accounted for 81% of sequential time at 4 m 33 s. The snapshot pattern had reduced
per-test *fixture setup*, but the tests were still slow during their bodies.

Profiling revealed the root cause: **`_init_components()` called PBKDF2 twice per invocation,
with zero caching.**

```
_init_components(directory)
  └── _derive_keys_from_stored_key(vault_key)
        └── derive_keys_from_vault_key(vault_key)
              ├── derive_read_key()  → PBKDF2(passphrase, salt_read,  600_000 iters) ≈ 100 ms
              └── derive_write_key() → PBKDF2(passphrase, salt_write, 600_000 iters) ≈ 100 ms
```

Every vault operation — `push`, `pull`, `status`, `stash revert`, `clone` — called
`_init_components()` independently. A stash test made 3 such calls (~600 ms of PBKDF2). A
multi-clone test made ~10 calls (~2 s). The same `(passphrase, vault_id)` pair was being
re-derived from scratch on every single operation.

### The fix — 11 lines

A module-level `@functools.lru_cache` on the PBKDF2 primitive in
`sgit_ai/crypto/Vault__Crypto.py`:

```python
@functools.lru_cache(maxsize=256)
def _pbkdf2_cached(passphrase: bytes, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(algorithm  = hashes.SHA256(),
                     length     = AES_KEY_BYTES,
                     salt       = salt,
                     iterations = PBKDF2_ITERATIONS)
    return kdf.derive(passphrase)
```

`derive_key_from_passphrase` became a one-liner:

```python
def derive_key_from_passphrase(self, passphrase: bytes, salt: bytes) -> bytes:
    return _pbkdf2_cached(passphrase, salt)
```

Because both arguments are `bytes` (hashable), `lru_cache` works directly. Each unique vault
key pays the PBKDF2 cost exactly **once per process**, regardless of how many operations are
performed on that vault.

### Why it was so effective

The snapshot pattern (Rounds 1–4) attacked per-test fixture construction — the cost before
the test body ran. The PBKDF2 cache attacked per-*operation* cost that was hidden everywhere:
inside test bodies, inside snapshot restores, inside every push/pull/status call. It applied
globally to the entire codebase, not just specific test files.

### The CI fix

The CI shared action (`owasp-sbot/OSBot-GitHub-Actions/pytest__run-tests@dev`) installed
packages via `pip install -e ".[dev]"`. This silently did nothing useful because Poetry group
dependencies (`[tool.poetry.group.dev.dependencies]`) are not exposed as pip extras. So
`coverage`, `pytest-cov`, and `pytest-xdist` were all absent in CI, causing `coverage:
command not found` (exit 127).

A local action at `.github/actions/pytest__run-tests/action.yml` replaced the shared one.
It explicitly installs the tools needed and runs pytest with `-n auto`:

```bash
pip install -e . pytest pytest-cov pytest-xdist coverage
coverage run --source=sgit_ai -m pytest -v -s --durations=0 -n auto ${{ inputs.test_target }}
```

`ci-pipeline.yml` was updated to `uses: ./.github/actions/pytest__run-tests` with
`parallel: "true"`.

### Result

| Directory | Round 4 (seq) | Round 5 | Delta |
|---|---|---|---|
| cli/ | 35 s 874 ms | 19 s 658 ms | −16.2 s |
| crypto/ | 11 s 461 ms | 7 s 574 ms | −3.9 s |
| objects/ | 3 s 104 ms | 1 s 536 ms | −1.6 s |
| appsec/ | 5 s 427 ms | 2 s 564 ms | −2.9 s |
| **sync/** | **4 m 33 s** | **28 s 681 ms** | **−244 s (−89%)** |
| **TOTAL** | **5 m 38 s** | **1 m 8 s** | **−270 s (−80%)** |
| **CI #32** | **4 m 9 s** | **1 m 9 s** | **−180 s (−72%)** |

sync/ alone dropped by 89% — from 4 m 33 s to 28 s — from **one 11-line change**.

---

## Final Cumulative Results

### Local

| | Time | vs Baseline |
|---|---|---|
| Baseline | 8 m 3 s | — |
| After Round 1 | 7 m 13 s | −10% |
| After Round 2 | 5 m 57 s | −26% |
| After Round 3 | 6 m 0 s | +noise (regression) |
| After Round 4 | 5 m 38 s | −30% |
| **After Round 5** | **1 m 8 s** | **−86%** |

### CI

| Run | Description | Time | vs Baseline |
|---|---|---|---|
| #23 | Baseline | 5 m 36 s | — |
| #24 | Round 1 | 4 m 45 s | −15% |
| #25 | Round 2 | 3 m 48 s | −32% |
| #26 | Round 3 | 3 m 54 s | −30% |
| #27 | Round 4 (-n auto in addopts) | 18 s ✗ | FAILED |
| #28 | Round 4 fix | 4 m 9 s | −26% |
| **#32** | **Round 5 (PBKDF2 cache + local CI action)** | **1 m 9 s** | **−80%** |

---

## Techniques Used

### 1. Class-level snapshot-and-restore (`Vault__Test_Env`)

**When to use:** Tests that require a fully initialised vault (init + commit + push) and
perform independent read/write operations that should not bleed between tests.

**How it works:** Build once in `setup_class`. Capture state as `(filesystem_copy,
deepcopy_of_api_store)`. Each test calls `restore()` to reset to that snapshot in ~3 ms
instead of rebuilding from scratch in ~200–400 ms.

**When not to use:** Tests with lightweight init-only setups. The snapshot adds a `push()`
call that costs more than it saves if the per-test cost is already cheap.

### 2. Module-level pre-computed fixtures for expensive primitives

**When to use:** Tests that need a valid instance of an expensive object (RSA key pair,
derived PBKDF2 key) but don't care that it was freshly generated.

**How it works:** Generate once at module import time, share across all tests via module-
level variable. Tests that validate key generation itself still generate fresh keys; tests
that only need "a valid key" reuse the shared one.

**Applied to:** RSA-4096 key pairs in `test_PKI__Crypto.py`, `test_CLI__PKI.py`,
`test_PKI__Key_Store.py`; PBKDF2 master key in secrets tests.

### 3. LRU cache on deterministic expensive computations in production code

**When to use:** Any production function that is (a) deterministic, (b) expensive, and
(c) called with the same arguments multiple times within a process lifetime.

**How it works:** `@functools.lru_cache` at the module level (not instance level) keyed on
hashable arguments. Results are memoised for the lifetime of the process.

**Applied to:** `_pbkdf2_cached(passphrase: bytes, salt: bytes)` — the inner PBKDF2 call
inside `Vault__Crypto.derive_key_from_passphrase`. This is a security-safe cache because
PBKDF2 is a deterministic KDF: the same inputs always produce the same output, and the
output (the derived key bytes) is already in memory whenever it is used.

**Note:** This was the highest-leverage change of the entire optimisation effort. It
required no test refactoring at all — it was a change to production code that made the
implementation smarter, and every test in the suite benefited automatically.

### 4. Parallel test execution via pytest-xdist

**When to use:** Once per-test cost is low, parallelism is the next lever. Effective when
tests are independent (which all unit tests here are).

**How it works:** `pytest -n auto` distributes tests across CPU cores. With ~4 workers, the
~60 s sequential time drops to ~15–20 s. In CI the entire suite runs in ~1 m 9 s including
installation, coverage instrumentation, and test execution.

**Key gotcha:** The dev dependency must actually be installed. Poetry group dependencies
are not exposed as pip extras, so `pip install -e ".[dev]"` silently installs nothing.
The fix was an explicit `pip install -e . pytest pytest-cov pytest-xdist coverage` in a
local CI action.

---

## Key Insights

**Profile before optimising test structure.** The snapshot pattern (Rounds 1–4) reduced
suite time from 8 m to 5 m 38 s — a solid 30% win. But the PBKDF2 cache took the same
suite from 5 m 38 s to 1 m 8 s in one 11-line change. If we had profiled *production code*
first, we would have found the PBKDF2 issue immediately and skipped several rounds of test
refactoring.

**The best test optimisation is often a production code fix.** The snapshot pattern is a
test-layer workaround for a slow fixture. The LRU cache fixes the underlying cause — the
same expensive computation being repeated when it never needed to be. After the cache, each
test is genuinely faster because each operation is genuinely faster.

**Understand your snapshot's cost model.** `Vault__Test_Env.setup_single_vault()` runs
`init + commit + push`. Using it for tests that only needed `init()` made things worse (Round
3 regression). The pattern has a cost floor; it only saves money when what it replaces is
more expensive.

**Validate CI assumptions explicitly.** The CI shared action's failure mode was silent:
`pip install -e ".[dev]"` returned exit 0 but installed nothing extra. The symptom
(`coverage: command not found`) only appeared at test-run time. Explicit dependency lists
are safer than relying on extras that may or may not be wired up correctly.
