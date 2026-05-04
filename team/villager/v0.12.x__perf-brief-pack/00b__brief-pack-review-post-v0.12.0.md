# Brief-Pack Review — Post-v0.12.0

**Date:** 2026-05-04
**Author:** Villager orchestrator (chat review)
**Pack:** `team/villager/v0.12.x__perf-brief-pack/`

The pack was authored when the codebase looked very different. This
file inventories every brief and notes what changed during v0.12.0
that affects each one. **TL;DR — most briefs are fine; B06, B12, and
B13 need substantive updates before execution.**

---

## What changed during v0.12.0 that affects the pack

| Change | Impact |
|---|---|
| `Vault__Sync.py` 3,032 LOC → 258-line facade with 12 sub-classes | B06 / B12 / B13 had assumed the monolith |
| Test framework + 98% coverage shipped | B07 baseline numbers stale; verification gates can be tightened |
| `tests/conftest.py` + `tests/_helpers/` real now | Several briefs referenced these as future work |
| `Schema__Push_State`, `Schema__Clone_Mode`, `Schema__Local_Config` shipped | B10 (migration command) inventory needs update |
| Mutation orchestrator at `tests/mutation/run_mutations.py` exists | Briefs that need mutation verification can reference real infra |
| Brief 05 surgical-write CLI shipped (`write`, `cat --id`, `ls --ids/--json`, `clone --read-key`, `derive-keys` read-only-mode) | B02 / B03 / B04 inventory grew |
| Brief 23 (E3 + E4 carry-forward) authored but not executed | B05 / B06 should reference whether to fold E3/E4 in |

---

## Per-brief review

### B01 — Instrumentation tools

**Status:** ✅ No update needed.
**Reason:** Pure new code under `sgit_ai/cli/dev/`. The Phase-0 tools
are independent of the sub-class split. Targets the existing
`_clone_with_keys` (now in `Vault__Sync__Clone.py:1276` instead of
`Vault__Sync.py:1276`). Minor: update the line reference in the brief
when the executor reads source.

### B02 — CLI restructure: namespaces

**Status:** ⚠️ Minor update needed.
**What to update:**
- The current 67 top-level commands count includes the new Brief 05
  surface (`write`, `cat`, `ls`, etc.). These already exist; they're
  not "new" commands to add — they're existing commands to namespace.
- `derive-keys` now has read-only-mode. Note for placement decision.
- The cruft inventory list should be re-grep'd against the current
  `CLI__Main.py` (post-Brief-05).

**Effort to update:** ~30 min — re-run `grep "add_parser"
sgit_ai/cli/CLI__Main.py` and refresh the inventory table.

### B03 — CLI restructure: clone family + `create`

**Status:** ⚠️ Update needed.
**What changed:**
- `sgit clone --read-key` already exists (per Brief 05). The brief
  says "**`clone-headless`**: NEW top-level command. Stub..." — but
  read-only clone via `clone --read-key` is partly the headless
  use-case. Worth distinguishing: `clone-headless` is an online-only
  ephemeral clone (no `.sg_vault/` or cache-only); `clone --read-key`
  is a read-only-but-still-on-disk clone. Different things.
- `clone --upgrade` (Workstream A-2 from Brief 06) is a deferred
  feature. If A-2 ships before B03, this brief should account for it.
- `clone-range` semantics still need to be designed (commit range
  syntax `<from>..<to>`).

**Effort to update:** ~1 hour.

### B04 — Context-aware visibility

**Status:** ⚠️ Minor update needed.
**What to update:**
- Visibility metadata table needs entries for the new Brief 05
  commands (`write`, `cat`, `ls`).
- Otherwise the design (3 contexts: outside / inside-working /
  inside-bare + universal) is unchanged.

**Effort to update:** ~30 min.

### B05 — Workflow framework (implementation)

**Status:** ✅ No update needed.
**Reason:** The framework is abstract — `Step` / `Workflow` /
`Workflow__Workspace` primitives. Independent of any current source
location. Brief is implementation-ready.

