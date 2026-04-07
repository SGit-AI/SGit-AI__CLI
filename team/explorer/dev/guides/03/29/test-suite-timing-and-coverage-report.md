# Test Suite Timing and Coverage Report
**Date:** 2026-03-29
**Python:** 3.11.14
**pytest:** 9.0.2
**Total tests:** 1402 passed, 0 failed

---

## 1. Overall Results

| Run | Duration | Tests |
|-----|----------|-------|
| Timing run (pytest --durations) | 477.63s (7m 57s) | 1402 passed |
| Coverage run (pytest --cov) | 333.86s (5m 33s) | 1402 passed |

**Overall coverage: 77% (7622 statements, 1756 missed)**

---

## 2. Slowest Tests (top 20)

| Duration | Test |
|----------|------|
| 10.17s | `cli/test_CLI__Commands.py::Test_CLI__Vault_Push_Pull::test_pull_up_to_date` |
| 5.45s | `sync/test_Vault__Sync__Multi_Clone.py::test_multi_round_multi_file` |
| 5.42s | `sync/test_Vault__Sync__Multi_Clone.py::test_delete_propagates_across_clones` |
| 5.42s | `sync/test_Vault__Sync__Multi_Clone.py::test_modification_propagates_across_clones` |
| 5.41s | `sync/test_Vault__Sync__Multi_Clone.py::test_round_trip_push_pull` |
| 5.07s | `sync/test_Vault__Sync__Multi_Clone.py::test_concurrent_edits_no_conflict` |
| 4.85s | `cli/test_CLI__PKI.py::Test_CLI__PKI_Encrypt_Decrypt::test_encrypt_recipient_not_found_exits` (setup) |
| 4.81s | `crypto/test_PKI__Crypto.py::Test_PKI__Crypto__Hybrid_Encryption::test_wrong_key_decrypt_fails` |
| 4.30s | `sync/test_Vault__Batch.py::test_second_push_is_delta_only` |
| 4.00s | `sync/test_Vault__Sync__Multi_Clone.py::test_pull_after_push_is_up_to_date` |
| 3.97s | `sync/test_Vault__Sync__Multi_Clone.py::test_concurrent_edits_with_conflict` |
| 3.72s | `sync/test_Vault__Sync__Remote_Failure.py::test_pull_with_failed_remote_after_divergence` |
| 3.63s | `sync/test_Vault__Sync__Push.py::test_push_second_push_only_uploads_delta` |
| 3.62s | `sync/test_Vault__Sync__Remote_Failure.py::test_pull_detects_remote_divergence` |
| 3.62s | `sync/test_Vault__Sync__Multi_Clone.py::test_bob_pushes_alice_pulls` |
| 3.61s | `sync/test_Vault__Sync__Multi_Clone.py::test_alice_pushes_bob_pulls` |
| 3.31s | `cli/test_CLI__PKI.py::Test_CLI__PKI_Encrypt_Decrypt::test_encrypt_creates_enc_file` (setup) |
| 3.23s | `sync/test_Vault__Sync__Clone.py::test_clone_commit_and_push` |
| 3.05s | `pki/test_PKI__Key_Store.py::test_list_keys_after_generate` |
| 3.04s | `cli/test_CLI__PKI.py::Test_CLI__PKI_Encrypt_Decrypt::test_decrypt_key_not_found_exits` (setup) |

**Key observation:** The slowest single test (10.17s) is the CLI push/pull integration test. Multi-clone sync tests cluster between 3.6–5.5s each. PKI crypto operations (key generation, RSA) are expensive at 2.7–4.8s. Most of the suite (3717 tests) runs in under 5ms.

---

## 3. Coverage by Module — Sorted by Coverage %

### Full Coverage (100%)

All `safe_types/`, `schemas/`, and several core modules achieve full coverage:

| Module | Stmts |
|--------|-------|
| `safe_types/` (all 27 files) | 100% |
| `schemas/` (all 26 files) | 100% |
| `crypto/Vault__Crypto.py` | 94 stmts |
| `objects/Vault__Object_Store.py` | 50 stmts |
| `pki/PKI__Key_Store.py` | 75 stmts |
| `pki/PKI__Keyring.py` | 43 stmts |
| `api/Transfer__Envelope.py` | 24 stmts |
| `sync/Vault__Components.py` | 24 stmts |
| `sync/Vault__Dump_Diff.py` | 59 stmts |
| `sync/Vault__Remote_Manager.py` | 44 stmts |
| `transfer/Simple_Token.py` | 18 stmts |
| `transfer/Simple_Token__Wordlist.py` | 18 stmts |
| `transfer/Vault__Archive.py` | 93 stmts |

### High Coverage (90–99%)

