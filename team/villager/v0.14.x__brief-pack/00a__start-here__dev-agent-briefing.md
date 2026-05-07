# Start Here — v0.14.x Vault Ops Sprint (SGit Dev Agent)

**Read this file first.** It tells you what to do, in what order, with the rules that matter.

---

## 1. What you're doing

You're implementing six briefs that ship before the visualisation track:

| # | Brief | Status |
|---|---|---|
| 01 | `--token` → `--as` rename on share/publish/export commands | ✅ DONE |
| 06 | Drop blanket dotfile exclusion + `sgit inspect ignored` | TODO |
| 07 | `.vault-settings` in tree + initial commit on `sgit init` | TODO |
| 04 | `sgit vault backup` / `vault restore` / `vault backups` | TODO |
| 02 | `sgit vault move` (transactional rotation + server move) | TODO |
| 03 | `vault move` test matrix (multi-round, transactional regression) | TODO |
| 08 | `--vault-key` flag on `vault delete-on-remote` / `vault probe` | TODO |
| 09 | Structured error handling at schema-parse boundaries (`parse_or_raise`) | TODO |
| 10 | Command discovery graph + friendly error formatter + smart suggestions | TODO |
| 12 | Vault move cleanup pass (post-implementation-review follow-ups) | TODO |
| 13 | `history log <from>..<to>` range syntax + JSON output for conductor agents | ✅ DONE |
| 15 | 🔴 URGENT: fix live move bugs + integration tests for move/backup/restore | TODO — LANDS FIRST |

