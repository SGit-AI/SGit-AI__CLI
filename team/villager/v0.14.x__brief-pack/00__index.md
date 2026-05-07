# v0.14.x Brief Pack — Vault Ops & CLI Polish

**Sprint:** post-v0.14.0, pre-visualisation track
**Goal:** ship the four vault-operation features (CLI rename, backup, restore, move) before starting visualisation work
**Estimated effort:** ~3 days dev + ½ day reviewer (brief 01 already landed)
**Status:** brief 01 DONE; briefs 04 → 02 → 03 ready for SGit Dev Agent

**SGit Dev Agent: read [`00a__start-here__dev-agent-briefing.md`](./00a__start-here__dev-agent-briefing.md) FIRST.** It tells you what to read in what order, the non-negotiable rules, the three correctness-critical things, and where to land your commits.

---

## Briefs in execution order

| # | Brief | Scope | Effort | Why this order |
|---|---|---|---|---|
| 01 | `01__cli-token-rename-brief.md` | Rename `--token` → `--as` on `vault share`, `vault export`, `share publish` | ½ day | First — settles CLI vocabulary before anything else references share commands |
| 06 | `06__dotfile-tracking-brief.md` | Drop blanket dotfile exclusion + `sgit inspect ignored` command | ~½ day | Lands early so `.vault-settings` (brief 07) is naturally trackable |
| 07 | `07__vault-settings-brief.md` | `.vault-settings` blob in tree + initial commit on `sgit init` | ~1 day | Depends on 06; needed before 02 so the move workflow handles `.vault-settings` correctly |
| 04 | `04__vault-backup-restore-brief.md` | New `sgit vault backup`, `sgit vault restore`, `sgit vault backups` commands | ~1 day | Ships before 02 because 02 step 7 calls into the backup primitive |
| 02 | `02__vault-move-brief.md` | New `sgit vault move` command — transactional rotation + server move with stable object IDs | ~1.5 days | Depends on backup primitive from 04 + needs to handle `.vault-settings` (07) |
| 03 | `03__vault-move-testing-brief.md` | Comprehensive testing for `vault move` (multi-round, transaction failure injection, regression) | ~1 day | Depends on 02 + uses 04's backup/restore for setup; verifies `.vault-settings` invariants |
| 08 | `08__vault-key-flag-brief.md` | `--vault-key <key>` flag on admin commands (`vault delete-on-remote`, `vault probe`) for headless operation | ~½ day | Independent of vault-ops; lands last in the pack before visualisation |
| 09 | `09__schema-parse-error-brief.md` | Structured error handling at every wire-boundary `Schema__*.from_json(...)` site — replaces generic ValueError with `Vault__Schema_Parse_Error` carrying schema name + source + field + value | ~½ day | Independent; ideally lands before 02/04/07 so they adopt the helper from the start |
| 10 | `10__command-graph-brief.md` | Friendly "command not found" error formatter + `Schema__Command_Graph` (auto-populated + curated metadata) + smart suggestions ("did you mean: vault info?") + `sgit dev commands {list,graph,find}` | ~1.5 days | Independent; lands last in the pack before visualisation. JSON export feeds the future viz track. |
| 12 | `12__vault-move-cleanup-brief.md` | Address 3 follow-ups from the brief 02 implementation review: surface re-encryption failures (no silent fallback), use `store_at()` in the move code path, verify cleanup state detection between 8a/8b | ~½ day | First in the remaining work — fixes follow-ups while context is fresh and unblocks tagging the v0.14.x release of vault backup + move |
| 13 | `13__history-range-brief.md` | `history log <from>..<to>` range syntax + `--files` / `--patch` / `--json` modes for per-commit walking. Powers conductor-style agents producing periodic vault-activity reports | ~½ day | Independent; low-risk pure addition; can land any time |
| 15 | `15__integration-tests-brief.md` | **🔴 URGENT.** Fix three live move bugs (Validate_Local doesn't walk commit graph → ships incomplete vault; empty old_vault_id in backup name; new vault key not displayed in success output). Plus add integration tests for move/backup/restore against a real server. Establishes the standard: every network-touching action requires an integration test. | ~1 day | **Lands FIRST** before any other v0.14.x work — closes the data-integrity hole + the test-coverage gap that let it ship. |
| 16 | `16__brief-15-followups.md` | Brief 15 review follow-ups: add the missing 9th integration test (`test_move_backup_can_be_restored_under_old_key` — disaster-recovery roundtrip); convert `_walk_tree` to iterative; add a comment to the ref-filter; replace the `.sg_vault_new/ → .sg_vault/` string hack with state-update at the rename step. | ~1 hour | After brief 15 merges; small reviewer-fix-style pass. |
| 17 | `17__commit-id-resolution-brief.md` | Commit-id prefix resolution at the CLI. Today `history log` prints short hashes (e.g. `6c6191cdf3a8`) but every command requires the full `obj-cas-imm-*` form, so copy-pasting the log output silently fails. Adds `resolve_commit_id` helper accepting full / short / shorter-prefix forms, with typed errors for not-found and ambiguous cases. Mirrors git's `git show <prefix>` UX. | ~½ day | Independent; small UX fix. Can fold into brief 16's reviewer-fix pass or land standalone. |
| 18 | `18__clone-missing-blobs-brief.md` | **🔴 CRITICAL — JUMPS TO FIRST.** sgit clone only downloads blobs reachable from HEAD's tree, not historical blobs. Every cloned vault is silently incomplete; `history show <past-commit>` is broken; `vault move` was actively shipping data-loss until Brief 15 §2a started catching it. Fix changes blob enumeration to walk every reachable tree across all commits. Plus three smaller fixes (move auto-repair, fsck dedup, error-message wording). | ~1 day | **Lands BEFORE everything else.** This is the root cause of the corrupted-vault-on-move incident; Brief 15 §2a is the band-aid keeping users safe. |

## Recommended landing order (post-vault-move-release)

The first vault-ops release (briefs 02, 03, 04) is greenlit — see `11__implementation-review.md`. Order for the remaining work before visualisation:

```
1. Brief 18  — 🔴 clone full-history blobs (root cause of the corrupted-vault-on-move incident; ~1 day)
2. Brief 16  — brief-15 cosmetic follow-ups (~1 hour)
3. Brief 17  — commit-id prefix resolution (~½ day)
4. Brief 12  — vault move cleanup pass (~½ day)
5. Brief 09  — schema-parse error handling (~½ day)
6. Brief 06  — dotfile tracking (~½ day)
7. Brief 07  — .vault-settings + initial commit (depends on 06; ~1 day)
8. Brief 08  — --vault-key flag for headless admin (~½ day)
9. Brief 10  — command graph + suggestions (largest; feeds visualisation; ~1.5 days)
```

Total remaining: ~5.5 days. After brief 10, the v0.14.x pack is complete and the visualisation track is unblocked.

Why this order:
- **18 first** — root cause of the data-loss incident. Every other brief assumes the clone path is correct. Brief 15 §2a is the band-aid keeping users safe; Brief 18 fixes the underlying bug so §2a goes from "essential" to "defence-in-depth".
- **16 second** — small reviewer-fix-style pass; closes the open follow-ups from brief 15.
- **17 third** — UX fix; small.
- **12 fourth** — small, addresses recently-shipped code, keeps reviewer context warm.
- **09 fifth** — the `parse_or_raise` helper should exist before briefs 07 and 06 add new schema-parse boundaries.
- **06 sixth** — drops blanket dotfile exclusion so `.vault-settings` is naturally trackable in brief 07 without special-case logic.
- **07 seventh** — depends on 06; introduces a new schema-parse boundary that should adopt 09's helper.
- **08 eighth** — independent; can land anywhere; placed here for momentum after the bigger 07.
- **10 last** — biggest piece. Lands last so its JSON export is the bridge into the visualisation track.

## Recommended landing order (different from numerical order)

The dependency graph dictates this sequence:

```
1. Brief 01  — token rename                   (DONE)
2. Brief 06  — dotfile tracking
3. Brief 07  — .vault-settings + initial commit
4. Brief 04  — backup/restore
5. Brief 02  — vault move
6. Brief 03  — vault move tests
```

Each brief lists explicit verification checklists. Each brief mandates Reviewer Fix passes (CLAUDE.md compliance, mock discipline) per the established two-session pattern.

## Out of scope for this sprint

- Visualisation track (`sgit_show/`, briefs `v01–v07` in `team/villager/v0.13.x__brief-pack/visualisation/`) — starts after these four land
- Standalone `sgit vault backup` cloud upload (e.g. `--output-dir s3://...`)
- Per-branch key rotation as a separate command from `vault move`
- `sgit_ai/cli/CLI__Migrate.py` enhancements — current command is sufficient
- Vault web team JS client work — covered in a debrief produced after brief 02 lands