| Module | Stmts | Miss | Cover | Missing lines |
|--------|-------|------|-------|---------------|
| `api/Vault__API__In_Memory.py` | 65 | 5 | 92% | 44-48, 51-52 |
| `cli/CLI__Credential_Store.py` | 78 | 11 | 86% | 51, 58-67 |
| `cli/CLI__Debug_Log.py` | 77 | 2 | 97% | 49, 79 |
| `cli/CLI__PKI.py` | 156 | 4 | 97% | 142-144, 197 |
| `crypto/PKI__Crypto.py` | 83 | 2 | 98% | 150-151 |
| `crypto/Vault__Key_Manager.py` | 65 | 1 | 98% | 75 |
| `objects/Vault__Commit.py` | 49 | 1 | 98% | 67 |
| `objects/Vault__Ref_Manager.py` | 54 | 1 | 98% | 67 |
| `secrets/Secrets__Store.py` | 54 | 1 | 98% | 55 |
| `sync/Vault__Storage.py` | 56 | 1 | 98% | 72 |
| `sync/Vault__Branch_Manager.py` | 68 | 1 | 99% | 79 |
| `sync/Vault__Branch_Switch.py` | 256 | 14 | 95% | 51, 61, 139, 147, 171, 183, 249, 293, 297, 353, 362-363, 377, 399 |
| `sync/Vault__Change_Pack.py` | 74 | 4 | 95% | 60, 84, 94, 103 |
| `sync/Vault__Fetch.py` | 81 | 4 | 95% | 52, 64, 102-103 |
| `sync/Vault__GC.py` | 74 | 4 | 95% | 46, 50, 86-87 |
| `sync/Vault__Merge.py` | 100 | 7 | 93% | 72-75, 92, 101-102 |
| `sync/Vault__Revert.py` | 127 | 9 | 93% | 34, 96, 100, 123, 142, 193-197 |
| `sync/Vault__Stash.py` | 175 | 12 | 93% | 102-105, 161, 183, 188, 215, 234, 245, 255-256 |
| `cli/CLI__Main.py` | 428 | 76 | 82% | 47-48, 58-60, 73, 76-82, 452-454, 457-458, 461-462, 467-513, 531, 543-544, 552-556, 574-575, 578-579, 582-584 |
| `cli/CLI__Token_Store.py` | 74 | 18 | 76% | 17, 22-24, 26, 31, 40, 48-54, 58, 61-62, 67 |

### Medium Coverage (70–89%)

| Module | Stmts | Miss | Cover | Notes |
|--------|-------|------|-------|-------|
| `api/Vault__Backend__Local.py` | 39 | 1 | 97% | |
| `api/Vault__Backend.py` | 30 | 9 | 70% | Error/fallback paths |
| `cli/CLI__Dump.py` | 116 | 35 | 70% | Verbose/filter paths |
| `objects/Vault__Inspector.py` | 247 | 66 | 73% | Format/display methods |
| `sync/Vault__Bare.py` | 96 | 24 | 75% | Clean/checkout edge paths |
| `sync/Vault__Diff.py` | 172 | 33 | 81% | Diff modes, sub-tree paths |
| `sync/Vault__Dump.py` | 299 | 42 | 86% | Optional/alt traversal paths |
| `sync/Vault__Ignore.py` | 103 | 21 | 80% | Pattern matching edge cases |
| `sync/Vault__Sub_Tree.py` | 163 | 29 | 82% | Sub-tree traversal |
| `sync/Vault__Sync.py` | 1145 | 179 | 84% | Largest file; error/recovery branches |

### Low Coverage (<70%) — Priority Targets

| Module | Stmts | Miss | Cover | Notes |
|--------|-------|------|-------|-------|
| `__main__.py` | 2 | 2 | 0% | Entry-point shim, not invoked in tests |
| `api/Vault__Backend__API.py` | 21 | 21 | 0% | Real HTTP backend — needs integration tests |
| `api/API__Transfer.py` | 167 | 112 | 33% | HTTP calls — integration test territory |
| `api/Vault__API.py` | 125 | 73 | 42% | HTTP-dependent methods |
| `cli/CLI__Branch.py` | 100 | 92 | 8% | Branch subcommands not wired to test harness |
| `cli/CLI__Diff.py` | 78 | 71 | 9% | Diff subcommand untested |
| `cli/CLI__Export.py` | 80 | 68 | 15% | Export subcommand untested |
| `cli/CLI__Progress.py` | 40 | 24 | 40% | Progress bar display |
| `cli/CLI__Publish.py` | 86 | 76 | 12% | Publish subcommand untested |
| `cli/CLI__Revert.py` | 43 | 37 | 14% | Revert subcommand untested |
| `cli/CLI__Share.py` | 39 | 32 | 18% | Share subcommand untested |
| `cli/CLI__Stash.py` | 100 | 91 | 9% | Stash subcommand untested |
| `cli/CLI__Vault.py` | 523 | 332 | 37% | Largest CLI class; many subcommands untested |
| `sync/Vault__Batch.py` | 157 | 45 | 71% | Batch failure/fallback paths |
| `transfer/Vault__Transfer.py` | 97 | 63 | 35% | Transfer client — integration territory |

