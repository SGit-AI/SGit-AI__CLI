# Test Performance and Coverage Analysis

**Generated:** 2026-03-29
**Test suite:** `tests/unit/` — 1 402 tests, all passing
**Total wall time (coverage run):** 264.85 s (4 m 25 s)
**Total wall time (timing-only run):** 258 s
**Python:** 3.11.14, pytest 9.0.2

---

## 1. Executive Summary

- **sync/ dominates runtime:** The sync directory accounts for ~69 % of all measured test time (181.6 s out of 264 s), driven by tests that spin up full in-memory vault lifecycles (init → commit → push → clone) for every single test method via `setup_method`.
- **CLI PKI setup is the single most expensive per-test overhead:** `Test_CLI__PKI_Encrypt_Decrypt` and `Test_CLI__PKI_Sign_Verify` each generate one or two RSA-4096 key pairs in `setup_method`, costing ~2.5–4.5 s per test.
- **Multi-clone integration tests are the slowest individual tests:** `Test_Vault__Sync__Multi_Clone` runs full Alice-and-Bob init/commit/push/clone sequences per test, with 9 of the 20 slowest individual tests living there.
- **Code coverage is 77 % overall, with two strongly polarised groups:** schema, safe_types, crypto, pki, and secrets are at or near 100 %; while cli/ (52 %), api/ (53 %), and transfer/ (72 %) are significantly under-covered.
- **Several CLI command modules are nearly untested:** `CLI__Branch` (8 %), `CLI__Diff` (9 %), `CLI__Stash` (9 %), `CLI__Publish` (12 %), `CLI__Revert` (14 %), `CLI__Export` (15 %), and `CLI__Share` (18 %) together represent 526 statements with fewer than 80 covered.

---

## 2. Test Timing — Top 20 Slowest Individual Tests

Source: `pytest --durations=50` run (561 s wall time including all 1 402 tests).

| Rank | Time   | Phase  | Test |
|------|--------|--------|------|
| 1    | 7.07 s | call   | `test_Vault__Sync__Multi_Clone::test_modification_propagates_across_clones` |
| 2    | 7.00 s | call   | `test_Vault__Sync__Multi_Clone::test_delete_propagates_across_clones` |
| 3    | 6.85 s | call   | `test_Vault__Sync__Multi_Clone::test_multi_round_multi_file` |
| 4    | 6.70 s | call   | `test_Vault__Sync__Multi_Clone::test_round_trip_push_pull` |
| 5    | 6.50 s | call   | `test_Vault__Sync__Multi_Clone::test_concurrent_edits_no_conflict` |
| 6    | 5.79 s | call   | `test_Vault__Batch::test_second_push_is_delta_only` |
| 7    | 5.18 s | call   | `test_Vault__Sync__Multi_Clone::test_concurrent_edits_with_conflict` |
| 8    | 5.00 s | call   | `test_Vault__Sync__Multi_Clone::test_pull_after_push_is_up_to_date` |
| 9    | 4.77 s | call   | `test_PKI__Key_Store::test_list_keys_after_generate` |
| 10   | 4.68 s | call   | `test_PKI__Crypto__PEM::test_wrong_passphrase_fails` |
| 11   | 4.64 s | call   | `test_Vault__Sync__Multi_Clone::test_bob_pushes_alice_pulls` |
| 12   | 4.55 s | **setup** | `test_CLI__PKI_Encrypt_Decrypt::test_encrypt_then_decrypt` |
| 13   | 3.98 s | call   | `test_Vault__Sync__Multi_Clone::test_alice_pushes_bob_pulls` |
| 14   | 3.89 s | call   | `test_Vault__Sync__Clone::test_clone_commit_and_push` |
| 15   | 3.86 s | call   | `test_Vault__Batch::test_push_uses_individual_when_use_batch_false` |
| 16   | 3.82 s | call   | `test_Vault__Batch::test_push_uses_batch_api` |
| 17   | 3.80 s | call   | `test_PKI__Crypto__PEM::test_export_import_private_key_with_passphrase` |
| 18   | 3.71 s | call   | `test_Vault__Sync__Push::test_push_second_push_only_uploads_delta` |
| 19   | 3.70 s | call   | `test_Vault__Batch::test_push_fallback_to_individual_when_batch_fails` |
| 20   | 3.69 s | call   | `test_Vault__Batch::test_push_batch_includes_write_if_match` |

