# v0.14.x Execution Plan — Briefs 01–04

**Date:** 2026-05-06 (updated after reading actual briefs + server tombstone spec)
**Branch:** `claude/review-v0.14-brief-pack-crcB7`
**Status:** Brief 01 DONE. Briefs 04 → 02 → 03 ready for Dev agent.

---

## Status

| Brief | Status | Commit |
|---|---|---|
| 01 — `--token` → `--as` rename | ✅ DONE | `012f765` + Reviewer Fix 8 (`8c79d60`) |
| 04 — `vault backup / restore / backups` | Pending | — |
| 02 — `vault move` | Pending | — |
| 03 — vault move test matrix | Pending | — |

Landing order: **04 → 02 → 03**. Brief 04's `Vault__Backup` class is consumed by Brief 02's
Step 7; it must land first.

---

## 1. Review Findings

### 1.1 Brief 01 — DONE

Landed exactly as specified. `vault share --as`, `vault export --as`, `share publish --as`
(all with `dest='share_as'`). Each command also has a separate `--token` for the access
credential. 8 tests in `tests/unit/cli/test_CLI__As_Flag.py`. No issues.

---

### 1.2 Brief 04 — Vault Backup/Restore

**Architecture the brief calls for** (§4a):

```
sgit_ai/core/actions/backup/
├── __init__.py
├── Vault__Backup.py          # zip creation + sha256 sidecar + manifest
└── Vault__Restore.py         # validation, extraction, expanded mode

sgit_ai/workflow/backup/
├── __init__.py
├── Workflow__Vault_Backup.py
├── Workflow__Vault_Restore.py
├── Backup__Workspace.py
├── Restore__Workspace.py
└── steps/
    ├── Step__Backup__Build_Zip.py
    ├── Step__Restore__Validate_Destination.py
    ├── Step__Restore__Verify_Zip_Integrity.py
    ├── Step__Restore__Extract_Bare.py
    ├── Step__Restore__Resolve_Vault_Key.py
    └── Step__Restore__Extract_Working_Copy.py

sgit_ai/schemas/backup/
├── __init__.py
└── Schema__Backup_Manifest.py
```

**Reuse opportunity — `uninit()` already has zip logic:**
`Vault__Sync__Lifecycle.uninit()` at `sgit_ai/core/actions/lifecycle/Vault__Sync__Lifecycle.py:132–169`
already builds the backup zip atomically (BytesIO buffer, then flush). `Vault__Backup`
should extract and extend this logic rather than re-implement. The `uninit()` method
should be refactored to call `Vault__Backup` instead of inline zip code.

**Gaps the brief doesn't fully specify:**

- Default output dir is `.sg_vault/backups/` (brief §2a step 3) — this is a new
  subdirectory; the Dev agent must create it on first use.
- `vault restore` §3b rule 2: "no vault in any parent path" — walk up from destination
  looking for `.sg_vault/`; this is non-trivial and must be tested explicitly.
- `Step__Restore__Extract_Working_Copy` (§3e step 5) — brief says "reuses the existing
  `Step__Clone__Extract_Working_Copy` logic." The Dev agent must find that step in
  `sgit_ai/workflow/clone/` and import it; do not duplicate the code.
- `Schema__Backup_Manifest` (§4b) must pass the Type_Safe round-trip invariant. Fields
  `schema_version`, `vault_id`, `key_generation`, `created_at`, `created_by`, `label`,
  `includes_key`, `object_count`, `byte_size` — all must use `Safe_*` types, not raw
  `str`/`int`.
- The brief's §5d integration with the move test suite references `tests/qa/sync/test_Vault__Move__Multi_Round.py` —
  this file is created by Brief 03, not Brief 04. Wire the integration after Brief 03 lands.

**Type_Safe compliance:** Brief explicitly calls for `Schema__Backup_Manifest`; this is
the only new schema. CLI handlers return plain `dict`; that is acceptable.

---

### 1.3 Brief 02 — Vault Move

**Key design insight (brief §2):** Object IDs stay stable across rotation. The filename
`obj-cas-imm-abc123` keeps its name; only the ciphertext changes (re-encrypted under new
key). All cross-references remain valid. The `id == hash(ciphertext)` CAS invariant is
deliberately broken for the rotation boundary. This is intentional.

**New primitives required:**

- `Vault__Object_Store.store_at(object_id, content, force=False)` (brief §5a) — write
  specific bytes to a specific object ID without re-hashing. Default no-overwrite; pass
  `force=True` for rotation. Lives in `sgit_ai/storage/Vault__Object_Store.py`. Needs its
  own test file.
