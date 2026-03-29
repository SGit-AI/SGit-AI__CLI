# Test Coverage Improvement Plan

**Date:** 2026-03-29
**Current state:** 1 425 unit tests · 77% coverage · 53s CI (parallel)
**Goal:** >90% coverage · integration tests in CI · QA scenarios formalized

---

## 1. Current Test Landscape

### 1.1 Test tiers

| Tier | Location | Tests | Runs in CI | Server needed |
|------|----------|-------|-----------|---------------|
| Unit | `tests/unit/` | 1 425 | Yes (53s) | No — `Vault__API__In_Memory` |
| Integration | `tests/integration/` | ~40 | **No** | Yes — `sgraph-ai-app-send` (Python 3.12+) |
| QA / Scenario | `tests/qa/` | ~40 | **No** (`--ignore=tests/qa`) | Mixed |

The integration and QA tiers exist but are invisible to CI.

### 1.2 Integration tests (what they do)

Three files, all using a real `sgraph-ai-app-send` HTTP server started via a session-scoped pytest fixture (`conftest.py::send_server`). If `sgraph-ai-app-send` is not installed the tests skip automatically.

| File | Focus |
|------|-------|
| `test_Vault__Integration.py` | Key derivation determinism, API read/write, crypto round-trip |
| `test_Vault__Batch__Integration.py` | Batch write/delete/list, push delta, change pack + GC drain |
| `test_Vault__Local_Server.py` | Full init/commit/push/pull/status lifecycle against real HTTP |

### 1.3 QA / Scenario tests (what they do)

| File | Focus | Server |
|------|-------|--------|
| `test_QA__Scenario_1__Solo_Workflow.py` | Alice solo: init → commit → push → clone → pull | In-memory |
| `test_QA__Scenario_2__Two_User_Collab.py` | Alice + Bob: concurrent edits, conflict, deletion propagation | In-memory |
| `test_QA__Vault_Init_Walkthrough.py` | Step-by-step init, bare structure inspection | In-memory |
| `test_QA__Vault_Walkthrough.py` | Full lifecycle with manual step markers | Requires local server port 18321 |

Scenarios 1, 2, and Init Walkthrough already use `Vault__API__In_Memory` — they can run in CI without any external server.

---

## 2. Current Coverage Gaps

### 2.1 CLI layer — the biggest gap

Overall CLI coverage: **~52%**. Eight modules are essentially untested:

| Module | Coverage | Missing stmts | Uncovered area |
|--------|----------|--------------|----------------|
| `CLI__Branch.py` | 8% | 92 | cmd_list, cmd_new, cmd_switch, cmd_delete |
| `CLI__Diff.py` | 9% | 71 | cmd_diff, cmd_diff_remote |
| `CLI__Stash.py` | 9% | 91 | cmd_stash, cmd_stash_pop, cmd_stash_drop, cmd_stash_list |
| `CLI__Publish.py` | 12% | 76 | All publish/upload commands |
| `CLI__Revert.py` | 14% | 37 | cmd_revert |
| `CLI__Export.py` | 15% | 68 | cmd_export, cmd_import |
| `CLI__Share.py` | 18% | 32 | cmd_share |
| `CLI__Vault.py` | ~37% | 332 | cmd_clone, cmd_pull, cmd_push, cmd_status, cmd_log, cmd_branch |

Total CLI missing: **~799 statements**.

### 2.2 API layer

| Module | Coverage | Missing stmts | Notes |
|--------|----------|--------------|-------|
| `Vault__Backend__API.py` | 0% | 21 | Live HTTP backend — needs integration |
| `API__Transfer.py` | 33% | 112 | Upload, download, batch, presigned URL |
| `Vault__API.py` | 42% | ~73 | Base class methods |

### 2.3 Sync layer (remaining gaps)