**Observation:** 9 of the top 20 are in `test_Vault__Sync__Multi_Clone`. Ranks 12 and 25 have the phase `setup`, meaning the cost is entirely in `setup_method` before the test body runs — a sign of expensive fixture construction.

---

## 3. Test Timing — By File and Directory

### 3a. Per-file totals (all phases: call + setup + teardown)

Files with all tests under 0.005 s (safe_types, schemas, most objects/api files) are shown as `< 0.1 s` — their contribution is negligible.

| File (tests/unit/…) | Total time |
|---|---|
| `sync/test_Vault__Sync__Multi_Clone.py` | **23.83 s** |
| `sync/test_Vault__Stash.py` | **19.09 s** |
| `cli/test_CLI__PKI.py` | **18.63 s** |
| `sync/test_Vault__Branch_Switch.py` | **17.79 s** |
| `sync/test_Vault__Sync__Push.py` | **14.17 s** |
| `sync/test_Vault__Sync__Clone.py` | **13.65 s** |
| `crypto/test_PKI__Crypto.py` | **12.53 s** |
| `sync/test_Vault__Dump.py` | **10.87 s** |
| `transfer/test_Vault__Archive.py` | **10.23 s** |
| `sync/test_Vault__Sync__Remote_Failure.py` | **9.78 s** |
| `sync/test_Vault__Revert.py` | **9.44 s** |
| `sync/test_Vault__Batch.py` | **8.99 s** |
| `sync/test_Vault__Sync__Uninit.py` | **8.41 s** |
| `cli/test_CLI__Commands.py` | **8.31 s** |
| `sync/test_Vault__Sync__Commit.py` | **6.15 s** |
| `sync/test_Vault__Bare.py` | **6.10 s** |
| `pki/test_PKI__Key_Store.py` | **6.00 s** |
| `objects/test_Vault__Inspector__Coverage.py` | **5.64 s** |
| `sync/test_Vault__Sync__Pull.py` | **5.29 s** |
| `sync/test_Vault__Sync__Status.py` | **4.86 s** |
| `sync/test_Vault__Batch__Large_Blob.py` | **4.84 s** |
| `sync/test_Vault__Sync__Fsck.py` | **4.46 s** |
| `crypto/test_Vault__Crypto.py` | **4.28 s** |
| `cli/test_CLI__Dump.py` | **4.07 s** |
| `sync/test_Vault__GC.py` | **4.06 s** |
| `secrets/test_Secrets__Store__Edge_Cases.py` | **3.18 s** |
| `secrets/test_Secrets__Store.py` | **2.89 s** |
| `sync/test_Vault__Sync__Helpers.py` | **2.24 s** |
| `appsec/test_AppSec__Vault_Security.py` | **2.18 s** |
| `sync/test_Vault__Sync__Init.py` | **2.05 s** |
| `sync/test_Vault__Dump_Diff.py` | **2.04 s** |
| `sync/test_Vault__Diff.py` | **1.82 s** |
| `sync/test_Vault__Sync__Init__Bare.py` | **1.66 s** |
| `cli/test_CLI__Credential_Store.py` | **1.40 s** |
| `transfer/test_Simple_Token.py` | **1.07 s** |
| `crypto/test_PKI__Crypto__Hardening.py` | **0.57 s** |
| `crypto/test_Vault__Crypto__Hardening.py` | **0.44 s** |
| `objects/test_Vault__Inspector.py` | **0.40 s** |
| `crypto/test_Vault__Crypto__Structure_Key.py` | **0.22 s** |
| `transfer/test_Vault__Transfer.py` | **0.18 s** |
| All safe_types/ files (74 tests) | **< 0.1 s total** |
| All schemas/ files (115 tests) | **< 0.1 s total** |
| All api/ files (41 tests) | **< 0.1 s total** |

