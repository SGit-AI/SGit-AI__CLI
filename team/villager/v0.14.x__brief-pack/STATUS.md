# v0.14.x Brief Pack — Status

**Last updated:** 2026-05-08
**Purpose:** single-page status of every brief in the v0.14.x pack. This is the **first file to read** when picking up the v0.14.x work in a new session.

For full brief content, open the individual brief file. For session-level context (how we got here), see `team/humans/dinis_cruz/claude-code-web/05/08/villager-session-debrief.md`.

---

## TL;DR

The v0.14.x sprint produced **22 brief-pack documents** between 2026-05-05 and 2026-05-08. **8 are fully landed**, **1 is partially done**, **8 are written but not yet implemented**, and **3 are review documents** (capture what landed against the briefs).

The next session should:

1. Read `00a__start-here__dev-agent-briefing.md` (canonical entry point for the SGit Dev Agent).
2. Read this STATUS.md for the up-to-date queue.
3. Pick the next brief per the recommended landing order in §4 below.

---

## 1. What's DONE ✅

| # | Brief | Implementation status | Review doc |
|---|---|---|---|
| 01 | `01__cli-token-rename-brief.md` — `--token` → `--as` rename | ✅ Landed `012f765` + Reviewer Fix 8 (`8c79d60`) | (no separate review; covered in 11) |
| 02 | `02__vault-move-brief.md` — vault move (transactional rotation + server move) | ✅ Landed `efccc92` + Reviewer Fix 11 + `5529106` two-layer fix | `11__implementation-review.md` |
| 03 | `03__vault-move-testing-brief.md` — vault move test matrix | ✅ Landed across `82a1264`, `1d7b070`, `25b5ee6` + Reviewer Fix 12 | (covered in 11) |
| 04 | `04__vault-backup-restore-brief.md` — backup/restore commands | ✅ Landed `c7e914b` + `361f15c` + `d2744ae` + Reviewer Fix 10 | (covered in 11) |
| 13 | `13__history-range-brief.md` — `history log A..B` range syntax | ✅ Landed `c009faa` (+ bonus diff-direction bug fix) | `14__brief-13-and-move-fixes-review.md` |
| 15 | `15__integration-tests-brief.md` — move bug fixes + integration test discipline | ✅ Landed `b39256f` + `5c0555d` (§3d roundtrip test follow-up) | (covered in 19) |
| 18 | `18__clone-missing-blobs-brief.md` — clone full-history blobs (P0 data-integrity fix) | ✅ Landed `5e7857e` + Reviewer Fix 13 + `2b77dfde` (Validate_Local ordering + thin-clone test) | `19__brief-18-review.md` |
| 20 | `20__merge-state-brief.md` — merge-in-progress first-class | ✅ Landed `ed5189f` + `ad87cd4` (CLAUDE.md compliance) | (review at end of session; STATUS) |

---

## 2. What's PARTIAL 🟡

| # | Brief | Done | Still TODO |
|---|---|---|---|
| 16 | `16__brief-15-followups.md` | §2 (missing 9th integration test `test_move_backup_can_be_restored_under_old_key`) landed in `5c0555d`; §3a (iterative `_walk_tree`) landed | §3b (one-line comment on `obj-cas-imm-` filter); §3c (replace `.sg_vault_new/` → `.sg_vault/` string-replace with state-update at rename step) — both ~30min total |

---

## 3. What's TODO 🔵

In the recommended landing order:

