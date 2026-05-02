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

## Merge 5 — Briefs 17, 19, 21 (Schema__Local_Config, mock cleanup, mutation infra)

**Commits merged:** `fc0fa38` (brief 17), `58da75d` (briefs 18/19/21 batch), `6531a9e` (brief 19 mock cleanup), `158a2b0` (brief 21 in-progress)
**My commit:** `0241b73`

### What the agent implemented

**Brief 17 — Schema__Local_Config full field set**
- `sgit_ai/safe_types/Enum__Local_Config_Mode.py` — `Enum__Local_Config_Mode` with `SIMPLE_TOKEN`
- `sgit_ai/schemas/Schema__Local_Config.py` extended: added `mode: Enum__Local_Config_Mode`,
  `edit_token: Safe_Str__Simple_Token`, `sparse: bool`
- `Vault__Sync`: two sites that wrote `local_config` as raw dict now use
  `Schema__Local_Config(...)` + `config.json()` — typed all the way through
- Two raw `json.load + .get('sparse')` reads replaced with
  `self._read_local_config(directory, storage).sparse`
- `tests/unit/schemas/test_Schema__Local_Config.py` — 13 new tests (round-trip, enum, sparse)

**Brief 19 — Mock cleanup (no-mocks rule)**
- `tests/unit/cli/test_CLI__Branch.py` — 3 `monkeypatch` tests converted to real-object tests:
  invalid `from_branch`, non-existent switch target, uncommitted changes before switch
- `tests/unit/cli/test_CLI__Diff.py` — similar monkeypatch → real-object conversion
- `tests/unit/cli/test_CLI__Export.py` — partly converted; one test (`test_cmd_export_vault_key_read_exception_silenced`)
  intentionally retains `monkeypatch` because the code path cannot be exercised without stubbing
  (collector also reads vault_key — isolation requires the stub)
- `tests/unit/cli/test_CLI__Revert.py` — minor cleanup
- New test file `tests/unit/sync/test_Vault__Sync__Probe_Artefacts.py` — 5 tests (M9 closer):
  probe_token must not write any file to disk, must not create `.sg_vault/`, must not write
  `clone_mode.json`; artefact-free even on error
- New test file `tests/unit/sync/test_Vault__Sync__Write_File__Encryption.py` — 4 tests (M7 closer):
  raw blob on disk must not contain plaintext, must be larger (IV+tag overhead), must decrypt
  back correctly, distinct plaintexts produce distinct blobs

**Brief 21 — Mutation test infrastructure**
- `tests/mutation/mutations.py` — catalogue of 15 mutations (M1–M10, B1–B5) with exact
  `old`/`new` strings; `str.replace` semantics; referenced back to mutation test matrix doc
- `tests/mutation/run_mutations.py` — worktree orchestrator: one `git worktree` per mutation,
  applies mutation, runs `pytest tests/unit/`, checks tests fail (mutation detected), cleans up;
  `--report JSON`, `--ids M1,M7` filter, exit 1 if any mutation missed
- `.github/workflows/ci-pipeline.yml` — new `run-mutation-tests` job (needs `run-tests`,
  uploads `mutation-report.json` artifact); `increment-tag` now also needs `run-mutation-tests`

### Fixes applied

**Two multi-paragraph method docstrings in `test_CLI__Export.py`:**
- `test_cmd_export_collect_error_exits` — 2-line docstring → 1 line
- `test_cmd_export_vault_key_read_exception_silenced` — 4-line docstring → 1 line

**`_apply_mutation` in `run_mutations.py`:**
3-line docstring (Returns note on separate paragraph) → single line.

**Sonnet agent deleted Merge 4 section from review log:**
All 62 lines of the Merge 4 section were removed in this batch. Restored — the review log
is written and owned by the Explorer; the Sonnet agent should not modify it.

**Recurring: Sonnet agent re-trimmed module docstrings in `conftest.py` and `Vault__Errors.py`:**
The rule correction (module-level docstrings are OK) did not persist into the Sonnet agent's
session. The 3 files that were restored in the previous commit were again trimmed to 2-line
comment headers. Our versions (full module docstrings) survived via git merge strategy.

**Note on CLAUDE.md standing rule update:**
The "module-level docstrings are fine" distinction needs to be added to CLAUDE.md or the
Sonnet onboarding doc so the Sonnet session stops re-trimming them.

