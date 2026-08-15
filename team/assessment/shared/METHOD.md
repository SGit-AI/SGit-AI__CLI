# METHOD — Ground Rules for Every Assessment Role

Read this file completely before your role file. It exists because the lessons
in it were each paid for with a real shipped bug.

## 1. Grounding reads (in this order, before any analysis)

1. `CLAUDE.md` (repo root) — project rules, Type_Safe conventions, commands.
2. `team/assessment/KNOWN-ISSUES.md` — what is already known and what is
   *accepted*. You exist to find what is NOT on this list.
3. The two most recent folders under `team/assessment/runs/` — what was
   reported last time (prefer one run from a different runner if available).
4. Architecture ground truth, skimmed for your role's needs:
   - `team/explorer/architect/contracts/` — wire formats, decisions D1–D10,
     crypto contracts, key-capability model
   - `team/explorer/architect/reviews/` — prior review passes (08/13 and
     08/14 are the method exemplars)
   - `team/explorer/historian/reality/` — current-state documents

## 2. The evidence standard

- **Every finding needs `file:line` evidence** from the current tree. A claim
  you cannot anchor to code is a question, not a finding — put it in the
  "Questions" section of your report instead.
- **Probe, don't just read.** The highest-severity bugs found in this repo
  (unicode cache self-destruction, rm-resurrection, stale-head deletion) were
  all invisible to code reading and trivial to see empirically. If your
  finding has a runnable shape, run it: write a throwaway script in /tmp,
  drive the CLI against `Vault__API__In_Memory`, or use the real local server
  (`tests/integration/conftest.py` shows how). State in the finding whether it
  is **CONFIRMED** (reproduced) or **PLAUSIBLE** (read-only).
- **Multi-actor by default.** Single-copy tests hide whole bug classes here.
  When probing sync/cache behaviour, use at least two clones of one vault.
- **Positive-outcome checks.** In fail-soft layers (cache, GC, pulls), "no
  error" proves nothing. Verify the action *happened* (object updated, file
  deleted on the server, content followed).
- Run the suites before trusting your probes: `pytest tests/unit/ -n auto`
  must be green on your branch; if it is not, that is finding #1.

## 3. What NOT to report

- Anything in `KNOWN-ISSUES.md` with status **accepted** or **open**, unless
  you have NEW evidence (changed severity, a working exploit, a regression).
  Then report it as `KI-ref: <id>` with the new evidence.
- Anything a previous run reported that is unchanged — reference it instead.
- Style preferences that contradict `CLAUDE.md` conventions. The repo's
  conventions win.
- Hypothetical issues in code paths that cannot be reached (prove
  reachability or file it as a Question).

## 4. Severity and confidence

Severity (impact if real): **CRITICAL** (data loss, key/plaintext exposure,
zero-knowledge break) · **HIGH** (wrong results, silent corruption, DoS of a
core flow) · **MEDIUM** (degraded/incorrect under realistic edge conditions)
· **LOW** (papercut, hardening) · **INFO** (observation worth recording).

Confidence: **CONFIRMED** (reproduced empirically) · **PLAUSIBLE** (strong
code-reading case) · **SPECULATIVE** (allowed only in Questions).

## 5. Report format (one file per role)

Write to `team/assessment/runs/YYYY/MM-DD__<runner>/NN__<role>.md`:

```markdown
# <Role> Assessment — YYYY-MM-DD (<runner>)
Base commit: <sha>   Suites: unit <n> passed / qa <n> / integration <n>

## Summary          ← 5-10 sentences, written LAST; verdict first
## Findings         ← one ### section per finding, ordered by severity
### <ROLE>-01 — <title>   [SEVERITY / CONFIDENCE]
Evidence: path/file.py:123
<what, why it matters, how reproduced or why plausible>
Recommendation: <specific, actionable>
## Questions        ← speculative items, phrased as questions for humans
## Coverage         ← what you examined and what you did NOT get to (be honest;
                      the conductor and the next run rely on this)
```

Finding ids are `SEC-`, `RES-`, `PERF-`, `BUG-`, `FEAT-`, `DOC-`, `UX-` + a
two-digit number, unique within the run.

## 6. Independence

Do not read the other roles' reports for this run. Overlap between roles is
expected and useful — the conductor uses agreement between independent passes
as a confidence signal. Coordinating destroys that signal.

## 7. Repo hygiene

Work on the run's `assessment/…` branch. Commit only your report and (if you
wrote probes worth keeping) new tests under `tests/`. Never "fix" what you
find — assessments observe; fixes are separate, human-approved work. Never
touch `team/humans/dinis_cruz/briefs/` (read-only by team rule).