- `sgit_ai/core/actions/move/Vault__Sync__Move.py` (brief §5b) — new action class with
  `move(directory, new_vault_key, target_api_url, reason)`.
- `Workflow__Vault_Move` + 8 step classes (brief §5c).
- `Schema__Vault_Move_Record` + `Schema__Vault_Moves` (brief §4b pattern).

**⚠️ Critical step-ordering correction (tombstone server spec):**

Brief 02 §5c Step 8 as written says: "Call the source-server API to delete the old
vault-id. Replace the local working `.sg_vault/` with `.sg_vault_new/`..." —
**this order is wrong.** The SG/Send server writes a permanent tombstone on delete.
If delete succeeds but the local rename fails, the client is left pointing at a
tombstoned vault with no recovery path (the tombstone is permanent; that vault_id can
never be written to again with any key).

**Correct Step 8 sequence:**

```
8a. Atomic local rename:
      mv .sg_vault      → .sg_vault_old_<ts>
      mv .sg_vault_new  → .sg_vault
      rm -rf .sg_vault_old_<ts>
    Client is now on the new vault. If this fails, .sg_vault_new/ still exists
    and the old vault is still intact — recoverable via --cleanup.

8b. DELETE old_vault_id from server → tombstone written.
    If this fails: two valid vaults exist. Emit warning:
    "Old vault {old_vault_id} still live on server. Run 'sgit vault move --cleanup'
    or 'sgit vault delete-on-remote' on the old directory to remove it."
```

This matches the server spec's safe sequence: update local config FIRST, then delete.

**Tombstone error handling:**
- Push to a tombstoned vault_id returns HTTP 403 `{"detail": "Write key mismatch"}`.
  SGit must detect this 403 and surface: `"Vault {vault_id} has been permanently deleted
  and cannot be reused. If this vault was moved, clone the new vault instead."` — not the
  raw "write key mismatch" which implies a credentials problem.
- `Vault__API__In_Memory` must be extended to implement tombstone behaviour (write a
  tombstone record on delete; reject subsequent writes with a 403-equivalent) so the
  transaction tests can exercise this path without a real server.

**`--cleanup` flag (replaces `--resume`, per Dinis 2026-05-06):**
`sgit vault move --cleanup` removes `.sg_vault_new/` if present and calls the target
API to delete any partially-pushed new vault_id. If the old vault is already tombstoned
(403 on delete = permanent), treat as "already cleaned up." No `move-in-progress.json`
needed; `.sg_vault_new/`'s presence is the only state indicator.

**`--dry-run` flag:** Walk all 8 steps logically, print what would happen, no side
effects, no API calls, no file writes. Test explicitly.

**Branch signing keys:** Always rotate unconditionally on `vault move` (Dinis 2026-05-06).
No flag. Step 2 (`Step__Move__Derive_New_Keys`) generates new branch signing keypairs
alongside the new vault key.

**`key_generation` counter:** Keep it in `move-history.json` for chain auditing. Do NOT
wire it into a cache-invalidation code path on pull — this is unnecessary because vault_id
changes on every move (Dinis 2026-05-06, see §1.4).

**Confirmation UX (brief §7):** 6-step interactive confirmation before any state change,
with `--yes` to skip all for CI. Prompts live in `CLI__Vault.cmd_vault_move()`, never in
the `Vault__Sync__Move` action class (no `CLI__Input` imports in core).

**Open question from brief §8b — resolved (Dinis 2026-05-06):**
Stale-clone adoption is N/A. Because vault_id always changes, existing clones pointing
at the old vault_id either (a) continue working if the old vault wasn't deleted, or
(b) get a 404/403 from the server. No automatic key adoption in `pull`. Drop the
`key_generation`-driven cache-invalidation feature and `test_Vault__Sync__Move__Stale_Cache.py`.

**Layer compliance:** `core/actions/move/` is the correct layer. Workflow steps live in
`sgit_ai/workflow/move/`. No new KNOWN_VIOLATIONS. Verify imports before committing.

---

### 1.4 Brief 03 — Vault Move Testing

**Test layout** (per brief §2, updated for resolved decisions):

