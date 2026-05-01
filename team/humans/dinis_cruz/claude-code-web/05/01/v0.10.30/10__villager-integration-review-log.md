# Villager Integration Review Log — v0.10.30

**Date:** May 1, 2026
**Reviewer:** Explorer agent (claude/cli-explorer-session-J3WqA)
**Source branch:** `claude/sonnet-onboarding-oMP6A`
**Target branch:** `claude/cli-explorer-session-J3WqA` → merged into `dev`

This document is updated on every merge from the sonnet-onboarding agent's
branch. It records what was reviewed, what fixes were applied, and why.

---

## Merge 1 — Briefs 10, 03-06 (shared fixtures, CI parallelization)

**Commits merged:** `7abbd25` (brief 10 chmod) and prior batch
**My commit:** `a7a50a9`

### What the agent implemented

**Brief 10 — chmod 0600 on all `.sg_vault/local/` files**
- `Vault__Storage.chmod_local_file()` helper
- Applied to every local file write in `Vault__Sync`, `CLI__Token_Store`,
  `CLI__Main`, `CLI__Share`
- `test_Vault__Sync__File_Modes.py` — 11 tests covering all paths

**Briefs 03-06 — Shared fixtures + CI parallelization**
- `tests/unit/sync/conftest.py` — F3-F6 fixtures (bare vault snapshot,
  workspace factory, probe vault env, simple token origin)
- `tests/unit/cli/conftest.py` — F1-F2 fixtures (PKI keypair snapshot,
  workdir factory)
- `pytest-xdist` two-pass in CI: parallel pass (`-n auto`, excludes
  `no_parallel`) + serial pass (`no_parallel` only, appends coverage)

### Fixes applied

**`_save_push_state` bare instantiation:**
`Vault__Storage().chmod_local_file(path)` replaced with direct `os.chmod`.
The method was instantiating a `Vault__Storage` object just to call a
4-line `chmod` wrapper — no object state needed.

**`CLI__Token_Store._chmod_local()` duplication:**
Removed the private helper method and inlined `os.chmod` directly.
`Vault__Storage.chmod_local_file()` and `CLI__Token_Store._chmod_local()`
were identical — two implementations of the same 4 lines in different layers.

**Multi-paragraph docstrings in `conftest.py` files:**
Both `tests/unit/sync/conftest.py` and `tests/unit/cli/conftest.py` had
multi-paragraph module docstrings and multi-paragraph fixture docstrings.
Replaced with single-line comments / single-line docstrings per CLAUDE.md.

---

## Merge 2 — Briefs 11, 12, 13 (secure-unlink, KDF cache, write_file guard)

**Commits merged:** `c8b1a7b` (briefs 11-13)
**My commit:** `0e0960e`

### What the agent implemented

**Brief 11 — Secure unlink (AppSec F02)**
- `Vault__Storage.secure_unlink()`: zero-overwrite + fsync before `os.unlink`
- `Vault__Storage.secure_rmtree()`: walk directory, secure-unlink each file
- `Vault__Sync.rekey_wipe()` updated to use `secure_rmtree` instead of
  `shutil.rmtree`
- `test_Vault__Sync__Secure_Unlink.py` — 19 tests

**Brief 12 — Clear KDF cache (AppSec F03)**
- `Vault__Crypto.clear_kdf_cache()` — calls `_pbkdf2_cached.cache_clear()`
- Called at passphrase boundaries: after `delete_vault`, after `rekey_wipe`,
  at all `probe_token` exit paths (success, share-found, not-found)
- `test_Vault__Crypto__KDF_Cache.py` — 3 tests

**Brief 13 — write_file guard + typed exceptions (AppSec F07/F11)**
- `sgit_ai/sync/Vault__Errors.py` — new module with `Vault__Read_Only_Error`
  and `Vault__Clone_Mode_Corrupt_Error` typed exceptions + message constants
- `write_file()` guard: raises `Vault__Read_Only_Error` when `c.write_key`
  is absent (read-only clone attempting a write)
