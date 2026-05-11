# Villager Orchestrator Session Debrief — v0.13.x → v0.14.x Sprint

**Session window:** 2026-05-05 to 2026-05-08
**Role:** Villager orchestrator (Opus)
**Counterparts:** SGit Dev Agent (Sonnet) on `claude/sonnet-onboarding-oMP6A` + `claude/cli-explorer-session-J3WqA`
**Branch:** `claude/villager-multi-agent-setup-sUBO6`

This debrief captures the arc of the session — what we planned, what shipped, what remains, and the discoveries we made along the way. It's intended for future-Dinis (and future-orchestrator-sessions) to read as the narrative complement to the structured `STATUS.md` in the brief pack.

---

## 1. Where we started

At session start, v0.13.x had just shipped (workflow framework, per-mode clones, migration command, layer cleanup, B07 CLI namespace cleanup, B08 workflow polish). I'd been the orchestrator across that sprint too, and the four core architectural pieces (B01-B08) were in place. The remaining v0.13.x items had been written but the implementations were incomplete.

The plan when we picked up: produce a "pre-release hardening" brief (called `00e` at the time) covering the small follow-ups before tagging v0.14.0. That set kicked off everything that followed.

---

## 2. The arc — what happened, in order

### Day 1 (2026-05-05) — v0.14.0 pre-release brief, P0 data-loss bug

Wrote `00e__v0.14.0-pre-release-brief.md` covering five items: (1) clone-resolve broad try/except masking mid-clone failures (which was the cause of an earlier "vault cloned but no key file" bug), (2) B05 lazy-fetch wiring decision, (3) B02 migration hardening (5 silent-error-swallowing sites), (4) B22 exception fallback, (5) end-to-end case-study run.

Then Dinis hit a **P0 sparse-clone data-loss bug** on his real case-study vault — a sparse clone produced a commit that deleted 189 unfetched files because `Vault__Sync__Commit.commit()` walks the local filesystem and treats absent files as deletions, with no awareness of sparse mode. Updated the pre-release brief to add §0 covering this as the highest-priority fix.

### Day 2 (2026-05-05 continued) — Brief pack consolidation

The Dev Agent landed all five items + the P0 fix from the pre-release brief. Then we consolidated the remaining v0.14.x work into a dedicated `team/villager/v0.14.x__brief-pack/` folder:

- Brief 01 — `--token` → `--as` rename (already done)
- Brief 02 — `sgit vault move` (transactional rotation + server move, stable object IDs)
- Brief 03 — vault move test matrix
- Brief 04 — `sgit vault backup/restore/backups`

Plus an execution plan (05) and start-here briefing (00a) for the Dev Agent.

The vault-move design went through a meaningful refinement during this phase. Initial proposal: re-encrypt-graph-rewrite-style. Dinis pushed back: "what if we keep the same object IDs?" That led to the actual design — deliberately break the `id == hash(ciphertext)` invariant for the rotation boundary, keep filenames stable, rely on AEAD's auth tag for tamper detection. Much cleaner. Plus the SG/Send tombstone behaviour (delete writes a permanent tombstone) led to the Step 8 ordering correction (atomic local rename FIRST, server delete SECOND).

### Day 3 (2026-05-05/06) — Brief 02 implementation + a real data-loss bug

Brief 02 landed. Reviewed at `11__implementation-review.md` — verdict GO, with one P1 follow-up (silent `except: pass` in re-encryption). Two `vault move` UX fixes landed (base_url resolution, fail-early-on-missing-token).

Then **Dinis hit a real data-loss bug** on his case-study vault during a real `sgit vault move`. The Brief 15 §2a check we'd added (commit-graph integrity walk) fired and aborted the move with "Local vault is missing 35 objects." That fix saved him from corruption. But it surfaced an upstream issue: **the local clone was incomplete because sgit's clone only downloads HEAD-tree blobs, not historical blobs.**

This was the root cause of an earlier corrupted-vault incident I'd misdiagnosed at the symptom level (the move was shipping incomplete vaults; I'd specified the §2a integrity check as the fix, which prevented further damage but didn't address WHY clones were missing objects).

### Day 4 (2026-05-07) — Brief 18 (critical), Brief 13 (history range), Brief 15 (move bug fixes + integration tests)