### 3b. Per-directory totals

| Directory | Total time | % of suite | Test files |
|---|---|---|---|
| `sync/` | **181.6 s** | 68.8 % | 30 files |
| `cli/` | **32.4 s** | 12.3 % | 8 files |
| `crypto/` | **18.0 s** | 6.8 % | 6 files |
| `transfer/` | **11.5 s** | 4.3 % | 4 files |
| `secrets/` | **6.1 s** | 2.3 % | 2 files |
| `objects/` | **6.0 s** | 2.3 % | 6 files |
| `pki/` | **6.0 s** | 2.3 % | 2 files |
| `appsec/` | **2.2 s** | 0.8 % | 1 file |
| `safe_types/`, `schemas/`, `api/` | **< 0.5 s total** | < 0.2 % | 96 files |

**Note:** The 3 721 tests whose individual times are under 0.005 s (reported as hidden by pytest) account for an estimated 15–20 s, spread across safe_types, schemas, objects, api, and fast cli tests. Even with those added, `sync/` remains by far the dominant cost.

---

## 4. Expensive Test Classes — What Makes Them Slow

### Pattern A: Full vault lifecycle per test (init + commit + push ± clone)

These classes use `setup_method` or a `_VaultFixture.__init__` helper that calls `Vault__Sync.init()` (and sometimes `push()` or `clone()`) for every test. The overhead is the full vault initialisation: key derivation, directory layout creation, crypto operations, and in-memory API setup.

| Test class | File | Pattern | Approx setup cost/test |
|---|---|---|---|
| `Test_Vault__Sync__Multi_Clone` | `test_Vault__Sync__Multi_Clone.py` | `init` + `commit` + `push` + `clone` (two actors) per test body | ~0.5 s setup + 3–7 s body |
| `Test_Vault__Batch` | `test_Vault__Batch.py` | `_init_vault()` helper calls `init` + `commit` + `push` per test | ~0.4 s + 3–6 s body |
| `Test_Vault__Sync__Push` | `test_Vault__Sync__Push.py` | `_init_and_push()` calls `init` + `commit` + `push` per test | ~0.4 s + 2–4 s body |
| `Test_Vault__Sync__Clone` | `test_Vault__Sync__Clone.py` | `_init_and_push()` then `clone()` per test | ~0.4 s + 2–4 s body |
| `Test_Vault__Sync__Remote_Failure` | `test_Vault__Sync__Remote_Failure.py` | `_init_and_push()` per test | ~0.4 s + 3 s body |
| `Test_Vault__Stash` (via `_VaultFixture`) | `test_Vault__Stash.py` | `init()` in `_VaultFixture.__init__` — 26 tests | ~0.2 s setup each |
| `Test_Vault__Revert` (via `_VaultFixture`) | `test_Vault__Revert.py` | `init()` in `_VaultFixture.__init__` — 15 tests | ~0.2 s setup each |
| `Test_Vault__Branch_Switch` (via `_VaultFixture`) | `test_Vault__Branch_Switch.py` | `init()` in `_VaultFixture.__init__`, some tests also call `push()` | ~0.2–0.4 s setup each |

### Pattern B: RSA-4096 key generation per test (PKI tests)

These test classes call `generate_and_store()` or `generate_encryption_key_pair()` + `generate_signing_key_pair()` in `setup_method`, which runs RSA-4096 key generation (inherently expensive).