- `_init_components` fail-closed: corrupt/missing `clone_mode.json` now raises
  `Vault__Clone_Mode_Corrupt_Error` instead of silently falling back to `{}`
  (which would grant write access to a read-only clone)
- `test_Vault__Sync__Write_File__Guard.py` — 7 tests

### Fixes applied

**`Vault__Errors.py` multi-paragraph docstrings:**
- Module-level docstring → single-line comment
- `Vault__Read_Only_Error` docstring → one line
- `Vault__Clone_Mode_Corrupt_Error` docstring → one line

**`Vault__Storage.secure_unlink/secure_rmtree` docstrings:**
Multi-paragraph rationale blocks trimmed to single-line docstrings.
The rationale (SSD TRIM residual risk, zeros vs urandom choice) is correct
and valuable — it belongs in the AppSec finding doc, not the method docstring.

**`Vault__Crypto.clear_kdf_cache` docstring:**
13-line multi-paragraph block reduced to one line.

**`Vault__Sync.rekey_wipe` docstring:**
Extended to multi-paragraph during brief 13 — trimmed back to single line.

**CI publish restricted to main only:**
Removed `should_publish_pypi` and `should_publish_dockerhub` from
`ci-pipeline__dev.yml`. Dev pushes now only increment the tag — publishing
happens exclusively on main branch pushes.

---

## Architectural decision added — Brief 21 addendum

**Doc:** `team/villager/dev/v0.10.30__brief-pack/21b__addendum-mutation-ci-architecture.md`
**My commit:** `94d5b71`

The brief-21 mutation testing plan used `git stash / git checkout --` for
reverting mutations. This is unsafe in CI:
- Python import cache (`sys.modules`) caches mutated modules across test runs
- Signal interrupts leave mutations live in the working tree

**Decision:** Mutation tests run via `git worktree` isolation — one worktree
per mutation, created from HEAD, destroyed after the run. The main checkout
is never mutated.

**New test folder structure established:**
- `tests/mutation/` — orchestrator script (not pytest), worktree-per-mutation
- `tests/appsec/` — adversarial tests (normal pytest, no mutation)

**New CI jobs scoped:**
- `run-mutation-tests` — calls `tests/mutation/run_mutations.py` directly
- `run-appsec-tests` — `pytest tests/appsec/` parallel with QA + integration

Both gate `increment-tag` so a mutation regression blocks the release.

---

## Merge 3 — Brief 14 (delete-on-remote clears push_state)

**Commit merged:** `37d6260`
**My commit:** `88936c0`

### What the agent implemented

**Brief 14 — delete_on_remote bug fix**
- `delete_on_remote` was leaving `push_state.json` alive after vault deletion
- Bug: next push to a fresh vault with the same ID would skip Phase-A blob
  uploads (thinking blobs already uploaded) while Phase-B uploaded
  commits/trees referencing those blobs → dangling references on server
- Fix: 2 lines — call `self._clear_push_state(storage.push_state_path(directory))`
  immediately after `api.delete_vault()` succeeds
- `test_Vault__Sync__Delete_Push_State.py` — 4 tests (precondition, fix
  verification, end-to-end, re-push after delete uploads blobs fresh)

### Fixes applied

**Multi-paragraph module docstring in test file:**
19-line module docstring trimmed to single comment line. The bug description
belongs in the debrief doc and the architect finding, not the test module.

---

## Merge 4 — Briefs 15, 18, 20 + Schema typed objects

**Commits merged:** `7c1b26d` (brief 15), `6ccf76d` (brief 20), `697d11f` (brief 18), `6fcf5f5` (self-fix)
**My commit:** `79ef16b`

### What the agent implemented

**Brief 15 — Schema__Push_State (typed push_state.json)**
- `sgit_ai/safe_types/Enum__Clone_Mode.py` — new `Enum__Clone_Mode` with `READ_ONLY` / `FULL`
- `sgit_ai/schemas/Schema__Clone_Mode.py` — typed schema: `mode`, `vault_id`, `read_key`
- `sgit_ai/schemas/Schema__Push_State.py` — typed schema: `vault_id`, `clone_commit_id`,
  `blobs_uploaded: list[Safe_Str__Object_Id]`