| Module | Coverage | Missing stmts |
|--------|----------|--------------|
| `Vault__Transfer.py` (transfer/) | 44% | 63 |
| `Vault__Batch.py` | 71% | 45 |
| `Vault__Bare.py` | 75% | 24 |
| `Vault__Ignore.py` | 80% | 21 |
| `Vault__Diff.py` | 81% | 33 |
| `Vault__Dump.py` | 86% | 42 |
| `Vault__Sync.py` | 85% | 183 |

---

## 3. Improvement Rounds

### Round 1 — Small CLI modules (Revert, Diff, Share, Stash)

**Target:** 4 modules totalling ~291 missing statements at 9–18% coverage.
**Approach:** Unit tests using `Vault__Test_Env` snapshot for vault state +
`argparse.Namespace` to fake CLI args — no real HTTP, no subprocess.
**Files to create:**
- `tests/unit/cli/test_CLI__Revert.py` — revert to previous commit, revert to HEAD
- `tests/unit/cli/test_CLI__Diff.py` — diff working vs HEAD, diff remote
- `tests/unit/cli/test_CLI__Share.py` — share new token, share with existing token, rotate
- `tests/unit/cli/test_CLI__Stash.py` — stash, pop, drop, list, stash-on-clean-tree

**Expected gain:** +250 covered statements, CLI 52% → ~62%

---

### Round 2 — CLI__Branch + CLI__Vault core commands

**Target:** The two largest CLI gaps — 92 + 332 missing statements.
**Files to create:**
- `tests/unit/cli/test_CLI__Branch.py` — list, new, switch, delete, current-branch display
- `tests/unit/cli/test_CLI__Vault__Push.py` — cmd_push normal, delta, nothing-to-push
- `tests/unit/cli/test_CLI__Vault__Pull.py` — cmd_pull up-to-date, behind, conflict
- `tests/unit/cli/test_CLI__Vault__Status.py` — cmd_status clean/dirty/staged
- `tests/unit/cli/test_CLI__Vault__Clone.py` — cmd_clone simple-token, vault:// URL, plain path
- `tests/unit/cli/test_CLI__Vault__Log.py` — cmd_log with/without depth, formatted output

**Expected gain:** +320 covered statements, CLI 62% → ~78%

---

### Round 3 — Vault__Transfer unit tests

**Target:** `Vault__Transfer.py` at 44% (63 missing). The transfer layer is the bridge between vault operations and the SG/Send API. It is already tested at the integration level but not at the unit level.
**Approach:** Use `Vault__API__In_Memory` to stand in for the real API. Test:
- `share(vault_dir)` — creates transfer, encrypts payload, uploads, returns URL
- `receive(token_str)` — downloads blob, decrypts, unzips, returns file dict
- Large file handling, empty vault handling, re-share idempotency

**File to create:** `tests/unit/transfer/test_Vault__Transfer__Unit.py`

**Expected gain:** +50 covered statements, transfer/ 72% → ~90%

---

### Round 4 — Sync layer edge cases (Batch, Bare, Ignore, Diff, Dump)

**Target:** Fill the remaining sync gaps that weren't addressed by earlier optimisation rounds.

| File | Missing | Test focus |
|------|---------|-----------|
| `Vault__Sync.py` | 183 | Error paths in push/pull/merge/clone/archive/export; conflict detection edge cases |
| `Vault__Batch.py` | 45 | Batch size limits, retry logic, partial failure |
| `Vault__Bare.py` | 24 | Bare checkout error paths (lines 66–92, 101, 112) |
| `Vault__Ignore.py` | 21 | Edge cases: negation patterns, directory-only patterns, glob anchoring |
| `Vault__Diff.py` | 33 | Binary file diff, deleted file diff, renamed file diff |
| `Vault__Dump.py` | 42 | Format/render branches in dump output methods |

**Files to create:** extend existing test files + targeted new files for Sync error paths.

**Expected gain:** +300 covered statements, sync/ 85% → ~92%, overall 77% → ~84%

---

### Round 5 — Integration tests in CI