Briefs 01, 02, 03, 04, 13 have landed. **Brief 15 is urgent and lands FIRST** before resuming other work — it fixes a live data-integrity bug in `vault move` (Validate_Local doesn't walk the commit graph, so the move can ship an incomplete vault to the server) and closes the integration-test gap that let it slip past 102 unit/QA tests. Briefs 06, 07, 08, 09, 10, 12, 15 are yours.

**Updated recommended landing order:** **15** → 12 → 09 → 06 → 07 → 08 → 10. See `00__index.md` for the rationale.

**Recommended landing of brief 09: early.** It's independent, but every later brief (02, 04, 07) introduces new schema-parse boundaries that should adopt `parse_or_raise` from the start. Land 09 between 06 and 07 so the helper exists by the time the new schemas come online.

**Land them in this order: 06 → 07 → 04 → 02 → 03.** Why:
- 06 first: drops the blanket `startswith('.')` rule so `.vault-settings` is naturally trackable.
- 07 second: depends on 06; introduces `.vault-settings` as a tracked file in the root tree, plus the initial commit on `sgit init`. Other briefs need to know `.vault-settings` exists.
- 04 third: backup/restore primitives that brief 02 step 7 calls into.
- 02 fourth: vault move — must handle `.vault-settings` correctly (re-encrypt, preserve object ID).
- 03 last: tests for vault move, including invariants that `.vault-settings` survives moves.

Total estimated effort: ~4.5 days for briefs 06 + 07 + 04 + 02 + 03 (06 ~½ day, 07 ~1 day, 04 ~1 day, 02 ~1.5 days, 03 ~½ day).

---

## 2. What to read, in what order

1. `team/villager/v0.14.x__brief-pack/00__index.md` — top-level overview.
2. `team/villager/v0.14.x__brief-pack/05__execution-plan.md` — the architectural plan including reuse opportunities and per-brief commit breakdown. **Read this before the briefs themselves** — it points out where the briefs were updated and which sections are most critical.
3. `team/villager/v0.14.x__brief-pack/04__vault-backup-restore-brief.md` — implement first.
4. `team/villager/v0.14.x__brief-pack/02__vault-move-brief.md` — implement second. **Pay particular attention to §4d (tombstone behaviour) and §5c step 8 (ordering is correctness-critical).**
5. `team/villager/v0.14.x__brief-pack/03__vault-move-testing-brief.md` — implement third.

Then read these existing source files BEFORE writing any code:

- `CLAUDE.md` — project conventions (Type_Safe rules, naming, file layout)
- `team/villager/CLAUDE.md` — team conventions
- `sgit_ai/storage/Vault__Object_Store.py` — the `store()` API you'll extend with `store_at()`
- `sgit_ai/core/actions/clone/Vault__Sync__Clone.py` — workflow pattern to mirror
- `sgit_ai/core/actions/lifecycle/Vault__Sync__Lifecycle.py:132–169` — existing zip logic that `Vault__Backup` should subsume (the brief's reuse opportunity)
- `sgit_ai/migrations/tree_iv/Migration__Tree_IV_Determinism.py` — closest existing pattern for re-encrypting an object graph. The graph-walk + decrypt + re-encrypt pattern in `vault move` mirrors this.
- `sgit_ai/workflow/Workflow__Runner.py` — workflow framework
- `sgit_ai/workflow/clone/` — directory layout for new workflow packages (mirror this for `workflow/backup/`, `workflow/move/`)
- `sgit_ai/cli/CLI__Vault.py` — where new vault-namespace CLI handlers go
- `sgit_ai/cli/CLI__Main.py` — subparser registration in `_register_vault_ns`
- `sgit_ai/network/api/Vault__API__In_Memory.py` — extend with tombstone simulation (brief 02 §5g)
- `tests/_helpers/vault_test_env.py` — the test fixture all unit tests use
- `tests/unit/architecture/test_Layer_Imports.py` — `KNOWN_VIOLATIONS` set; no new violations may be introduced
- `tests/qa/sync/conftest.py` — qa-tier fixture wiring

---

## 3. Non-negotiable rules

These are the rules that have caused the most reviewer fixes and re-reviews on previous sprints. Internalise them before starting.

### Type_Safe and CLAUDE.md
- **Zero raw primitives** in Type_Safe classes. Every `str` / `int` / `dict` field must be a `Safe_*` subclass or a typed collection (`list[Safe_Str]`, never bare `list`).
- **Every new schema must pass the round-trip invariant**: `assert cls.from_json(obj.json()).json() == obj.json()`. Add this assertion to at least one test per schema.
- **Classes for everything.** No module-level functions. No `@staticmethod`. All behaviour lives in methods on Type_Safe classes.
- **Naming:** `Safe_Str__Vault_Move_Reason`, `Schema__Vault_Move_Record`, `Workflow__Vault_Move`, `Step__Move__Build_Temp_Vault`, `Test_Vault__Sync__Move`. Test files: `test_Vault__Sync__Move__Smoke.py`.
- **Single-line docstrings.** No multi-paragraph module/class/function docstrings. If you need to explain WHY something non-obvious, a one-line `# WHY: ...` comment beats a four-line docstring. Reviewer Fix passes have repeatedly trimmed multi-paragraph docstrings — write them once correctly.
- **No `__init__.py` files in `tests/`.** Source dirs need `__init__.py`; test dirs do not.

### Mocks
- **Zero mocks for storage, crypto, API.** Use `Vault__Test_Env` and the local SG/Send fixture. The only exception is `input()` mocking in `test_CLI__Vault__Move__Prompts.py` (and equivalent backup/restore prompt tests) — there's no realistic alternative for stdin emulation. **No other mocks anywhere.**
- If you find yourself wanting to mock a network call, extend `Vault__API__In_Memory` instead.

### CLI and layer compliance
- **Prompt UX (`input()`) lives only in `CLI__Vault.py`** — never in action classes (`core/actions/`) or storage/crypto. Action classes are pure logic.
- **Don't introduce new layer violations.** Run `pytest tests/unit/architecture/test_Layer_Imports.py` after every commit; if it fails because you added an import that crosses layers, find a different way.
- **All new workflows must `@register_workflow`** so they show up in `sgit dev workflow list`.
- **Add delegate methods to `sgit_ai/core/Vault__Sync.py`** for each new top-level action (`Vault__Sync.move()`, `.move_cleanup()`, `.backup()`, `.restore()`). Mirror the existing pattern.

### Git workflow
- **One concern per commit.** Don't mix the rename and the test refactor and the new schema in one commit.
- **After each major commit, run a Reviewer Fix pass** (or expect one). The reviewer catches CLAUDE.md violations, mock additions, multi-paragraph docstrings. Fix what they flag in a separate commit prefixed `Reviewer Fix N: ...`.
- **Push after every commit.** Don't accumulate.
- **Commit messages** follow the existing pattern: `feat(area): summary`, `fix(area): summary`, `test(area): summary`. Include `https://claude.ai/code/session_<id>` trailer.

---

## 4. The three correctness-critical things

If you get nothing else right, get these three right.

### 4a. Step 8 of `vault move` ordering — local rename FIRST, server delete SECOND

`Workflow__Vault_Move` step 8 has two sub-steps. They MUST be in this order:

```
8a. Atomic local rename:
      mv .sg_vault          → .sg_vault_old_<ts>
      mv .sg_vault_new      → .sg_vault
      rm -rf .sg_vault_old_<ts>

8b. Server delete:
      DELETE /api/vault/destroy/{old_vault_id}
```

**Why this order matters:** the SG/Send server writes a permanent tombstone on delete. If 8b runs before 8a and 8a then fails, the user is stranded — the local clone points at a permanently-tombstoned `vault_id` with no recovery path. The tombstone cannot be removed without server-admin intervention.

Brief 02 §5c documents this explicitly. Brief 02 §4d explains the SG/Send tombstone behaviour. Read both before implementing step 8.

### 4b. Tombstone 403 must be translated to a friendly message

When SGit pushes to a tombstoned `vault_id`, the server returns:

```
HTTP 403
{"detail": "Write key mismatch"}
```

The raw message is misleading — it implies a credentials problem, but the actual issue is "this vault has been deleted and cannot be reused." SGit must:

1. Catch the 403 specifically.
2. Check whether the move-history shows this `vault_id` as a `from_vault_id` (i.e. the user moved away from it).
3. If yes, surface: `"Vault {vault_id} has been permanently moved/deleted. Clone the new vault at {to_vault_id}."`
4. If the move-history doesn't know the new location, surface: `"Vault {vault_id} has been permanently deleted. If this vault was moved, clone the new vault directly."`

Test this behaviour in `test_Vault__Sync__Move__Tombstone.py` (brief 03 §3g).

### 4c. Sparse-mode safety in backup and restore

Brief 04 doesn't add a sparse-mode hazard, but be aware of the existing one fixed in v0.14.0: commits from sparse clones preserve unfetched entries by default. Backup zips a vault's full `bare/data/` directory; if you back up a sparse clone, the zip captures only the locally-fetched objects. Restore from such a zip yields a vault missing those objects — the user's working copy will be incomplete in `--mode expanded`.

For the testing brief, add an explicit test: `test_backup_of_sparse_clone_warns_user` — backup of a clone where `local_config.sparse=True` should print a warning that the resulting backup is incomplete and direct the user to `sgit pull` or full-clone before backing up.

(This isn't called out explicitly in brief 04 — flag it as a question to Dinis if you want confirmation, or just implement defensively.)

---

## 5. How to make decisions

You'll hit ambiguity. The pattern:

1. **First, check `team/villager/v0.14.x__brief-pack/05__execution-plan.md`** — many ambiguities have already been resolved there with attribution to Dinis 2026-05-06.
2. **Second, check the relevant brief's "Resolved decisions" or "Out of scope" sections** — these capture earlier dialogue.
3. **Third, look at the closest existing pattern in the codebase** — e.g. how does `Vault__Sync__Clone` handle a similar case?
4. **Fourth, prefer the more conservative / safer / more-confirmation choice.** When in doubt, ask one more `[y/N]`.
5. **Last resort: ask Dinis** — but bundle questions. Don't ask one-at-a-time. Collect 3-5 questions and ask them together so he can answer in one reply.

When you ask a question, format it so Dinis can answer Y/N or pick from 2-3 options. Don't ask broad "what should I do?" questions.

---

## 6. Testing checkpoints

**After brief 04 lands:**
- All unit tests pass (`pytest tests/unit/ -q`).
- ~22 new tests in `tests/unit/core/actions/backup/`.
- `sgit vault backup .` works end-to-end on a real vault.
- `sgit vault restore <zip> <dest>` works for both `--mode bare` and `--mode expanded`.
- `sgit vault backups` lists backups with the right metadata.
- Workflow registry (`sgit dev workflow list`) includes `vault-backup` and `vault-restore`.

**After brief 02 lands:**
- All unit tests pass.
- `Vault__API__In_Memory` tombstone simulation works (test file in place).
- `sgit vault move` works end-to-end on a real vault (in-place rotation case).
- `sgit vault move --to <other-server>` works for server move.
- `sgit vault move --cleanup` finishes a partial move.
- `sgit vault move --dry-run` walks the workflow without side effects.
- All move tests in `tests/unit/core/actions/move/` pass.

**After brief 03 lands:**
- All unit tests pass (~3,300 total).
- New qa-tier tests pass (multi-round move scenario, ~30s additional runtime).
- ≥95% line coverage on `sgit_ai/core/actions/move/` and `sgit_ai/core/actions/backup/`.
- KNOWN_VIOLATIONS unchanged (still 7).
- `sgit dev workflow list` shows all new workflows registered.

**Run after every commit:**
```bash
pytest tests/unit/ -q --tb=no
pytest tests/unit/architecture/test_Layer_Imports.py -v
```

---

## 7. When you're done

After brief 03's last test commit + final reviewer fix:

1. Push the branch and confirm green CI.
2. Write a one-paragraph debrief at `team/humans/dinis_cruz/claude-code-web/<date>/v0.14.x-vault-ops-debrief.md` covering:
   - What landed (commits, test counts, file additions)
   - Anything that surprised you during implementation
   - Any followups you'd recommend before visualisation starts
3. Tell Dinis you're done and the branch is ready for review.

The vault-web debrief described in `02__vault-move-brief.md §9` is OUT OF SCOPE for this sprint — that's a separate document Dinis will produce later for the SG/Send web client team.

---

## 8. Things to ignore (out of scope)

Do NOT do these as part of this sprint, even if they seem related:

- The visualisation track (`sgit_show/`, briefs `v01–v07` in `team/villager/v0.13.x__brief-pack/visualisation/`).
- Cloud upload of backups (`--output-dir s3://...`).
- Standalone "rotate branch keys without a vault move" command.
- A web client for opening backups in a browser.
- Auto-backup on schedule.
- Backup pruning / lifecycle management.
- Cross-version restore (v0.14 vault → v0.15 client) — single-version testing only.
- The `Vault__API__In_Memory` tombstone simulation **does not need to mimic the real server's tombstone-file semantics** — just the observable behaviour (writes raise 403, reads return not_found, list returns empty). Don't write a tombstone file.

If something feels in scope but isn't on the briefs, raise it as a question rather than expanding the work yourself.

---

## 9. Quick reference: file naming you'll create

```
sgit_ai/core/actions/backup/
├── __init__.py
├── Vault__Backup.py
└── Vault__Restore.py

sgit_ai/core/actions/move/
├── __init__.py
└── Vault__Sync__Move.py

sgit_ai/workflow/backup/
├── __init__.py
├── Workflow__Vault_Backup.py
├── Workflow__Vault_Restore.py
├── Backup__Workspace.py
├── Restore__Workspace.py
└── steps/Step__Backup__Build_Zip.py + 5 Step__Restore__*.py files

sgit_ai/workflow/move/
├── __init__.py
├── Workflow__Vault_Move.py
├── Move__Workspace.py
└── 8 Step__Move__*.py files

sgit_ai/schemas/backup/
├── __init__.py
└── Schema__Backup_Manifest.py

sgit_ai/schemas/move/
├── __init__.py
├── Schema__Vault_Move_Record.py
└── Schema__Vault_Moves.py

tests/unit/core/actions/backup/
├── test_Vault__Backup.py
└── test_Vault__Restore.py

tests/unit/core/actions/move/
├── test_Vault__Sync__Move__Smoke.py
├── test_Vault__Sync__Move__Object_IDs.py
├── test_Vault__Sync__Move__Sentinel.py
├── test_Vault__Sync__Move__Transaction.py
├── test_Vault__Sync__Move__Markers.py
├── test_Vault__Sync__Move__Backup.py
├── test_Vault__Sync__Move__Tombstone.py
└── test_Vault__Sync__Move__Cleanup.py

tests/unit/network/api/
└── test_Vault__API__In_Memory__Tombstone.py

tests/unit/storage/
└── test_Vault__Object_Store__Store_At.py

tests/unit/cli/
├── test_CLI__Vault__Move__Prompts.py
├── test_CLI__Vault__Move__Dry_Run.py
└── (backup/restore prompt tests — names per brief 04 §5c)

tests/qa/sync/
└── test_Vault__Move__Multi_Round.py
```

Files modified (not created):
- `sgit_ai/storage/Vault__Object_Store.py` — add `store_at()`
- `sgit_ai/core/Vault__Sync.py` — add `backup`, `restore`, `move`, `move_cleanup` delegates
- `sgit_ai/core/actions/lifecycle/Vault__Sync__Lifecycle.py` — refactor `uninit()` to delegate zip creation to `Vault__Backup`
- `sgit_ai/cli/CLI__Vault.py` — add `cmd_backup`, `cmd_restore`, `cmd_backups`, `cmd_vault_move`, `cmd_vault_move_cleanup`
- `sgit_ai/cli/CLI__Main.py` — register all new subparsers in `_register_vault_ns`
- `sgit_ai/network/api/Vault__API__In_Memory.py` — add tombstone simulation

---

Read the briefs. Start with brief 04. Push often. When in doubt, ask in batches.