```
tests/unit/core/actions/move/
├── test_Vault__Sync__Move__Smoke.py          # happy path (brief 00h §6 cases 1–9)
├── test_Vault__Sync__Move__Object_IDs.py     # ID stability — most critical
├── test_Vault__Sync__Move__Sentinel.py       # sentinel commit invariants
├── test_Vault__Sync__Move__Transaction.py    # failure injection per step (9 tests)
├── test_Vault__Sync__Move__Markers.py        # key_generation + move-history.json
├── test_Vault__Sync__Move__Backup.py         # backup zip + restore round-trip
├── test_Vault__Sync__Move__Cleanup.py        # --cleanup (replaces --resume)
└── (DROP) test_Vault__Sync__Move__Stale_Cache.py   # stale-cache N/A; drop this file

tests/unit/cli/
├── test_CLI__Vault__Move__Prompts.py         # UX (input() mocking OK here only)
└── test_CLI__Vault__Move__Dry_Run.py         # --dry-run performs no state change

tests/qa/sync/
└── test_Vault__Move__Multi_Round.py          # 3 sequential moves, 10 invariants
```

**Transaction test infrastructure:**
`Vault__API__In_Memory` needs tombstone support to make `test_Vault__Sync__Move__Transaction.py`
work without mocks — specifically to test that:
- After successful delete, the old vault_id returns 403 on any write attempt.
- `--cleanup` treats a 403 on delete as "already deleted."

Add tombstone simulation to `Vault__API__In_Memory` as part of Brief 02 (not 03), so the
transaction tests can use it immediately.

**Brief 03 §3i note — input() mocking:** The brief explicitly allows `input()` mocking
in `test_CLI__Vault__Move__Prompts.py`. This is the sole exception to the no-mocks rule
in this sprint; storage/api/crypto mocking remains prohibited.

**Multi-round QA scenario (brief §4):**
Three sequential moves covering in-place rotation, server move (no key change), and
combined rotation + server move. Key assertion: all pre-move object IDs survive every
move; only sentinel commit objects are new. Full assertion matrix at brief 03 §4.

---

## 2. Execution Plan

### Brief 04 — Vault Backup/Restore (~1 day)

**Commit 1:** `feat(storage): implement Vault__Object_Store.store_at()`
- Modified: `sgit_ai/storage/Vault__Object_Store.py` — add `store_at(object_id, content, force=False)`
- New: `tests/unit/storage/test_Vault__Object_Store__Store_At.py` — no-overwrite default, force-overwrite, does not validate hash

**Commit 2:** `feat(backup): Vault__Backup, Schema__Backup_Manifest, Workflow__Vault_Backup`
- New: `sgit_ai/schemas/backup/__init__.py`, `Schema__Backup_Manifest.py`
- New: `sgit_ai/core/actions/backup/__init__.py`, `Vault__Backup.py`
- New: `sgit_ai/workflow/backup/__init__.py`, `Workflow__Vault_Backup.py`,
  `Backup__Workspace.py`, `steps/Step__Backup__Build_Zip.py`
- Modified: `sgit_ai/core/actions/lifecycle/Vault__Sync__Lifecycle.py` — refactor
  `uninit()` to delegate zip creation to `Vault__Backup`

**Commit 3:** `feat(backup): Vault__Restore, Workflow__Vault_Restore`
- New: `sgit_ai/core/actions/backup/Vault__Restore.py`
- New: `sgit_ai/workflow/backup/Workflow__Vault_Restore.py`, `Restore__Workspace.py`,
  and all 5 `Step__Restore__*` files (reuse `Step__Clone__Extract_Working_Copy`)

**Commit 4:** `feat(cli): vault backup / restore / backups subcommands`
- Modified: `sgit_ai/cli/CLI__Vault.py` — `cmd_backup`, `cmd_restore`, `cmd_backups`
- Modified: `sgit_ai/cli/CLI__Main.py` — register 3 subparsers in `_register_vault_ns`

**Reviewer Fix pass**

**Commit 5:** `test(backup): Vault__Backup and Vault__Restore tests (~22 tests)`
- New: `tests/unit/core/actions/backup/test_Vault__Backup.py` (10 tests per brief §5a)
- New: `tests/unit/core/actions/backup/test_Vault__Restore.py` (12 tests per brief §5b)

---

### Brief 02 — Vault Move (~1.5 days)

**Commit 1:** `feat(api): add tombstone support to Vault__API__In_Memory`
- Modified: `sgit_ai/network/api/Vault__API__In_Memory.py` — write tombstone on delete;
  reject writes to tombstoned vault_ids with a 403-equivalent exception
- New: `tests/unit/network/api/test_Vault__API__In_Memory__Tombstone.py`

