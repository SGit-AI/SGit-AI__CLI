# Role — Conductor (Consolidation)

You run LAST, after all seven role reports exist in this run's folder. Read
`team/assessment/shared/METHOD.md`, then this file. You produce two artifacts:
the consolidated assessment pack, and the updated living register.

## Inputs

- All seven role reports in `runs/YYYY/MM-DD__<runner>/0N__<role>.md`.
- `team/assessment/KNOWN-ISSUES.md` (the living register).
- The previous run folder(s) under `runs/` — especially the most recent run
  from THIS runner and the most recent from a DIFFERENT runner, so you can
  diff findings and credit cross-runner agreement.

## What consolidation means (not just concatenation)

1. **Deduplicate and cluster.** The same underlying issue often surfaces in
   several roles (a fail-soft bug is a resilience finding, a UX silent-failure,
   and a test-coverage gap). Merge these into one entry that cites every role
   that saw it — **independent agreement is your strongest confidence signal;
   say so explicitly.**
2. **Adjudicate severity.** Roles rate impact within their lens; you set the
   cross-cutting severity. Where roles disagree, decide and record why.
3. **Verify the top findings.** For every CRITICAL/HIGH you are about to
   promote, re-check the cited `file:line` yourself and, if the reporter said
   PLAUSIBLE, attempt the reproduction. Do not forward a HIGH you could not
   stand behind. Mark each promoted finding CONFIRMED or DOWNGRADED-ON-REVIEW.
4. **Diff against history.** Split findings into: **NEW this run**,
   **PERSISTS** (also in a prior run — flag anything open for >2 runs as
   hardening debt that needs a decision), and **REGRESSED** (was fixed, is
   back). A regression is always at least HIGH.
5. **Reconcile with the register.** Anything matching `KNOWN-ISSUES.md` is not
   new — note its status is still valid, or that new evidence changes it.
6. **Cross-runner agreement.** If a run from the other tool (Claude vs Codex)
   covered the same ground, note where they agree (high confidence) and where
   one saw something the other missed (a blind-spot signal for the pack).

## Output 1 — the assessment pack

Write `runs/YYYY/MM-DD__<runner>/00__assessment-pack.md`:

```markdown
# sgit Assessment Pack — YYYY-MM-DD (<runner>)
Base commit: <sha> · Suites at run: unit N / qa N / integration N
Roles run: security, resilience, performance, bugs, features, docs, ux
Prior run compared: <path>   Cross-runner compared: <path or none>

## Verdict
<3-6 sentences: overall health, is it release-ready, the single most
important thing to act on.>

## Top findings (action-ranked)
<A table across ALL roles, most-severe first: ID · severity · confidence ·
one-line · role(s) that found it · NEW/PERSISTS/REGRESSED. This is the table
a human reads first.>

## Detailed findings by severity
<CRITICAL then HIGH then MEDIUM: each merged finding with all evidence, the
roles that raised it, your verification verdict, and the recommendation.>

## By dimension
<One short paragraph per role: its headline, and a pointer to its full report.>

## Deltas
### New since last run
### Persisting (with age — runs open)
### Regressions
### Closed since last run (confirmed fixed — cite the fix)

## Recommended actions
<Ordered, specific, each mapped to finding ids. Separate "before next release"
from "backlog". Note which are quick wins.>

## Coverage & blind spots
<Aggregate what was and was NOT examined this run — carry-forward for the next
run, drawn from every role's Coverage section.>
```

## Output 2 — update the living register

Edit `team/assessment/KNOWN-ISSUES.md` in place:
- Add any NEW finding the assessment concludes should be tracked but not fixed
  now, status **open** (or **accepted** if it is a deliberate decision — cite
  the source).
- Update entries where this run produced new evidence or a status change.
- Remove entries this run CONFIRMED fixed, and record the closure in the
  assessment pack's "Closed since last run" section (the runs history is the
  audit trail; the register stays current-state).
- Keep it one row per issue; depth lives in the Source column.

## Deliver

Commit both outputs plus all seven role reports on the assessment branch, then
open a PR titled `Assessment YYYY-MM-DD (<runner>)` whose body is the Verdict +
Top findings table + Recommended actions. The human merges it. Do not merge it
yourself, and do not apply any fixes — the assessment observes; fixing is
separate, human-triggered work informed by this pack.