| # | Brief | Scope | Effort |
|---|---|---|---|
| 21 | `21__brief-20-followups.md` | `sgit history reset --fetch` flag + 5 missing integration tests from Brief 20 §7b. Confirmed in production by the conductor agent's recovery — without `--fetch` users fall back to full re-clone | ~½ day |
| 16 | `16__brief-15-followups.md` (remaining items) | §3b filter comment + §3c path-update at rename step | ~30 min |
| 17 | `17__commit-id-resolution-brief.md` | Commit-id prefix resolution at CLI. Today `history log` prints short hashes but every command requires the full `obj-cas-imm-*` form — copy-paste from log fails. Adds `resolve_commit_id` helper accepting full/short/prefix forms | ~½ day |
| 12 | `12__vault-move-cleanup-brief.md` | Three move follow-ups from Brief 02 review: surface re-encryption failures (no silent fallback in `Build_Temp_Vault`), use `store_at()` API in the move code path, verify cleanup state detection between 8a/8b | ~½ day |
| 09 | `09__schema-parse-error-brief.md` | Structured error handling at every wire-boundary `Schema__*.from_json(...)` call. New `Vault__Schema_Parse_Error` + `parse_or_raise` helper applied at ~8 known parse sites. Replaces generic `ValueError` with structured errors naming schema + field + value | ~½ day |
| 06 | `06__dotfile-tracking-brief.md` | Drop blanket `startswith('.')` exclusion from 4 files. Expand `ALWAYS_IGNORED_DIRS` with `.idea`, `.vscode`, `.next`, `.terraform`, etc. New `ALWAYS_IGNORED_FILES` for security-sensitive names (`.env`, `.netrc`, `id_rsa`...). New `sgit inspect ignored` command with `--rules` and `--why <path>` modes | ~½ day |
| 07 | `07__vault-settings-brief.md` | `.vault-settings.json` blob at root of every tree + initial commit on `sgit init`. New `Schema__Vault_Settings` (vault_name, created, created_by). New `sgit vault settings get/set/init` commands. Aligns sgit with the SG/Send web client's `createFromToken` pattern | ~1 day |
| 08 | `08__vault-key-flag-brief.md` | `--vault-key <key>` flag on `vault delete-on-remote` / `vault probe` for headless operation. Solves the broken-vault recovery scenario (can't clone the vault to delete it) | ~½ day |
| 10 | `10__command-graph-brief.md` | Friendly "command not found" error formatter + `Schema__Command_Graph` (auto-populated + curated metadata) + smart suggestions ("did you mean: vault info?") + `sgit dev commands {list,graph,find}`. JSON export feeds future visualisation track | ~1.5 days |

**Total remaining effort:** ~5 days of dev work + reviewer fix passes.

After Brief 10, the v0.14.x pack is complete and the **visualisation track** is unblocked.

---

## 4. Recommended landing order

```
1. Brief 21  — Brief 20 follow-ups (history reset --fetch + integration tests)  ~½ day
2. Brief 16  — Brief 15 cosmetic follow-ups (§3b + §3c remaining)                ~30 min
3. Brief 17  — Commit-id prefix resolution                                       ~½ day
4. Brief 12  — Vault move cleanup pass (silent re-encryption fallbacks etc.)     ~½ day
5. Brief 09  — Schema-parse error handling (helper used by later briefs)         ~½ day
6. Brief 06  — Dotfile tracking (drops blanket rule so .vault-settings.json works) ~½ day
7. Brief 07  — .vault-settings.json + initial commit (depends on 06)             ~1 day
8. Brief 08  — --vault-key flag for headless admin                               ~½ day
9. Brief 10  — Command graph + suggestions (largest; feeds visualisation)        ~1.5 days
```

Rationale:
- **21 first** — confirmed real-world gap (conductor agent had to full-re-clone); small.
- **16 second** — closes the open cosmetic items; ~30 min.
- **17 third** — small UX fix; copy-paste-from-log should work.
- **12 fourth** — addresses move follow-ups while context is fresh.
- **09 fifth** — `parse_or_raise` helper should exist before 06 + 07 add new schema-parse boundaries.
- **06 sixth** — drops blanket dotfile exclusion so `.vault-settings.json` is naturally trackable in 07.
- **07 seventh** — depends on 06; introduces new schema-parse boundary that adopts 09's helper.
- **08 eighth** — independent; placed here for momentum.
- **10 last** — biggest piece; JSON export is the natural bridge into visualisation.

---

## 5. Review and feedback docs (informational, not action items)

These capture the SGit team's analysis of incoming designs from sibling teams:

| Doc | Audience | Subject |
|---|---|---|
| `team/humans/dinis_cruz/claude-code-web/05/07/sg-send-api__public-vault-rfc-response.md` | SG/Send API team | Public Vault RFC v0.27.5 response — simplified design, ~5h server work + ~½ day sgit |
| `team/humans/dinis_cruz/claude-code-web/05/07/vault-web-debrief__timestamp-fields.md` | Vault Web team | Timestamp field conventions (Safe_UInt vs Safe_Str__ISO) |
| `team/humans/dinis_cruz/claude-code-web/05/08/vault-web-feedback__realtime-viewer-v022.md` | Vault Web team | Feedback on Real-Time Vault Viewer Design v0.2.2 — mandatory pre-commit stale check, tombstone handling, Public Vault integration |

These are FYI / referenced by the action briefs above but don't themselves trigger sgit-side work until the partner teams respond.

---

## 6. Visualisation track — what's next after v0.14.x

After Brief 10 ships, the visualisation track is unblocked. The pack lives at `team/villager/v0.13.x__brief-pack/visualisation/` (yes, v0.13.x — it's been there since the original planning round). The 7 briefs (v01–v07) cover:

- v01 — `sgit_show` package framework
- v02 — Vault metadata explorer (sgit show vault)
- v03 — Commit graph visualisation
- v04 — Metadata explorer (per-vault inspection)
- v05 — Tree explorer (per-commit inspection)
- v06 — Search and filter
- v07 — Commit-zip projection (architectural research)

Brief 10's `Schema__Command_Graph` JSON export is the natural data bridge — visualisation consumes it.

---

## 7. Quick reference — files in this pack

```
team/villager/v0.14.x__brief-pack/
├── 00__index.md                              ← overview + landing order
├── 00a__start-here__dev-agent-briefing.md    ← Dev Agent entry point
├── STATUS.md                                 ← THIS FILE — current status
├── 01__cli-token-rename-brief.md             ✅ DONE
├── 02__vault-move-brief.md                   ✅ DONE
├── 03__vault-move-testing-brief.md           ✅ DONE
├── 04__vault-backup-restore-brief.md         ✅ DONE
├── 05__execution-plan.md                     ← original brief-pack plan (historical)
├── 06__dotfile-tracking-brief.md             🔵 TODO
├── 07__vault-settings-brief.md               🔵 TODO
├── 08__vault-key-flag-brief.md               🔵 TODO
├── 09__schema-parse-error-brief.md           🔵 TODO
├── 10__command-graph-brief.md                🔵 TODO
├── 11__implementation-review.md              ← review of 02 + 03 + 04
├── 12__vault-move-cleanup-brief.md           🔵 TODO
├── 13__history-range-brief.md                ✅ DONE
├── 14__brief-13-and-move-fixes-review.md     ← review of 13 + move fixes
├── 15__integration-tests-brief.md            ✅ DONE
├── 16__brief-15-followups.md                 🟡 PARTIAL — §3b + §3c remain
├── 17__commit-id-resolution-brief.md         🔵 TODO
├── 18__clone-missing-blobs-brief.md          ✅ DONE
├── 19__brief-18-review.md                    ← review of 18
├── 20__merge-state-brief.md                  ✅ DONE
└── 21__brief-20-followups.md                 🔵 TODO
```

Plus `visualisation/` sub-pack (unchanged from earlier planning round) for the post-v0.14.x track.

---

## 8. How to pick up this work in a new session

1. Read `team/villager/CLAUDE.md` for team conventions.
2. Read this STATUS.md for current state.
3. Read `00a__start-here__dev-agent-briefing.md` for the Dev Agent contract.
4. Pick the next brief from §4's recommended order — open that file, read it, implement it.
5. After implementation, update STATUS.md (move the brief from TODO to DONE).
6. Write an implementation review doc as `<next-number>__<brief>-review.md` if non-trivial (follow the 11/14/19 pattern).

The pack is self-describing. Pick up where this session ended; no oral handoff needed.