**Target:** Run the existing `tests/integration/` suite in CI.
**Current blocker:** Integration tests require `sgraph-ai-app-send` (Python 3.12+). The
current CI is Python 3.11.
**Approach:**
1. Add a second CI job in `.github/actions/` or a new workflow that:
   - Uses Python 3.12
   - Installs `pip install -e ".[dev]" sgraph-ai-app-send`
   - Runs `pytest tests/integration/ -v`
2. Gate this job on the unit tests passing first.
3. Mark as `continue-on-error: false` — integration failures should block merge.

**New files:**
- `.github/workflows/ci-integration.yml` (or add a job to `ci-pipeline.yml`)

**Expected gain:** 40 integration tests running in CI, catching real HTTP/server regressions automatically.

---

### Round 6 — QA Scenarios in CI

**Target:** Run the three in-memory QA scenarios (`Scenario_1`, `Scenario_2`,
`Vault_Init_Walkthrough`) in CI as a "scenario" tier.
**Current blocker:** `--ignore=tests/qa` in `addopts`.
**Approach:**
1. Remove `test_QA__Vault_Walkthrough.py` from the in-CI set (it requires an external
   server on port 18321 and is a manual walkthrough script by design).
2. Create a `tests/qa/conftest_ci.py` marker or a pytest mark (`@pytest.mark.qa`) so
   the three in-memory scenarios can be run with `pytest -m qa tests/qa/`.
3. Add a third CI job (or extend the unit job) to run the qa subset.

**New files:**
- Update `tests/qa/test_QA__Scenario_1__Solo_Workflow.py` — add `@pytest.mark.qa`
- Update `tests/qa/test_QA__Scenario_2__Two_User_Collab.py` — add `@pytest.mark.qa`
- Update `tests/qa/test_QA__Vault_Init_Walkthrough.py` — add `@pytest.mark.qa`
- Update `ci-pipeline.yml` or new workflow to run `pytest -m qa tests/qa/`

**Expected gain:** ~100 scenario tests in CI, catching end-to-end regression in solo + collaborative workflows.

---

## 4. Projected Coverage After All Rounds

| Area | Now | R1 | R2 | R3 | R4 | R5+R6 |
|------|-----|----|----|----|----|-------|
| CLI | 52% | 62% | 78% | 78% | 80% | 80% |
| API | 53% | 53% | 53% | 53% | 55% | **80%** (integration) |
| sync/ | 87% | 87% | 87% | 87% | 92% | 92% |
| transfer/ | 72% | 72% | 72% | 90% | 90% | 90% |
| **Overall** | **77%** | **79%** | **83%** | **84%** | **87%** | **~91%** |

---

## 5. CI Architecture After All Rounds

```
PR / push to dev or main
│
├── [Job 1] Unit tests (Python 3.11, parallel)    ~53s
│   pytest tests/unit/ -n auto
│
├── [Job 2] Integration tests (Python 3.12)        ~60s
│   pytest tests/integration/ -v
│   requires: sgraph-ai-app-send
│
└── [Job 3] QA scenarios (Python 3.11, in-memory)  ~30s
    pytest -m qa tests/qa/
    (excludes Vault_Walkthrough — manual only)
```

All three jobs must pass for a merge to be allowed.

---

## 6. Priority Order

| Priority | Round | Effort | Coverage gain | Risk |
|----------|-------|--------|--------------|------|
| 1 | Round 1 — Small CLI modules | Low (4 files) | +250 stmts | Low |
| 2 | Round 5 — Integration in CI | Medium (1 workflow) | Real HTTP coverage | Low |
| 3 | Round 6 — QA scenarios in CI | Low (mark + workflow) | 100 scenario tests | Low |
| 4 | Round 2 — CLI__Branch + Vault | High (6 files) | +320 stmts | Medium |
| 5 | Round 3 — Vault__Transfer unit | Medium (1 file) | +50 stmts | Low |
| 6 | Round 4 — Sync edge cases | High (many files) | +300 stmts | Medium |

Rounds 5 and 6 (CI pipeline expansion) are high-leverage because they bring already-written tests into the automated safety net. They should happen in parallel with or before the unit coverage rounds.
