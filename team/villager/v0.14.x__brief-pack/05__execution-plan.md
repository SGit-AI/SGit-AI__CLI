# v0.14.x Execution Plan — Briefs 01–04

**Date:** 2026-05-06
**Branch:** `claude/review-v0.14-brief-pack-crcB7`
**Based on:** task description + codebase analysis (see §1.0 for why)

---

## 1. Review Findings

### 1.0 Critical: Brief Pack Files Not Committed

`team/villager/v0.14.x__brief-pack/00__index.md` through `04__*.md` do not exist on
`dev` or any other ref. This plan is derived from the task description and direct codebase
reading. Before a Dev agent begins implementation, Dinis must commit the actual briefs so
the agent can verify paths, method names, and acceptance criteria against the source of truth.
All findings below marked "from task description" are inferred, not verified against brief text.

---

### 1.1 Brief 01 — CLI Token Rename

**From task description:** "small CLI rename"

`--token` is registered **five times** in `sgit_ai/cli/CLI__Main.py` with inconsistent
help strings: `"SG/Send access token"` (L103, global flag) vs `"Access token"` (L271,
L329, L402, L446, per-subcommand). All five `add_argument` calls must be updated
atomically. Every downstream caller uses `getattr(args, 'token', None)` — a mechanical
grep-and-replace — but it touches `CLI__Vault.py`, `CLI__Share.py`, `CLI__Export.py`,
`CLI__Publish.py`, and `CLI__Token_Store.py`.

**Gap:** Without the brief text I cannot confirm what exactly is being renamed (the
argparse flag name? the `args.token` attribute? the `CLI__Token_Store` method names?).
See Q1 in §3.

**Type_Safe compliance:** No violations expected — the rename lives in the argparse
layer, not in Type_Safe classes.

---

### 1.2 Brief 04 — Vault Backup/Restore Commands

**From task description:** new commands `sgit vault backup`, `vault restore`,
`vault backups`.

**Existing code the brief must reuse (not duplicate):**

- `Vault__Sync__Lifecycle.uninit()` at `sgit_ai/core/actions/lifecycle/Vault__Sync__Lifecycle.py:132–169`
  already creates `.vault__{name}__{timestamp}.zip` backups — but is **destructive**: it
  calls `shutil.rmtree(sg_dir)` at L164. A standalone `backup` command must extract only
  the zip-creation half. Extract a private `_create_backup_zip(directory, target_dir=None)`
  helper from `uninit()` and expose it as a public `backup()` method. Do NOT create a
  separate `Vault__Backup.py`; the logic belongs in `Vault__Sync__Lifecycle` alongside
  `uninit()` and `restore_from_backup()`.

- `Vault__Sync__Lifecycle.restore_from_backup()` at L171–210 already handles restoration.
  It is exposed via `sgit init --restore` (CLI__Main.py:146–147). The new `vault restore`
  command wraps this same method; no new core logic is required.

**Missing edge cases not covered by the brief's §3b description:**

1. `restore_from_backup()` raises a bare `RuntimeError` at L182: `"Vault already exists
   in {directory} — remove .sg_vault/ first"`. The `vault restore` UX should catch this
   and print an actionable hint: `"hint: run 'sgit vault uninit' first to back up and
   remove the existing vault"`.
2. `vault backups` must resolve its search scope: does it scan only the current directory
   or recursively? The zip naming convention (`.vault__*__*.zip`) must be documented in
   help text because it is non-obvious.
3. The backup zip write is already atomic (written to `io.BytesIO` then flushed at L153)
   — this is correct behavior; no change needed.

**Brief 02 §5d / §4a file-location ambiguity (from task description):** Do not create
`Vault__Backup.py` or `Vault__Restore.py`. The backup primitive brief 02 step 7 needs is
`Vault__Sync__Lifecycle._create_backup_zip()` — already in the lifecycle class. Confirm
this with Dinis (Q2).

**Type_Safe compliance:** Return dicts from `backup()` and `list_backups()` are
acceptable as plain `dict` for CLI surface. If the brief introduces
`Schema__Vault_Backup`, it must pass the round-trip invariant before use.

---

### 1.3 Brief 02 — Vault Move

**From task description:** `sgit vault move` — transactional rotation + server move;
step 7 consumes the backup primitive from brief 04.