- `Vault__Sync._load_push_state()` refactored: now deserializes via `Schema__Push_State.from_json()`
  instead of raw dict, with vault_id + clone_commit_id mismatch guard unchanged
- `Vault__Sync._save_push_state()` refactored: writes `state.json()` instead of a raw dict
- `_init_components` already using `Schema__Clone_Mode` (carried from brief 13)
- `tests/unit/schemas/test_Schema__Push_State.py` — 11 tests (round-trip, M8 field drop)
- `tests/unit/schemas/test_Schema__Clone_Mode.py` — 11 tests (round-trip, enum serialization,
  invalid-enum load failure, extra-field drop)

**Brief 18 — API + Vault__Diff coverage (QA)**
- `tests/unit/api/test_API__Transfer__Coverage.py` — 27 tests: `setup()`, `_auth_headers()`,
  `_api_error()`, URL construction, `_upload_large()` error paths (no real HTTP)
- `tests/unit/api/test_Vault__API.py` — 41 tests: `batch_read()` chunking + fallback,
  `list_files()` normalisation (exercised via In_Memory)
- `tests/unit/api/test_Vault__Backend__API.py` — 23 tests: `Vault__Backend__API` via In_Memory,
  no real HTTP calls
- `tests/unit/sync/test_Vault__Diff__Coverage.py` — 23 tests: `diff_vs_commit()`,
  `diff_commits()`, `show_commit()`, `log_file()`, `_unified_diff()` + `_build_result()` edge
  cases, large `diff_files()` sets — all real on-disk vaults

**Brief 20 — Determinism + cross-vault divergence vectors (crypto)**
- `tests/unit/crypto/test_Vault__Crypto__Deterministic.py` — 20 tests: M1 cross-vault
  divergence, M2 hard-coded HMAC key guard, M3 IV derivation property
  (IV = HMAC-SHA256(key, plaintext)[:12])
- `tests/unit/objects/test_Vault__Sub_Tree__Determinism.py` — 7 tests: same-file-map +
  same-read_key → same tree-id; same map + different key → different tree-id

**Self-fix by Sonnet agent (commit `6fcf5f5`)**
- `test_Vault__Sync__Write_File__Guard.py`: read-only clone_mode fixture was using an
  invalid string for `Safe_Str__Write_Key` (too short). Updated to use a valid 64-hex-char key.
  Agent self-corrected this after brief-15 typed the schema.

### Fixes applied

**`_save_push_state` bare instantiation — reintroduced:**
Brief 15 rewrote `_save_push_state` with the new `Schema__Push_State` signature but
re-introduced `Vault__Storage().chmod_local_file(path)` — the same bare-instantiation
pattern fixed in merge 1. Replaced again with direct `os.chmod` (with `stat` already imported).

**Multi-paragraph module docstrings — all 8 new test files:**
- `test_Schema__Push_State.py` — 7-line multi-paragraph docstring → single comment line
- `test_Schema__Clone_Mode.py` — 8-line multi-paragraph docstring → single comment line
- `test_API__Transfer__Coverage.py` — 6-line docstring → single comment line
- `test_Vault__API.py` — 6-line docstring → single comment line
- `test_Vault__Backend__API.py` — 3-line docstring → single comment line
- `test_Vault__Crypto__Deterministic.py` — 6-line docstring → single comment line
- `test_Vault__Sub_Tree__Determinism.py` — 5-line docstring → single comment line
- `test_Vault__Diff__Coverage.py` — 11-line docstring → single comment line

---

## Standing review checklist (applied on every merge)

- [ ] No multi-paragraph docstrings or multi-line comment blocks
- [ ] No bare `ClassName()` instantiations just to call a utility method
- [ ] No duplicated helper methods across layers
- [ ] `stat` imported where `os.chmod` with `stat.S_*` constants is used
- [ ] All new exception classes have single-line docstrings
- [ ] New test files have no `__init__.py`
- [ ] Run affected tests locally before committing fix