**Commit 2:** `feat(move): Vault__Sync__Move + Workflow__Vault_Move (8 steps)`
- New: `sgit_ai/core/actions/move/__init__.py`, `Vault__Sync__Move.py`
- New: `sgit_ai/workflow/move/__init__.py`, `Workflow__Vault_Move.py`,
  `Move__Workspace.py`, and 8 `Step__Move__*.py` files
- New: `sgit_ai/schemas/move/__init__.py`, `Schema__Vault_Move_Record.py`,
  `Schema__Vault_Moves.py`
- **Critical:** Step 8 must do local rename BEFORE server delete (see §1.3)

**Commit 3:** `feat(cli): vault move subcommand + --cleanup flag`
- Modified: `sgit_ai/cli/CLI__Vault.py` — `cmd_vault_move`, `cmd_vault_move_cleanup`
- Modified: `sgit_ai/cli/CLI__Main.py` — register `vault move` with `--new-key`, `--to`,
  `--reason`, `--yes`, `--dry-run`, `--cleanup`, `--token`

**Reviewer Fix pass**

**Commit 4:** `test(move): smoke + object-ID stability + sentinel tests`
- New: `tests/unit/core/actions/move/test_Vault__Sync__Move__Smoke.py`
- New: `tests/unit/core/actions/move/test_Vault__Sync__Move__Object_IDs.py`
- New: `tests/unit/core/actions/move/test_Vault__Sync__Move__Sentinel.py`

**Commit 5:** `test(move): markers + backup + transaction + cleanup tests`
- New: `tests/unit/core/actions/move/test_Vault__Sync__Move__Markers.py`
- New: `tests/unit/core/actions/move/test_Vault__Sync__Move__Backup.py`
- New: `tests/unit/core/actions/move/test_Vault__Sync__Move__Transaction.py`
- New: `tests/unit/core/actions/move/test_Vault__Sync__Move__Cleanup.py`

---

### Brief 03 — Vault Move Test Matrix (~½ day)

**Commit 1:** `test(move): CLI prompt + dry-run tests`
- New: `tests/unit/cli/test_CLI__Vault__Move__Prompts.py` (12 tests, input() mocking OK)
- New: `tests/unit/cli/test_CLI__Vault__Move__Dry_Run.py`

**Commit 2:** `test(move): multi-round QA scenario`
- New: `tests/qa/sync/test_Vault__Move__Multi_Round.py` (10 tests per brief §4)
- Modified: `tests/qa/sync/test_Vault__Move__Multi_Round.py` — wire `vault backup`
  checkpoint per brief 04 §5d integration

**Reviewer Fix pass**

---

## 3. Resolved Decisions (all from Dinis 2026-05-06)

| Decision | Resolution |
|---|---|
| Brief 01 — exact rename | `--as` with `dest='share_as'`; separate `--token` for access credential. DONE. |
| Brief 02 §8a — branch key rotation | Always rotate. Unconditional, no flag. |
| Brief 02 §8b — stale-clone adoption | N/A. vault_id changes → old clones get 404/403. No cache-invalidation in pull. |
| Brief 02 §8c — `--resume` | Replace with `--cleanup`. No persisted state file needed. |
| Brief 04 §4a — new files vs lifecycle | New files as specified in the brief. `uninit()` refactored to delegate. |
| Step 8 ordering | Local rename FIRST, server delete SECOND (tombstone is permanent). |

## 4. Guidance for the Dev Agent

**Start here:**
1. Read all five briefs in `team/villager/v0.14.x__brief-pack/` in order: `00__index.md`,
   `01` (DONE — skip), `04`, `02`, `03`.
2. Read `tests/_helpers/vault_test_env.py` — all unit tests use this fixture.
3. Read `sgit_ai/workflow/clone/` — the workflow pattern to mirror for new move/backup workflows.
4. Read `tests/unit/architecture/test_Layer_Imports.py` — KNOWN_VIOLATIONS must not grow.

**Non-negotiable rules:**
- Zero mocks for storage/api/crypto. `input()` mocking is permitted only in
  `test_CLI__Vault__Move__Prompts.py`.
- All new `Schema__*` classes must pass the round-trip invariant:
  `assert cls.from_json(obj.json()).json() == obj.json()`.
- No `__init__.py` files in `tests/`. Source directories need `__init__.py`.
- All prompt UX (`CLI__Input` calls) stays in `CLI__Vault`; action classes are pure logic.
- Step 8 of `Workflow__Vault_Move`: local rename before server delete. This is correctness-
  critical — the tombstone is permanent.
- Tombstone 403 on push: surface "vault has been permanently deleted" not "write key mismatch".