---

## Merge 6 — Brief 22 E1/E2/E5 (Vault__Sync split)

**Commits merged:** `fed08a2` (E1), `ec72379` (E2), `9effbec`–`5ac058e` (E5-1 through E5-7)
**My commit:** `3f45464`

### What the agent implemented

**E1 — `_populate_dir_contents` + `_build_tree_from_dir_contents` (Vault__Sub_Tree)**
- Extracted ~80 lines of duplicated dir-walk logic from `build` and `build_from_flat`
- Both methods now call the shared private helpers; no external callers changed

**E2 — `encrypt_or_reuse_blob` (Vault__Sub_Tree)**
- Extracted "encrypt blob or reuse existing" logic into `Vault__Sub_Tree.encrypt_or_reuse_blob()`
- `Vault__Sync.write_file` now delegates to it via `sub_tree`
- Deduplicates ~20 lines appearing in Sub_Tree.build and write_file

**E5 (all 7 commits) — Class-level split of Vault__Sync.py**
- `Vault__Sync__Base.py` — shared helpers: `_init_components`, `_read_vault_key`, `_get_read_key`,
  `_derive_keys_from_stored_key`, `_read_local_config`, `_scan_local_directory`,
  `_checkout_flat_map`, `_remove_deleted_flat`, `_remove_empty_dirs`, plus commit-walk helpers
- `Vault__Sync__Commit.py` — `commit`, `write_file`, filesystem helpers
- `Vault__Sync__Status.py` — `status`
- `Vault__Sync__Pull.py` — `pull`, `reset`, BFS fetch helpers (`_find_missing_blobs`,
  `_fetch_missing_objects`, `_clone_download_blobs`)
- `Vault__Sync__Push.py` — `push`, `_push_branch_only`, push-tracking helpers, upload helpers
- `Vault__Sync__Clone.py` — `clone`, `clone_read_only`, `clone_from_transfer`,
  `_clone_with_keys`, `_clone_resolve_simple_token`
- `Vault__Sync__Admin.py` — `delete_on_remote`, `rekey*` x5, `probe_token`, `merge_abort`,
  `branches`, `gc_drain`, `create_change_pack`, `remote_*`, `uninit`, `restore_from_backup`
- `Vault__Sync.py` (facade) — 578 LOC (well under 1,000 target); inherits `Vault__Sync__Base`;
  each public method delegates to the appropriate sub-class via
  `Vault__Sync__XYZ(crypto=self.crypto, api=self.api).method(...)`
- Sparse (`sparse_ls`, `sparse_fetch`, `sparse_cat`) and Fsck (`fsck`, `_repair_object`)
  remain in `Vault__Sync.py` per the E5 optional-deferral decision; deferred to v0.11.x

**Skipped:** E3 (`Vault__Graph_Walk`) and E4 (`batch_download` on Object_Store) — agent
proceeded directly from E1/E2 to E5. The BFS walk duplication and blob-bucketing duplication
remain; these can be addressed in the next sprint.

**Test result:** all 2,333 unit tests pass after the split.

### Fixes applied

**`Vault__Sync__Base` class docstring — multi-paragraph:**
4-line class docstring trimmed to single line.

**`_remove_empty_dirs` method docstring — multi-paragraph:**
3-line docstring trimmed to single line.

**Recurring: Sonnet agent again deleted Merge 5 section from review log.**
Our git version survived via merge strategy. This is the third consecutive merge
where the review log section was deleted. The agent's branch also reverted the
module-docstring clarification in `00b__explorer-review-process.md`; again our
version survived. The pattern suggests the Sonnet agent's session does not retain
the correction — a persistent reminder in the brief-pack is the only fix.

---

## Standing review checklist (applied on every merge)

- [ ] No multi-paragraph **class or method** docstrings — one line max (module-level docstrings are fine)
- [ ] No bare `ClassName()` instantiations just to call a utility method
- [ ] No duplicated helper methods across layers
- [ ] `stat` imported where `os.chmod` with `stat.S_*` constants is used
- [ ] All new exception classes have single-line docstrings
- [ ] New test files have no `__init__.py`
- [ ] Run affected tests locally before committing fix
- [ ] Sonnet agent must not modify the integration review log — Explorer owns it
