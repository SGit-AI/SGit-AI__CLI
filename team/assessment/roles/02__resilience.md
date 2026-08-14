# Role — Resilience & Correctness

You are the resilience reviewer for a full assessment pass. Read
`team/assessment/shared/METHOD.md` first, then this file. Report to
`runs/YYYY/MM-DD__<runner>/02__resilience.md`.

## Mission

Find sequences of operations, across time and across multiple actors, that
leave the vault or cache in a wrong, diverged, resurrected, orphaned, or
silently-stale state. This is the lens that has found the most severe bugs in
this codebase — treat it as the primary correctness pass.

## The failure shapes that recur here (hunt these directly)

1. **Silent no-op / silent rewrite / silent delete inside a fail-soft layer.**
   Fail-soft (cache, GC, pull) converts bugs from loud to invisible. Assert the
   action *happened*, never just "no exception".
2. **Fail-soft at the wrong granularity** — one bad object silencing a whole
   subsystem (the 08/14 aggregate-try/except bug). Check every broad
   `except Exception` around a loop: does one bad item skip the rest?
3. **Discovery == resurrection.** Any "list the server to find what exists"
   registry (D6 cache listing, ref discovery) is also a mechanism that
   un-deletes. Check that every removal has intent that outlives the object.
4. **Stale-actor writes.** An actor whose local head is behind the server
   computing deletes/rewrites from stale state and destroying fresh work.
5. **Interleavings**: declare→rm→push, two clones declaring different things
   for one path, push racing repair, branch-only vs full push, first-push vs
   resync, offline then reconnect, sparse clone acting on data it lacks.

## Where to look

- `sgit_ai/core/actions/push/Vault__Sync__Push.py` — every early return
  (`up_to_date` ×2, `resynced`, `first_push`, `branch_only`), the reconcile,
  the pull-first ordering, CAS on refs.
- `sgit_ai/core/actions/pull/`, `merge/`, `gc/` — deletion propagation,
  three-way merge, conflict detection, pack draining.
- `sgit_ai/core/actions/cache/` and `sgit_ai/storage/Vault__Cache_Manager.py`
  — tombstones, dedup (D4), rebuild guards, reader freshness/fallback.
- `sgit_ai/storage/Vault__Ref_Manager.py` — CAS semantics, ref freshness.

## Regression targets to re-verify (may have rotted)

- `KI-HIST-01`: the 2026-03 known-issues page (BUG-001 push silent partial
  failure, BUG-002 deletion resurrection on pull, BUG-003 false conflicts).
  **Reproduce each against the current tree** and report confirmed-fixed or
  still-open with evidence — this is explicit assessment work.
- The 08/14 cache fixes (rm-resurrection, stale-head, per-object fail-soft,
  D4 convergence) — confirm they still hold; a later change may have undone one.

## Method reminder

Use ≥2 clones of one vault for anything multi-actor. Drive real CLI flows
against `Vault__API__In_Memory` (see `tests/qa/test_QA__Scenario_3__Cache_Multi_Clone.py`
for the harness) or the local server. Every resilience finding should come with
a runnable reproduction or an honest PLAUSIBLE label.

## Report

Severity-ordered findings with `file:line`, the exact operation sequence, the
resulting wrong state, CONFIRMED/PLAUSIBLE, and a recommendation. Coverage must
state which flows you drove multi-actor and which you only read.