**Optional cross-reference:** add a note about the transaction-log
emission hook (Step 3.5 was added during the earlier review pass —
verify this is captured in the brief; if so, no update).

### B06 — Apply workflow to clone

**Status:** 🔴 **MAJOR update needed.**
**What changed:**
- `_clone_with_keys` is now in `sgit_ai/sync/Vault__Sync__Clone.py`,
  not `sgit_ai/sync/Vault__Sync.py:1276–1410`.
- The 10-step decomposition in the brief still applies, but the
  refactor target is different. The brief currently says "Refactor
  the existing `_clone_with_keys` (`sgit_ai/sync/Vault__Sync.py:
  1276–1410`)". That's stale.
- The workflow class lands at `sgit_ai/workflow/clone/Workflow__Clone.py`
  initially (per the brief), then relocates to
  `sgit_ai/core/actions/clone/` after B13. The brief acknowledges
  this; just verify the wording is right.
- **Brief 23 (E3 + E4 carry-forward) is relevant**: `Vault__Graph_Walk`
  is the natural step to extract during the workflow refactor. B06
  should explicitly fold E3 in (as `Step__Clone__Walk_Trees`) rather
  than leave it as a separate brief. **Recommendation: merge B23 E3
  into B06**, leave E4 (batch_download) for B23 to ship standalone.

**Effort to update:** ~1.5 hours — retarget paths, fold in E3 from
B23, decide E4 placement.

### B07 — Diagnose case-study

**Status:** ⚠️ Minor update needed.
**What to update:**
- Sprint-overview baseline numbers ("285s warm / 2,367 tests / 88%")
  are stale. Current: ~258s warm / 2,748+ tests / 98%.
- The 5 hypotheses (H1–H5) are still the right framing.
- Tooling (B01) is unchanged.

**Effort to update:** ~15 min — refresh the baseline table.

### B08 — Server clone packs

**Status:** ✅ No update needed.
**Reason:** Server-side design. Independent of client-side refactor.
The wire format spec is still to be authored in B08's Phase 1.

### B09 — Per-mode clone implementations