| Test class | File | Setup operation | Approx cost per test |
|---|---|---|---|
| `Test_CLI__PKI_Encrypt_Decrypt` | `test_CLI__PKI.py` | Two `generate_and_store()` calls (sender + receiver) | 2.5–4.5 s in **setup** |
| `Test_CLI__PKI_Sign_Verify` | `test_CLI__PKI.py` | One `generate_and_store()` call | ~2.5 s in **setup** |
| `Test_CLI__PKI_Import_Contacts` | `test_CLI__PKI.py` | Two raw `generate_encryption_key_pair()` + `generate_signing_key_pair()` | ~0.5 s in **setup** |
| `Test_PKI__Key_Store` | `test_PKI__Key_Store.py` | `generate_and_store()` in per-test bodies | 0.4–4.8 s per test body |
| `Test_PKI__Crypto__PEM` | `test_PKI__Crypto.py` | RSA-4096 key ops per test body | 3.8–4.7 s per test body |

### Pattern C: PBKDF2 / AES-GCM per test (Vault__Crypto, secrets)

Vault__Crypto and Secrets__Store tests invoke PBKDF2 key derivation per test. Each call is ~0.2–0.4 s, giving `test_Vault__Crypto.py` a 4.28 s total and `test_Secrets__Store__Edge_Cases.py` a 3.18 s total.

### Pattern D: Vault__Archive encryption per test (transfer)

`test_Vault__Archive.py` (10.23 s) calls AES-GCM encrypt/decrypt in every test. With 57 tests each doing ~0.35–0.43 s of crypto work, this adds up quickly.

---

## 5. Code Coverage — By Directory

Coverage measured with `pytest --cov=sgit_ai --cov-report=term-missing`. Total: **77 %** (5 871 / 7 622 statements).

| Module directory | Coverage % | Statements | Missing | Notes |
|---|---|---|---|---|
| `safe_types/` | **100 %** | 444 | 0 | Fully tested |
| `schemas/` | **100 %** | 367 | 0 | Fully tested |
| `pki/` | **100 %** | 118 | 0 | Fully tested |
| `secrets/` | **98.1 %** | 54 | 1 | Near-complete |
| `crypto/` | **98.8 %** | 242 | 3 | Near-complete |
| `objects/` | **83.0 %** | 400 | 68 | Good; `Vault__Inspector` has 66 missing |
| `sync/` | **87.0 %** | 3 273 | 424 | Good but large surface; `Vault__Sync` alone has 174 missing |
| `transfer/` | **72.1 %** | 226 | 63 | `Vault__Transfer` has 63 missing (35 % coverage) |
| `api/` | **53.1 %** | 471 | 221 | Two files near-zero; `API__Transfer` 33 %, `Vault__API` 42 % |
| `cli/` | **52.1 %** | 2 023 | 969 | Many CLI command classes untested |

---

## 6. Code Coverage — Lowest and Highest Coverage Modules

### 6a. Ten lowest-coverage modules (by statement coverage %)

| Coverage % | Module | Statements | Missing | Key uncovered areas |
|---|---|---|---|---|
| **0 %** | `sgit_ai/__main__.py` | 2 | 2 | Entry-point guard (`if __name__ == '__main__'`) — never invoked directly |
| **0 %** | `sgit_ai/api/Vault__Backend__API.py` | 21 | 21 | Live HTTP backend — entire file uncovered |
| **8 %** | `sgit_ai/cli/CLI__Branch.py` | 100 | 92 | `cmd_list`, `cmd_new`, `cmd_switch`, `cmd_delete` — all command bodies |
| **9 %** | `sgit_ai/cli/CLI__Diff.py` | 78 | 71 | `cmd_diff`, `cmd_diff_remote` — all command bodies |
| **9 %** | `sgit_ai/cli/CLI__Stash.py` | 100 | 91 | `cmd_stash`, `cmd_stash_pop`, `cmd_stash_drop`, `cmd_stash_list` |
| **12 %** | `sgit_ai/cli/CLI__Publish.py` | 86 | 76 | All publish/upload command bodies |
| **14 %** | `sgit_ai/cli/CLI__Revert.py` | 43 | 37 | `cmd_revert` command body |
| **15 %** | `sgit_ai/cli/CLI__Export.py` | 80 | 68 | `cmd_export`, `cmd_import` command bodies |
| **18 %** | `sgit_ai/cli/CLI__Share.py` | 39 | 32 | `cmd_share` command body |
| **33 %** | `sgit_ai/api/API__Transfer.py` | 167 | 112 | Upload, download, batch, presigned URL methods |