**No move logic exists.** Closest pattern: `Vault__Sync__Lifecycle.rekey()` at L84–91,
which does wipe → rekey_init → rekey_commit but stays on the **same** vault_id on the
server. Move requires a different vault_id: new init under a new key, push to a new remote
vault_id, then delete the old vault_id from the server.

**Proposed sequence for `move(directory, new_vault_key=None)`:**

1. Read-only guard: raise immediately if no `write_key` (mirrors `delete_on_remote()` L19).
2. Clean-state check: raise or warn if uncommitted changes exist (see Q4).
3. Capture `old_vault_id` from local config (before any wipe).
4. `backup(directory)` — safety net before destruction (brief 04 primitive).
5. `rekey_wipe(directory)` — remove `.sg_vault/`.
6. `rekey_init(directory, new_vault_key)` — new vault_id derived from new key.
7. `rekey_commit(directory)` — re-encrypt all working files under new key.
8. `push(directory)` — upload to new vault_id on server.
9. `delete_on_remote(directory)` using `old_vault_id` — **only if `--delete-old` flag
   is set** (see Q3 and proposed change in §3).
10. Return `{old_vault_id, new_vault_id, backup_path, commit_id}`.

**Transactional boundary gap:** Steps 5–7 are destructive and non-atomic. If step 8
(push) fails, the local vault has already been wiped and re-inited. Recovery requires
restoring the backup from step 4. This must be documented in user-facing error output:
`"Push failed. Your vault backup is at: {backup_path}. Run 'sgit init --restore {backup_path}' to recover."`.

**Missing edge cases:**

1. **Post-delete partial failure:** If step 9 (`delete_on_remote`) fails after a
   successful push, the user has two live vault_ids on the server. Log a warning with the
   old_vault_id so the user can manually run `vault delete-on-remote` on it.
2. **`--yes` flag required:** The move is more destructive than `rekey`. It must require
   `--yes` or interactive confirmation before step 5, matching `rekey` and
   `delete-on-remote` UX.
3. **Local config update:** after step 8, `.sg_vault/local/config.json` contains the
   new vault_id; no explicit helper is needed — `rekey_init` calls `Vault__Sync.init()`
   which writes fresh config. Verify this is correct before implementing.

**Layer compliance:** `Vault__Sync__Lifecycle` is in the `core` layer — correct. No
new KNOWN_VIOLATIONS introduced. A workflow (`Workflow__Move`) is not warranted for this
scope; the sequential method calls in `Vault__Sync__Lifecycle.move()` are sufficient.
Confirm no import from `cli` into `core` (watch `CLI__Input` prompt calls — these must
stay in `CLI__Vault.cmd_move()`, not in `move()`).

**Type_Safe compliance:** `move()` return dict is plain `dict`. Any
`Schema__Vault_Move_State` the brief introduces must use `Safe_*` field types, not raw
`str` or `dict`.

---

### 1.4 Brief 03 — Vault Move Testing

**From task description:** "comprehensive test matrix for vault move"

**`Vault__Test_Env` is sufficient** for all realistic move scenarios. The in-memory API
store is keyed by vault_id (`Vault__API__In_Memory._store`), so old_vault_id and
new_vault_id can coexist in one test session. `setup_single_vault()` is the right fixture
for move tests; `setup_two_clones()` is not needed.

**Test scenarios that require care:**

- **Mid-push failure simulation:** Cannot be done without either (a) making
  `Vault__API__In_Memory` support call-count-based failure injection, or (b) restructuring
  the test to verify the recovery invariant rather than the failure itself. Option (b) is
  preferred to avoid mocks: verify that after a simulated incomplete push state, calling
  `restore_from_backup()` with the backup from step 4 yields a working vault.
- **Concurrent API reads during move:** Not testable with in-memory API; flag as deferred.

**KNOWN_VIOLATIONS:** No new violations expected. Move tests belong in
`tests/unit/core/actions/lifecycle/` to match the existing pattern for lifecycle tests.

---

## 2. Execution Plan

### Landing Order

Confirmed: **01 → 04 → 02 → 03**

Brief 04's `_create_backup_zip()` helper must land before brief 02 step 4 can call it.
Brief 02's `move()` method must land before brief 03's extended test matrix targets it.

---

### Brief 01 — CLI Token Rename

**Estimated effort:** ½ day

**Commit 1:** `fix(cli): rename token argument — <old-name> → <new-name> across all parsers`
- Modified: `sgit_ai/cli/CLI__Main.py` — all 5 `add_argument` calls + standardize
  help strings to one consistent description
