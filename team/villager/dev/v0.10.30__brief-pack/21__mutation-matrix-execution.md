# Brief 21 — Mutation matrix execution

**Owner role:** **Villager AppSec** (designs / verifies) + **Villager QA**
(executes mutations live)
**Status:** Ready to execute. **Best after briefs 10–20 land** because
several of them already close mutation rows (M5, M7, M8, M10, M1, M2, M3).
**Prerequisites:** Briefs 12, 13, 15, 18, 20 strongly recommended first.
**Estimated effort:** ~6 hours per the original AppSec plan, less if
several rows are already closed by earlier briefs.
**Touches:** test additions only; no source. Mutations are applied and
reverted in-flight, never committed.

> ⚠️ **READ FIRST — Architectural addendum supersedes the mutation approach below:**
> `team/villager/dev/v0.10.30__brief-pack/21b__addendum-mutation-ci-architecture.md`
>
> The `git stash` / `git checkout --` approach described in the Hard Rules
> section below is **replaced** by a `git worktree` orchestrator
> (`tests/mutation/run_mutations.py`) for CI safety.  The addendum defines
> the exact scope of what brief 21 must build: `mutations.py` catalogue,
> `run_mutations.py` orchestrator, missing closer tests, M00 update, and
> the `run-mutation-tests` CI job.  Read 21b before writing any code.

---

## Why this brief exists

`team/villager/appsec/v0.10.30/M00__mutation-test-matrix.md` defines
10 surgical mutations + 5 baseline. AppSec predicted 6 of 10 undetected
by current tests. By the time this brief runs, several rows should
already have closer tests from earlier briefs:

| # | Mutation | Predicted | Closer brief | Expected status by brief 21 start |
|---|---|---|---|---|
| M1 | HMAC → SHA-256 (1) | U | brief 20 | D |
| M2 | HMAC key constant | U | brief 20 | D |
| M3 | random IV instead of HMAC | P | brief 20 | D |
| M4 | rmtree → pass | D | (already) | D |
| M5 | maxsize=0 | U | brief 12 | D |
| M6 | omit read_key write | D | (already) | D |
| M7 | drop encryption in write_file | U | brief 13 (partial) + this brief | D |
| M8 | extra field in push_state | U | brief 15 + 16 | D |
| M9 | probe writes disk artefact | U | this brief | D |
| M10 | drop write-key header | U (in-mem) | brief 18 | D |

Brief 21's job is to **execute** every row live (apply mutation, run
tests, observe pass/fail, write missing test, revert mutation) and
confirm the predicted status. Any row that's still U after the closer
brief is a real gap — write the missing test in this brief.

---

## Required reading

1. This brief.
2. `team/villager/appsec/appsec__ROLE.md` — adversarial testing protocol.
3. `team/villager/qa/qa__ROLE.md` — mutation execution.
4. `team/villager/appsec/v0.10.30/M00__mutation-test-matrix.md`.
5. Whichever earlier briefs (10–20) have landed by the time this brief
   starts, to know which rows are already covered.

---

## Scope

**In scope:**
- For each row M1–M10 + B1–B5:
  1. Apply the mutation as specified (one-line edit in the target file).
  2. Run the affected tests + the full suite.
  3. Observe pass / fail.
  4. **Revert the mutation immediately** — even if tests fail.
  5. If observed status differs from predicted: investigate.
  6. If currently undetected: write the missing test, watch it fail
     against the mutation, revert, observe it now passes.
- Update each row in M00 to the live-observed status.
- Special handling for M9 (probe writes disk artefact) — write a test
  that asserts probe leaves no disk state, then verify the test catches
  a synthetic disk-write injection.
- Special handling for M10 (auth header) — verified by brief 18's
  integration test; cross-reference and confirm.

**Out of scope:**
- Adding new mutation rows. The matrix is fixed for v0.10.30.
- Refactoring source to make tests easier to write — escalate as Dev
  follow-up if needed.
- Committing any mutation. **Mutations exist in working-tree only and
  are reverted before commit.** Use `git stash` / `git checkout --` to
  revert.

**Hard rules:**
- **Never commit a mutation.** If you forget, fix immediately and force-
  drop the mutation commit (only if you haven't pushed). If you've
  pushed a mutation, escalate to Dinis immediately.
- No mocks.
- Coverage must not regress.
- Tests under Phase B parallel CI shape.

---

## Acceptance criteria

- [ ] Every row of M00 has a live-observed status (no row remains
      "predicted").
- [ ] Every row that was U or P at predict time is now D — either via
      a closer brief or via a test added in this brief.
- [ ] No mutation was committed. Verify with `git log` and `git diff
      origin/dev -- sgit_ai/`.
- [ ] Suite ≥ 2,105 + N passing, coverage ≥ 86%.
- [ ] No new mocks.
- [ ] M00 doc updated with a §"Live-Run Results" section.

---

## Deliverables

1. M00 doc update (live-observed statuses).
2. Test file additions for any row not closed by an earlier brief.
3. Closeout note appended to `team/villager/appsec/v0.10.30/99__consolidated-report.md`
   with the new "Detected today" count.

Commit message:
```
test(appsec): execute mutation matrix M00 — all rows D

Closes mutation matrix execution per AppSec brief 21. Every M-row and
B-row now executed live; observed status matches or exceeds predicted.
Any rows that were U at predict time and not closed by briefs 10–20
have new closer tests in this commit. No mutation committed —
mutations applied, observed, and reverted.

https://claude.ai/code/session_<id>
```

---

## When done

Return a ≤ 250-word summary:
1. Live-observed status per row.
2. Tests added in this brief (file:test count).
3. Coverage delta.
4. Any divergence from predict-time prediction (and why).
5. Confirmation that no mutation was committed.