### 6b. Ten highest-coverage modules (non-trivial files only)

| Coverage % | Module | Statements | Missing |
|---|---|---|---|
| **100 %** | `sgit_ai/sync/Vault__Archive.py` (transfer) | 93 | 0 |
| **100 %** | `sgit_ai/sync/Vault__Dump_Diff.py` | 59 | 0 |
| **100 %** | `sgit_ai/sync/Vault__Remote_Manager.py` | 44 | 0 |
| **100 %** | `sgit_ai/sync/Vault__Components.py` | 24 | 0 |
| **100 %** | `sgit_ai/transfer/Simple_Token.py` | 18 | 0 |
| **100 %** | `sgit_ai/transfer/Simple_Token__Wordlist.py` | 18 | 0 |
| **100 %** | `sgit_ai/crypto/Vault__Crypto.py` | 94 | 0 |
| **100 %** | `sgit_ai/pki/PKI__Key_Store.py` | 75 | 0 |
| **100 %** | `sgit_ai/pki/PKI__Keyring.py` | 43 | 0 |
| **98 %** | `sgit_ai/crypto/PKI__Crypto.py` | 83 | 2 |

### 6c. Significant uncovered functions/methods (large missing-line blocks)

| Module | Missing lines | Uncovered area |
|---|---|---|
| `sgit_ai/cli/CLI__Vault.py` | 332 | Majority of CLI command implementations: `cmd_clone`, `cmd_pull`, `cmd_push`, `cmd_status`, `cmd_diff`, `cmd_log`, `cmd_branch`, and several subcommand handlers |
| `sgit_ai/sync/Vault__Sync.py` | 174 | Error-path branches in `push`, `pull`, `merge`, `clone`; the `archive` and `export` flows; conflict detection edge cases |
| `sgit_ai/api/API__Transfer.py` | 112 | All live HTTP methods: `upload_object`, `download_object`, `batch_write`, `presigned_url_*` |
| `sgit_ai/api/Vault__API.py` | 73 | `Vault__API` base class — all concrete methods |
| `sgit_ai/cli/CLI__Branch.py` | 92 | Entire branch management CLI (list, new, switch, delete) |
| `sgit_ai/cli/CLI__Stash.py` | 91 | Entire stash CLI (stash, pop, drop, list) |
| `sgit_ai/objects/Vault__Inspector.py` | 66 | Formatting methods for `cat-object`, `inspect tree`, `inspect log` output paths |
| `sgit_ai/sync/Vault__Bare.py` | 24 | Bare vault checkout and clean error paths (lines 66–92, 101, 112) |
| `sgit_ai/sync/Vault__Dump.py` | 42 | Several format/render branches in dump output methods |
| `sgit_ai/cli/CLI__Progress.py` | 24 | All progress-bar rendering (terminal output code) |

---

## 7. Recommendations for Optimisation

Based purely on the timing and coverage data above — no implementation changes suggested.

### 7.1 Test speed — sync/ directory (highest priority)

**Issue:** `Test_Vault__Sync__Multi_Clone`, `Test_Vault__Batch`, `Test_Vault__Sync__Push`, and `Test_Vault__Sync__Clone` each call a full `init → commit → push → [clone]` sequence inside every test body or as a per-test helper. With 9 tests in Multi_Clone alone costing 3–7 s each, this class is responsible for ~24 s out of the suite's ~258 s.

**Option A — Class-scoped fixture:** Share the vault initialisation once per class using `@classmethod` + `setup_class` or a `pytest` session/module-scoped fixture. Tests that only read state (not mutate) can share the fixture safely.

**Option B — Split test classes:** Separate read-only assertions from mutating scenarios. The former can share a pre-built fixture; the latter need isolation but could be smaller in number.

