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

## Standing review checklist (applied on every merge)

- [ ] No multi-paragraph docstrings or multi-line comment blocks
- [ ] No bare `ClassName()` instantiations just to call a utility method
- [ ] No duplicated helper methods across layers
- [ ] `stat` imported where `os.chmod` with `stat.S_*` constants is used
- [ ] All new exception classes have single-line docstrings
- [ ] New test files have no `__init__.py`
- [ ] Run affected tests locally before committing fix