**Status:** ⚠️ Minor update needed.
**What changed:**
- `clone-headless` design needs to distinguish from `clone --read-key`
  (per B03's note above). One sentence in the brief is enough.
- `clone-branch` lazy-history logic — its tests should consume
  `vault_with_N_commits` fixture (now exists).

**Effort to update:** ~30 min.

### B10 — Migration command

**Status:** ⚠️ Minor update needed.
**What changed:**
- Schema migrations referenced in the brief (`Migration__Schema_Push_State`,
  `Migration__Schema_Clone_Mode`, `Migration__Schema_Local_Config_Extension`)
  are **already done** — the schemas exist now. These migration slots
  are no-op stubs; the brief should clarify that.
- The first real migration (`Migration__Server_Pack_Prebuild`) stands.

**Effort to update:** ~30 min.

### B12 — Layered restructure: Storage layer

**Status:** 🔴 **MAJOR update needed.**
**What changed:**
- The B22 v0.10.30 work already moved most of `Vault__Sync` into
  sub-classes. The Storage extraction (Vault__Object_Store,
  Vault__Ref_Manager, Vault__Sub_Tree, Vault__Branch_Manager,
  Vault__Key_Manager, Vault__Storage) is now a **smaller, lower-risk
  move** because the sub-classes already use these as dependencies
  cleanly.
- Architect move plan (`changes__storage-move-plan.md` referenced by
  the brief) should be re-derived against the post-B22 codebase.
- Layer-import enforcement test still applies.
- `secrets/` fold-in decision still pending.

**Effort to update:** ~2 hours — re-survey the post-B22 dep graph,
update the migration map, simplify the risk note.

### B13 — Layered restructure: Core + Network

**Status:** 🔴 **MAJOR update needed.**
**What changed:**
- The "dissolve `Vault__Sync.py` (3,032 LOC) into `core/actions/<command>/`"
  framing is wrong now. `Vault__Sync.py` is already 258 LOC + 12
  sub-classes. The remaining work is **moving the 12 sub-classes**
  into `core/actions/<command>/` and then converting them to workflows
  (after B06 lands).
- This is now **substantially less risky** than originally framed.
  Each sub-class moves as one commit; existing sub-class tests transfer
  unchanged.
- `api/` + `transfer/` consolidation under `network/` stands.
- `pki/` fold under `crypto/pki/` stands.

**Effort to update:** ~3 hours — rewrite Phase 1 (the extraction is
no longer "dissolve a 3,032-LOC monolith"; it's "relocate 12 already-
extracted sub-classes"). The acceptance criteria + layer-import test
extension are unchanged.

### B14 — Plugin system

**Status:** ✅ No update needed.
**Reason:** Plugin loader + read-only namespace migration. The
namespaces exist regardless of where the read-only handlers live.
B14 still works against the post-B13 layout.

**Optional:** add a note that the new `dev workflow` CLI from B05 is
loaded by the dev plugin once that plugin exists.

### B15 — Push / pull / fetch generalize

**Status:** ⚠️ Minor update needed.
**What changed:**
- `Vault__Sync__Pull.py` and `Vault__Sync__Push.py` already exist as
  separate files (per B22). The "shared step library" idea still
  applies; the source location for the workflow refactor is now
  per-sub-class, not per-method-in-Vault__Sync.
- `_fetch_missing_objects` (B11/B15 references) is now in
  `Vault__Sync__Pull.py`.

**Effort to update:** ~45 min — retarget paths, simplify the "split
push/pull/fetch" framing.

---

## Summary table

| Brief | Update needed | Effort |
|---|---|---:|
| B01 | None (line-ref refresh during execution) | — |
| B02 | Minor — re-run inventory grep | 30 min |
| B03 | Update — `clone --read-key` distinction; `clone --upgrade` if A-2 ships | 1 h |
| B04 | Minor — visibility table for new commands | 30 min |
| B05 | None | — |
| B06 | **MAJOR** — retarget paths, fold E3 from B23 | 1.5 h |
| B07 | Minor — refresh baseline numbers | 15 min |
| B08 | None | — |
| B09 | Minor — clone-headless distinction; fixture references | 30 min |
| B10 | Minor — schema migrations are already done | 30 min |
| B12 | **MAJOR** — re-derive migration map post-B22 | 2 h |
| B13 | **MAJOR** — extraction is much smaller now | 3 h |
| B14 | None | — |
| B15 | Minor — retarget paths to existing sub-classes | 45 min |

**Total update work: ~10 hours.** Three majors (B06, B12, B13) +
five minors (B02, B03, B04, B07, B09, B10, B15).

---

## Recommended approach

**Don't update all briefs up front.** The pattern v0.10.30 used was:
update the brief just-in-time before its executor agent picks it up.
That worked well — kept the docs honest without stale-update churn.

Apply the same here:

1. **B01 / B05 / B07 / B08** — execute immediately when ready; no doc update.
2. **B02 / B03 / B04 / B09 / B10 / B15** — quick refresh (≤1h each)
   when the executor is about to start.
3. **B06 / B12 / B13** — rewrite the affected sections **before**
   launching the executor. Architect-led, ~6.5 hours total.

The Architect can do B06 / B12 / B13 updates in one focused session.
B12 + B13 are coupled (both layered restructure); B06 is independent
but needs the same Architect's attention.

---

## What this review does NOT do

- It doesn't update any brief. Each update happens just-in-time.
- It doesn't reorder the sequencing graph. Same dependency graph;
  just lower risk on B12 / B13 because B22 did half the work.
- It doesn't add new briefs. Brief 23 (E3 + E4 carry-forward) is
  already in the v0.10.30 pack and recommended for folding into B06.