**Option C — Lighter fixture for setup-heavy tests:** Tests in `Test_Vault__Stash` and `Test_Vault__Revert` only need `sync.init()` (no push/clone). They currently pay ~0.2 s per test × 26/15 tests. A module-scoped fixture that initialises once would reduce this to a single 0.2 s cost.

### 7.2 Test speed — CLI__PKI (second priority)

**Issue:** `Test_CLI__PKI_Encrypt_Decrypt` and `Test_CLI__PKI_Sign_Verify` generate RSA-4096 key pairs in `setup_method`, costing 2.5–4.5 s per test in the **setup phase** alone. This is the source of the `setup` entries visible in the top-20 slowest list.

**Option:** Generate the key pair once at the class level (or use a pre-generated test fixture key in PEM form) and share it across all tests in the class. RSA key generation cost is proportional to key size; a pre-computed fixture would eliminate this entirely from the hot path.

### 7.3 Test speed — PKI__Crypto and PKI__Key_Store

**Issue:** `test_PKI__Crypto.py` has individual tests taking 3.4–4.7 s because RSA-4096 key generation happens inside the test body itself (e.g. `test_wrong_passphrase_fails`, `test_export_import_private_key_with_passphrase`). `test_PKI__Key_Store.py::test_list_keys_after_generate` costs 4.77 s.

**Option:** Provide a module-level or session-scoped pre-generated key-pair fixture and share it across tests that only need a valid key rather than a freshly generated one. Only tests explicitly validating key-generation behaviour need a fresh key.

### 7.4 Test speed — transfer/Vault__Archive

**Issue:** `test_Vault__Archive.py` (57 tests, 10.23 s total) does AES-GCM encrypt/decrypt for every test at ~0.35–0.43 s each. The crypto work is fast but accumulates.

**Option:** Group tests that use the same plaintext/key inputs into one test (or parametrize) so the encryption setup is done once and multiple assertions are checked against the same output.

### 7.5 Code coverage — CLI command classes

**Issue:** Eight CLI command classes have coverage below 20 %. These are not untestable — the sync logic they wrap is thoroughly covered. The gap is specifically the CLI adapter layer (argument parsing, output formatting, error-exit paths).

**Suggested focus order** (by statement count × coverage gap):
1. `CLI__Vault.py` — 332 missing (37 % covered): highest absolute gap
2. `CLI__Branch.py` — 92 missing (8 %): entire class untested
3. `CLI__Stash.py` — 91 missing (9 %): entire class untested
4. `CLI__Diff.py` — 71 missing (9 %): entire class untested
5. `CLI__Export.py` — 68 missing (15 %): entire class untested

### 7.6 Code coverage — API layer

**Issue:** `API__Transfer.py` (33 %) and `Vault__API.py` (42 %) are under-covered because live HTTP paths are exercised only in integration tests. `Vault__Backend__API.py` is 0 % covered (21 statements).

