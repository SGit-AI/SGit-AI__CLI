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