Brief 15 was written quickly in response to the "we don't have integration tests" gap that let the data-loss bug ship past 102 unit tests. It bundled three live move bugs (Validate_Local doesn't walk commit graph; empty old_vault_id in backup filename; new vault-key not displayed in success output) plus mandatory integration tests for move/backup/restore. Brief 18 then captured the root cause of the broader bug: clone needs to download every blob reachable from every tree across all commits, not just HEAD's.

Brief 13 (history log range syntax) landed in parallel — small independent addition for a conductor-style agent's use case.

Both shipped. Reviews at `14__brief-13-and-move-fixes-review.md` and `19__brief-18-review.md`. Verdict: GO on both.

### Day 5 (2026-05-07/08) — Public Vault RFC, Vault Web feedback, Brief 20 (merge state)

Two cross-team artifacts:

1. **Public Vault RFC response** to the SG/Send API team. Their initial RFC was complex (full new vault type); after Dinis's clarifications, the design simplified to: existing vault flow + one read_key file + `X-Vault-Public` header for bucket routing + optional CloudFront for Phase 2. Estimated ~5h server work + ~½ day sgit-side.

2. **Vault Web team feedback** on their Real-Time Viewer v0.2.2. Their proposal (drop the working-branch model, single ref against named HEAD) was architecturally right but pre-dated our v0.14.x work. Sent feedback covering mandatory pre-commit stale check, tombstone handling, Public Vault integration, schema alignment (`.vault-settings.json` is THEIR filename — we updated Brief 07 to match), and verified that their history-rendering UI requires Brief-18-style historical-blob fetching.

Then a real-world incident: two agents (@Content and a conductor agent) got stuck in a conflict loop on the same vault, no escape route. The pull output promised `sgit merge-abort` but the command didn't exist. Brief 20 was written to make merge-in-progress a first-class state. Two equally-supported resolution flows (capture-then-resolve, agent-friendly DEFAULT; resolve-then-merge-commit, git-style). Plus push refusal with `.conflict` files (with `--push-conflict` override), pull refusal during merge, status surfacing.

Brief 20 landed (commit `ed5189f`) with 20 unit tests but zero integration tests — the executor silently skipped the 5 integration tests the brief specified. The conductor agent's recovery report from the same day confirmed the `--fetch` gap in `sgit history reset`: standard clones don't cache the parent commit you want to reset to, so the documented recovery path was unavailable. Without `--fetch`, recovery required a full re-clone.

Brief 21 was written to cover both gaps (Brief 20's missing integration tests + the `history reset --fetch` flag). ~½ day estimated.

---

## 3. What landed (DONE)

8 implementation briefs shipped + 3 implementation reviews:

| Brief | What |
|---|---|
| 01 | `--token` → `--as` rename on share/publish/export |
| 02 | `sgit vault move` — transactional key rotation + optional server move, stable object IDs |
| 03 | vault move test matrix (multi-round QA + transaction tests) |
| 04 | `sgit vault backup/restore/backups` |
| 13 | `sgit history log A..B` range syntax + `--files / --patch / --json` modes |
| 15 | Move bug fixes (Validate_Local commit graph walk, empty vault_id guard, new-key display) + integration test discipline |
| 18 | Clone full-history blobs (P0 data-integrity fix) + auto-repair in move's Validate_Local |
| 20 | Merge-in-progress first-class state (merge-abort, resolve, two resolution flows, push/pull refusals) |

Implementation reviews:
- `11__implementation-review.md` — review of 02 + 03 + 04
- `14__brief-13-and-move-fixes-review.md` — review of 13 + move follow-up fixes
- `19__brief-18-review.md` — review of 18

Plus the cross-team docs:
- Public Vault RFC response to SG/Send API team
- Vault Web team feedback on timestamp conventions
- Vault Web team feedback on Real-Time Viewer v0.2.2

---

## 4. What's planned but NOT yet implemented

See `team/villager/v0.14.x__brief-pack/STATUS.md` for the full table. Summary:

- **Brief 21** — Brief 20 follow-ups (`history reset --fetch` + 5 missing integration tests)
- **Brief 16 (partial)** — §3b filter comment + §3c path-update cleanup
- **Brief 17** — Commit-id prefix resolution at CLI
- **Brief 12** — Vault move cleanup pass (silent re-encryption fallbacks, store_at refactor)
- **Brief 09** — Schema-parse error handling helper
- **Brief 06** — Dotfile tracking (drop blanket rule + `sgit inspect ignored`)
- **Brief 07** — `.vault-settings.json` in tree + initial commit on `sgit init`
- **Brief 08** — `--vault-key` flag for headless admin commands
- **Brief 10** — Command graph + smart suggestions + JSON export

Total ~5 days of dev work remains. After Brief 10, the visualisation track is unblocked.

---

## 5. Lessons + patterns worth carrying forward

### 5a. The "integration tests catch what unit tests can't" lesson, twice

Two separate bugs in this session shipped past extensive unit tests:

1. **Vault move's `base_url=None`** crash — 92 unit tests against `Vault__API__In_Memory` (which ignores base_url) didn't catch it. Caught by Dinis on first live use.
2. **The conflict-loop / data-integrity scenario** — 20 unit tests proved merge state mechanics worked in isolation, but the integration test that would have proven the loop is structurally impossible against a real server was silently skipped.

Both led to brief 15 (the integration-test discipline brief, which made it the standard going forward) and brief 21 (which re-spec'd the integration tests that should have landed with Brief 20).

The pattern: **any action class that touches the network needs an integration test against the real local SG/Send server.** The `tests/integration/conftest.py` fixture (`vault_api`, `crypto`, `temp_dir`) makes this cheap. The cost of skipping is "Dinis discovers the bug on a real vault."

Worth a one-line addition to the start-here briefing for next sessions: *"If a brief specifies integration tests by name, land them or explicitly defer them in the commit message. Don't silently skip."* (Added to Brief 21 §7.)

### 5b. Architectural decisions that involved Dinis's input

A few moments where the executor's natural path would have produced worse outcomes, and Dinis's intuition saved time:

- **Vault move object-ID stability** (Day 2). I'd specified a graph-rewrite approach; Dinis pushed for stable IDs. The actual design (deliberately break the CAS invariant for rotated objects) is cleaner and produced a much smaller change.
- **`.vault-settings.json` as the canonical name** (Day 5). Brief 07 had specified `.vault-settings` (no extension); the Vault Web team's design used `.vault-settings.json`. Dinis: "if we're creating a different one, fix on our side." Updated 41 references in Brief 07. Interop maintained.
- **Linear capture-then-resolve flow** in Brief 20. I'd specified the git-style "resolve-then-merge-commit" path. Dinis added: "we should also support committing the conflicts first, then resolving — each step is a regular commit." Brief 20 §3c now supports BOTH flows; the agent-friendly linear flow is the default.
- **`--push-conflict` override** (Brief 20). Dinis added: "refuse push if .conflict files exist, override with --push-conflict for cases where the agent wants to share a stuck state." Clean and explicit.

The pattern: when the architectural direction comes from someone who's actually USING the system, the design improves. The executor (and orchestrator) over-engineers in absence of usage signal.

### 5c. The "discoverable status page" pattern

Earlier sessions had the brief pack but no single discoverable status. Picking up a session required reading the index + every brief to know what was DONE vs TODO. Inefficient.

This session ends with a `STATUS.md` at a predictable location, marked as the first file to read. Combined with the `00a__start-here__dev-agent-briefing.md` (canonical Dev Agent entry point), there's a clean handoff surface for future sessions.

Worth maintaining: update STATUS.md after every brief lands. Don't let it drift.

### 5d. Two-session executor + reviewer pattern

The two-session pattern (Sonnet executor on its own branch + Sonnet reviewer doing Reviewer Fix passes) has been steady throughout. The Reviewer Fix 13 in Brief 18 caught a thread-pool cap that wasn't in my brief but mattered for vaults with hundreds of historical blobs. The Reviewer Fix 8 / 11 / 12 caught CLAUDE.md compliance issues consistently.

Pattern is working; preserve it.

---

## 6. Open questions / decisions deferred to future sessions

1. **Public Vault implementation timing** — the SG/Send API team's Phase 1 (bucket + header routing, ~5h server work) is on their queue. When it ships, sgit's brief 13-shaped follow-up is ~½ day. Not yet written as a brief because it's blocked on the server work.

2. **Vault Web team integration** — they're working on Real-Time Viewer v0.2.2+ incorporating our feedback. No sgit-side action items pending until they push back with questions.

3. **The visualisation track** — fully designed in `team/villager/v0.13.x__brief-pack/visualisation/` but blocked on Brief 10 (command graph) shipping the JSON export that visualisation consumes. After v0.14.x completes, this is the natural next sprint.

4. **Browser-side merge-state UX** — once Brief 20 lands and stabilises, the web viewer team will likely need to integrate. Not blocking; cross-team coordination for later.

---

## 7. Health check on the codebase

Current state (post-Brief 20 merge):

- **3,450+ unit tests passing.**
- **Integration suite** has tests for: clone full-history blobs, vault move (4 tests), vault backup (2 tests), vault restore (2 tests), move-backup roundtrip (1 test). Brief 20's 5 integration tests are TODO.
- **KNOWN_VIOLATIONS** unchanged at 7 (all legitimate dev-plugin entries).
- **Public Vault** support: 0% (waiting on server work).
- **Visualisation track:** 0% (waiting on Brief 10).

The shipped v0.14.x release (after Briefs 01-04 + 13 + 15 + 18 + 20) is the most useful sgit yet: per-mode clones, transactional vault move, backup/restore, history range + JSON for agents, full-history blob downloading, working merge-conflict resolution. All against integration tests where it matters.

---

## 8. Where to pick this up

For the next session orchestrator or Dev Agent:

1. **Read first:** `team/villager/v0.14.x__brief-pack/STATUS.md`.
2. **Pick the next brief** from §4 of STATUS (currently: Brief 21 → Brief 16 remaining → Brief 17 → ...).
3. **Read the brief**, implement it, run unit + integration tests.
4. **Write an implementation review** as `<next-number>__<brief>-review.md` if non-trivial.
5. **Update STATUS.md** to move the brief from TODO to DONE.

The pattern is self-sustaining. No oral handoff needed.

— Villager orchestrator (Opus), 2026-05-08