**Option:** Integration tests already exist in `tests/integration/`. Ensuring the integration test suite exercises the full API client surface would close this gap without requiring mocks (which the project's critical rules prohibit).

### 7.7 Code coverage — transfer/Vault__Transfer

**Issue:** `Vault__Transfer.py` is at 35 % (63 missing statements). The uncovered lines (33–98) are the upload, download, and transfer lifecycle methods. These likely require a live or in-memory transfer server.

**Option:** The existing `Vault__API__In_Memory` pattern used in sync tests may be applicable here — verify whether `Vault__Transfer` can be exercised with the same in-memory backend before routing this to integration tests.

---

## 8. Optimisation Round 1 — Results (2026-03-29)

Commit `5d9db08`: class-level vault snapshots via `Vault__Test_Env` helper.

### 8.1 What was changed

- **New:** `tests/unit/sync/vault_test_env.py` — `Vault__Test_Env` with `setup_single_vault()`, `setup_two_clones()`, `restore()` (shutil.copytree + copy.deepcopy(api._store), ~3 ms per test)
- **Modified:** `test_Vault__Sync__Multi_Clone`, `test_Vault__Sync__Clone`, `test_Vault__Sync__Push`, `test_Vault__Sync__Remote_Failure`, `test_Vault__Stash`, `test_Vault__Branch_Switch` — all switched from per-test `setup_method` init to class-level snapshot + per-test restore
- **Modified:** `test_CLI__PKI` — RSA-4096 key pairs generated once in `setup_class`, key directory copied per test

### 8.2 Measured results

#### Local (developer machine)

| Directory  | Before       | After        | Delta       |
|------------|-------------|-------------|-------------|
| api/       | 14 ms       | 41 ms       | +27 ms      |
| appsec/    | 6 s 269 ms  | 4 s 710 ms  | −1.6 s      |
| **cli/**   | **32 s 764 ms** | **42 s 526 ms** | **+9.8 s** |
| crypto/    | 23 s 862 ms | 22 s 861 ms | −1 s        |
| objects/   | 13 s 951 ms | 15 s 105 ms | +1.2 s      |
| pki/       | 6 s 988 ms  | 7 s 734 ms  | +0.7 s      |
| safe_types/| 0 ms        | 0 ms        | —           |
| schemas/   | 1 ms        | 1 ms        | —           |
| secrets/   | 14 s 668 ms | 13 s 901 ms | −0.8 s      |
| **sync/**  | **6 m 19 s**| **5 m 20 s**| **−59 s**   |
| transfer/  | 5 s 657 ms  | 5 s 791 ms  | +0.1 s      |
| **TOTAL**  | **8 m 3 s** | **7 m 13 s**| **−50 s (−10 %)** |

#### CI pipeline (GitHub Actions)

| Run  | Commit   | Time     |
|------|----------|----------|
| #23 (before) | `31fea03` | 5 m 36 s |
| #24 (after)  | `45f1af1` | 4 m 45 s |
| **Delta** | | **−51 s (−15 %)** |

### 8.3 Notes

- **sync/ saved 59 s** as expected — the class-level snapshot pattern worked.
- **cli/ regressed by +10 s** — caused by 22 new Simple Token tests added in the same sprint, not by the optimisation itself. The PKI class-level fix did not cause harm; the new tests added real work.
- **CI saved proportionally more (15 %) than local (10 %)** — CI has less available parallelism, so per-test setup overhead is more impactful there.
- The 51 % reduction claimed by the agent was measured in its isolated worktree environment and does not reflect the full suite including new tests.

---

## 9. Optimisation Round 2 — Results (2026-03-29)

Commit `55a0b93`: 7 more sync files + crypto RSA fixtures + secrets PBKDF2 fixtures.

### 9.1 What was changed

- **sync/:** Applied `Vault__Test_Env` snapshot pattern to `test_Vault__Batch`, `test_Vault__Sync__Pull`, `test_Vault__Sync__Commit`, `test_Vault__Dump`, `test_Vault__Revert`, `test_Vault__GC`, `test_Vault__Sync__Uninit`
- **crypto/:** 4 RSA-4096 + EC key pairs generated at module level in `test_PKI__Crypto.py`; shared by all tests that just need "a valid key"
- **secrets/:** PBKDF2 master key derived once at module level in `test_Secrets__Store.py` + `test_Secrets__Store__Edge_Cases.py`; monkey-patched per test

### 9.2 Measured results

#### Local (developer machine)

| Directory  | Round 1      | Round 2      | Delta       |
|------------|-------------|-------------|-------------|
| api/       | 41 ms       | 28 ms       | −13 ms      |
| appsec/    | 4 s 710 ms  | 4 s 772 ms  | +0.1 s      |
| cli/       | 42 s 526 ms | 38 s 302 ms | −4.2 s      |
| **crypto/**| **22 s 861 ms** | **13 s 18 ms** | **−9.8 s** |
| objects/   | 15 s 105 ms | 14 s 512 ms | −0.6 s      |
| pki/       | 7 s 734 ms  | 6 s         | −1.7 s      |
| safe_types/| 0 ms        | 0 ms        | —           |
| schemas/   | 1 ms        | 1 ms        | —           |
| **secrets/**| **13 s 901 ms** | **1 s 634 ms** | **−12.3 s** |
| **sync/**  | **5 m 20 s**| **4 m 32 s**| **−48 s**   |
| transfer/  | 5 s 791 ms  | 6 s 51 ms   | +0.3 s      |
| **TOTAL**  | **7 m 13 s**| **5 m 57 s**| **−76 s (−18 %)** |

#### CI pipeline (GitHub Actions)

| Run  | Commit   | Time     | Delta from baseline |
|------|----------|----------|---------------------|
| #23 (baseline) | `31fea03` | 5 m 36 s | — |
| #24 (Round 1)  | `45f1af1` | 4 m 45 s | −51 s (−15 %) |
| #25 (Round 2)  | `51fc947` | 3 m 48 s | −108 s (−32 %) |

### 9.3 Cumulative results (baseline → Round 2)

| Directory  | Baseline     | Round 2      | Total delta  |
|------------|-------------|-------------|--------------|
| cli/       | 32 s 764 ms | 38 s 302 ms | +5.5 s*      |
| crypto/    | 23 s 862 ms | 13 s 18 ms  | −10.8 s      |
| secrets/   | 14 s 668 ms | 1 s 634 ms  | **−13.0 s**  |
| sync/      | 6 m 19 s    | 4 m 32 s    | **−107 s**   |
| **TOTAL**  | **8 m 3 s** | **5 m 57 s**| **−126 s (−26 %)** |
| **CI**     | **5 m 36 s**| **3 m 48 s**| **−108 s (−32 %)** |

*cli/ increase due to 22 new Simple Token tests added in the same sprint.

### 9.4 Standout wins

- **secrets/: −12.3 s (−88%)** — PBKDF2 fixture eliminated almost all derivation overhead
- **crypto/: −9.8 s (−43%)** — RSA module-level pre-generation removed the heaviest single tests
- **sync/: −107 s cumulative** — class-level snapshots across 13 test files total

---

## 10. Optimisation Round 3 — Remaining Targets

Post-Round-2 profile: **sync/ still 76% of total at 4 m 32 s**.

### 10.1 sync/ — 4 m 32 s (many files still unoptimised)

Files not yet touched by the snapshot pattern:

| File | Estimated time | Notes |
|------|---------------|-------|
| `test_Vault__Bare.py` | ~6 s | Per-test bare vault creation |
| `test_Vault__Sync__Helpers.py` | ~2 s | Init per test |
| `test_Vault__Sync__Status.py` | ~5 s | Init per test |
| `test_Vault__Sync__Fsck.py` | ~4 s | Init + fsck per test |
| `test_Vault__Change_Pack.py` | ~3 s | Init per test |
| `test_Vault__Diff.py` | ~2 s | Init per test |
| `test_Vault__Merge.py` | ~4 s | Init per test |
| `test_Vault__Fetch.py` | ~3 s | Init per test |

Potential saving: **~29 s** from applying snapshot pattern.

### 10.2 objects/ — 14 s

`test_Vault__Inspector__Coverage.py` builds full vault structures per test (12 tests, ~5.6 s). `test_Vault__Object_Store.py` and `test_Vault__Commit.py` also do per-test init. Snapshot pattern would save ~**8 s**.

### 10.3 pki/ — 6 s

`Test_PKI__Key_Store::test_list_keys_after_generate` is ~5 s alone (RSA keygen in body). Module-level pre-generated key fixture would save ~**4 s**.

### 10.4 Projected Round 3 savings

| Area | Target saving |
|------|--------------|
| sync/ remaining files | −25 to −30 s |
| objects/ snapshot | −8 s |
| pki/ RSA fixture | −4 s |
| **Total projected** | **−37 to −42 s** |

Post Round 3 estimated total: **~5 m 15 s → ~5 m** locally, **~3 m 10 s** CI.