- Modified: `sgit_ai/cli/CLI__Vault.py`, `CLI__Share.py`, `CLI__Export.py`,
  `CLI__Publish.py` — all `getattr(args, 'token', None)` → `getattr(args, '<new_name>', None)`
- Modified: `sgit_ai/cli/CLI__Token_Store.py` — if method names are changing

**Reviewer Fix pass**

**Commit 2:** `test(cli): update tests for token argument rename`
- Modified: any test in `tests/unit/cli/` that constructs `Namespace(token=...)` or
  passes `--token`

---

### Brief 04 — Vault Backup/Restore Commands

**Estimated effort:** 1 day

**Commit 1:** `feat(lifecycle): extract backup() and list_backups() from uninit()`
- Modified: `sgit_ai/core/actions/lifecycle/Vault__Sync__Lifecycle.py`
  - Extract `_create_backup_zip(directory, target_dir=None) -> str` (zip path) from
    `uninit()` — zip creation only, no rmtree
  - Add `backup(directory, target_dir=None) -> dict` public method
  - Add `list_backups(directory) -> list[dict]` method (sorted by mtime descending)
  - Refactor `uninit()` to call `_create_backup_zip()` (no behavior change)

**Commit 2:** `feat(cli): add vault backup / restore / backups subcommands`
- Modified: `sgit_ai/cli/CLI__Vault.py` — add `cmd_backup(args)`, `cmd_restore(args)`,
  `cmd_backups(args)`
- Modified: `sgit_ai/cli/CLI__Main.py` — register subparsers `vault backup`,
  `vault restore`, `vault backups` under the existing `vault` subparser

**Reviewer Fix pass**

**Commit 3:** `test(lifecycle): backup, restore, and list_backups tests`
- New: `tests/unit/core/actions/lifecycle/test_Vault__Sync__Lifecycle__Backup.py`
  - `test_backup_creates_zip_without_destroying_sg_vault` — backup, assert `.sg_vault/`
    still present
  - `test_backup_to_custom_target_dir` — zip lands in specified directory
  - `test_restore_into_fresh_directory` — backup + rmtree `.sg_vault/` + restore,
    assert vault_id matches and files are accessible
  - `test_restore_raises_if_sg_vault_exists` — restore into existing vault, assert
    helpful error message with `sgit vault uninit` hint
  - `test_list_backups_sorted_by_timestamp` — create 2 backups, assert newest is first

---

### Brief 02 — Vault Move

**Estimated effort:** 1.5 days

**Commit 1:** `feat(lifecycle): add Vault__Sync__Lifecycle.move() — transactional vault move`
- Modified: `sgit_ai/core/actions/lifecycle/Vault__Sync__Lifecycle.py`
  - Add `move(directory, new_vault_key=None, delete_old=False) -> dict`
  - Must capture `old_vault_id` before any wipe
  - Must call `backup()` (brief 04 primitive) before `rekey_wipe()`
  - Must print recovery path in all failure branches

**Commit 2:** `feat(cli): add vault move subcommand`
- Modified: `sgit_ai/cli/CLI__Vault.py` — add `cmd_move(args)`
- Modified: `sgit_ai/cli/CLI__Main.py` — register `vault move` with `--new-key`,
  `--yes`, `--delete-old`, `--json` flags

**Reviewer Fix pass**

**Commit 3:** `test(lifecycle): happy-path and guard tests for vault move`
- New: `tests/unit/core/actions/lifecycle/test_Vault__Sync__Lifecycle__Move.py`
  - `test_move_happy_path` — move completes; new_vault_id in API store, old_vault_id
    absent (when `delete_old=True`), local config reflects new vault_id
  - `test_move_backup_persists_after_move` — backup zip from step 4 is not deleted by
    the move itself
  - `test_move_requires_write_access` — read-only clone raises before any mutation
  - `test_move_without_delete_old_leaves_old_vault_live` — `delete_old=False`; assert
    both vault_ids present in API store

**Commit 4:** `test(lifecycle): partial-failure and recovery for vault move`
- Additions to `test_Vault__Sync__Lifecycle__Move.py`:
  - `test_move_recovery_from_backup_after_push_failure` — after a failed move (simulate
    by using a vault with an already-closed API store post-wipe), verify that
    `restore_from_backup(backup_path)` produces a valid vault matching the pre-move state
  - `test_move_warns_on_delete_failure` — patch `delete_on_remote` to raise; assert the
    return dict contains `old_vault_id` and that the warning message includes it. (Note:
    no mock of the API — use `delete_old=True` on a vault_id that was never pushed to the
    API, so the delete_on_remote raises naturally from a 404-equivalent.)