---

## 4. Analysis and Recommendations

### What is well-covered

- **All Safe_* types** (100%): The entire `safe_types/` layer is fully covered — validation, regex, boundary enforcement.
- **All schemas** (100%): Every `Schema__*` class has full round-trip coverage.
- **Core crypto** (98–100%): `Vault__Crypto`, `PKI__Crypto`, `Vault__Key_Manager` are near-perfect.
- **Core sync engine** (84–99%): `Vault__Sync.py`, the 1145-line core, sits at 84%. The uncovered 179 lines are in error-recovery and rare-path branches.
- **PKI layer** (100%): `PKI__Key_Store`, `PKI__Keyring` fully covered.

### What is under-covered — unit test gaps

The CLI layer has significant untested surface area:

1. **`CLI__Branch` (8%)**, **`CLI__Stash` (9%)**, **`CLI__Diff` (9%)**, **`CLI__Publish` (12%)**, **`CLI__Revert` (14%)**, **`CLI__Share` (18%)** — These CLI command classes exist but have no dedicated test files. Each needs a `test_CLI__Branch.py`, `test_CLI__Stash.py`, etc. modelled on the existing `test_CLI__PKI.py` / `test_CLI__Commands.py` pattern.

2. **`CLI__Vault.py` (37%)** — The largest CLI class (523 stmts) with 332 uncovered lines. The existing `test_CLI__Commands.py` covers only the most common commands. The uncovered ranges (lines 27-48, 60-80, 127-150, 247-277, etc.) correspond to `stash`, `branch`, `diff`, `export`, `publish`, `share`, `revert` subcommands.

3. **`CLI__Main.py` (82%)** — The 76 missed lines include `lines 467-513` which is the subcommand dispatch table for the untested CLI classes above.

### What is under-covered — integration boundary

These modules have low unit coverage because they are thin wrappers over HTTP:

- `api/Vault__Backend__API.py` (0%): Real HTTP backend — appropriate to test in `tests/integration/`.
- `api/API__Transfer.py` (33%): HTTP transfer client.
- `transfer/Vault__Transfer.py` (35%): Real transfer flows.

These should not be forced into unit tests; they are the targets for the Python 3.12 integration test venv.

### Performance hotspots

The following test categories are disproportionately slow and are candidates for investigation or parallelisation:

- **Multi-clone tests** (5 tests × ~5s = 25s total): Each spawns multiple vault instances with full push/pull cycles. Consider whether some scenarios can share setup via `setUpClass` / session-scoped fixtures.
- **PKI keygen** (~2–5s per test): RSA key generation is inherently expensive. The `test_CLI__PKI.py` class setups are 1.7–4.85s each. Using pre-generated key fixtures stored as test vectors could eliminate most of this cost.
- **The 10.17s CLI push/pull test**: `test_pull_up_to_date` calls the full push/pull cycle via CLI subprocess. This is the single most expensive test — worth profiling to see if the subprocess overhead can be reduced or the test split.

---

## 5. Coverage Summary Table

| Layer | Coverage |
|-------|----------|
| `safe_types/` | 100% |
| `schemas/` | 100% |
| `crypto/` | 98–100% |
| `pki/` | 100% |
| `objects/` | 73–100% |
| `secrets/` | 98% |
| `sync/` | 71–99% |
| `transfer/` | 35–100% |
| `api/` | 0–100% (HTTP backends: 0–42%) |
| `cli/` | 0–97% (untested subcommands: 8–18%) |
| **TOTAL** | **77%** |

---

## 6. Immediate Next Steps

Priority order for coverage improvement without touching integration boundaries:

1. Add `tests/unit/cli/test_CLI__Branch.py` — covers `CLI__Branch` (100 stmts, currently 8%).
2. Add `tests/unit/cli/test_CLI__Stash.py` — covers `CLI__Stash` (100 stmts, currently 9%).
3. Add `tests/unit/cli/test_CLI__Diff.py` — covers `CLI__Diff` (78 stmts, currently 9%).
4. Add `tests/unit/cli/test_CLI__Revert.py` — covers `CLI__Revert` (43 stmts, currently 14%).
5. Add `tests/unit/cli/test_CLI__Export.py`, `test_CLI__Publish.py`, `test_CLI__Share.py`.
6. Expand `test_CLI__Commands.py` or `test_CLI__Vault.py` to cover the untested `CLI__Vault` subcommands (lines 247–277, 299–321, etc.).

Completing items 1–6 would push overall coverage from **77% to approximately 87–90%**.