---

### Brief 03 — Vault Move Test Matrix

**Estimated effort:** ½ day

**Commit 1:** `test(lifecycle): comprehensive move test matrix (brief 03)`
- New: `tests/unit/core/actions/lifecycle/test_Vault__Move__Matrix.py`
  - `test_move_multi_round_invariant` — move A→B, then B→C; assert C has same file
    content as A
  - `test_move_with_20_files` — larger file set to exercise object-store behavior
  - `test_move_with_explicit_new_vault_key` — supply a known vault_key and assert the
    new vault_id is deterministic
  - `test_move_concurrent_reads_deferred` — placeholder test documenting the deferred
    concurrent-read scenario with a `pytest.mark.skip` and rationale

**Test execution order (brief 03 §7):** All lifecycle move tests run in a single pytest
session in this order (by file, then by definition order within each file):
1. `test_Vault__Sync__Lifecycle__Move.py` — guards, happy path, partial failure
2. `test_Vault__Move__Matrix.py` — multi-round invariants, edge cases

No prescribed `pytest` ordering markers needed; definition order within each file is
sufficient.

---

## 3. Questions and Proposed Changes

### Open Questions for Dinis

**Q1 (blocking — Brief 01):** What is the exact rename? Options:
(a) `--token` flag → `--sg-send-token` (breaking UX change for existing scripts),
(b) `--token` flag → `--access-token` (less breaking, more generic),
(c) rename of `CLI__Token_Store` methods only (no CLI flag change).
Impact ranges from 15-minute find-replace to a ½-day coordinated change.

**Q2 (Brief 04):** Should `vault backup` write the zip into the vault directory
(matching `uninit()` behavior, so backups accumulate alongside working files) or require
`--target-dir`? If in the vault directory, `vault backups` and the default `vault restore`
UX are simpler. If `--target-dir`, more flexible but adds a required argument.

**Q3 (Brief 02 §8 — open question in brief):** Should `vault move` delete the old vault
from the server by default or only with an explicit `--delete-old` flag? **Recommendation:
require `--delete-old`.** Auto-delete is irreversible. Separating the copy phase (move)
from the cleanup phase (delete-old) gives users a safety window to verify the new vault
works before destroying the old one.

**Q4 (Brief 02):** Should `vault move` require a clean vault (no uncommitted changes)?
`rekey_commit()` re-encrypts all working-directory files, so uncommitted changes would be
silently included in the new vault. **Recommendation: require clean state** (run `status`
check before step 5 and abort with a clear message) to avoid surprising users.

**Q5 (Brief 03 §4 — multi-round invariants):** Confirming my interpretation: the
invariant is that `content(vault_C) == content(vault_A)` after `move(A→B)` then
`move(B→C)`, where content is the set of decrypted file paths and bytes. Is there an
additional invariant about commit history being preserved across the move?

### Proposed Changes to the Briefs

**Brief 01:** Standardize the five help strings to `"SG/Send API access token"` during
the rename pass regardless of which flag name is chosen.

**Brief 04 §3b:** Specify that `vault restore` must catch the existing RuntimeError from
`restore_from_backup()` when `.sg_vault/` already exists and print:
`"error: vault already exists in {directory}. Run 'sgit vault uninit' first to back up and remove it."`.

**Brief 04 §4a:** Do not create `Vault__Backup.py` or `Vault__Restore.py`. Keep all
logic in `Vault__Sync__Lifecycle`. The brief likely specifies separate files to separate
concerns, but the concerns are already co-located with `uninit()` and the backup zip
logic — splitting adds import surface without benefit.

**Brief 02 §5 (transactional boundary):** Add to the brief: "on any failure after step 5
(rekey_wipe), the error output must include the backup_path so the user can recover without
forensic investigation." This is a user-trust requirement, not just a nice-to-have.

**Brief 02 §8 open questions:** My recommendations are captured in Q3 and Q4 above:
require `--delete-old`, require clean state before move begins.

**Brief 03 §7 test order:** Confirmed as: guards → happy path → partial failure →
multi-round invariants. No change needed if the brief matches this order.
