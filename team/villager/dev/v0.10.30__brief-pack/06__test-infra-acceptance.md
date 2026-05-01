# Brief 06 — Test Infrastructure Acceptance Gate (v0.10.30)

**Phase:** B — Improve (gate)
**Owner role:** **Villager DevOps** (primary, owns the measurements) +
**Villager QA** (signs off on coverage and behaviour preservation)
**Status:** BLOCKED until briefs 04 and 05 are merged.
**Prerequisites:** Briefs 01, 02, 04, 05 merged.
**Estimated effort:** ~1–2 hours
**Touches:** measurement only — no source / test / config changes.

---

## Why this brief exists

This is the gate between Phase B (test infrastructure improvements) and
the deferred queue (briefs 10–20: hardening, schemas, bug fix, crypto
tests, mutation matrix, Vault__Sync.py split).

**Per the next-phase plan §3, no brief from the deferred queue may
start until brief 06 is signed off.** This brief is the formal sign-off:
re-measure everything, compare to baselines, decide pass/fail.

If the gate fails, brief 06 returns the work to brief 03 for redesign or
brief 04/05 for additional iteration. Do not relax the targets to make
the gate pass.

---

## Required reading

1. This brief.
2. `team/villager/devops/devops__ROLE.md` and
   `team/villager/qa/qa__ROLE.md` — both roles share ownership.
3. `team/villager/qa/v0.10.30__coverage-baseline.md` — baseline coverage.
4. `team/villager/devops/v0.10.30__runtime-baseline.md` — baseline runtime.
5. `team/villager/dev/v0.10.30__shared-fixtures-design.md` — what brief
   04 was supposed to deliver (with §8 implementation log).
6. `team/villager/devops/v0.10.30__parallelization-report.md` — what
   brief 05 delivered.

---

## What you measure

### A. Re-run coverage (mirror brief 01)

```
pytest tests/unit/ --cov=sgit_ai --cov-report=term-missing --cov-report=json:coverage.json
```

Capture: coverage %, lines covered, lines total, test counts, runtime.

### B. Re-run runtime (mirror brief 02)

Three runs of `time pytest tests/unit/ -q`. Cold + warm samples.

### C. Re-run parallelization

```
pytest tests/unit/ -n auto -m "not no_parallel"
pytest tests/unit/ -m no_parallel
```

Combined wall clock = the post-Phase-B real CI cost.

### D. Determinism check

Run the suite twice in succession with random ordering enabled (if a
randomly-ordering plugin is installed) or with the default ordering.
Results must be identical. If a test passes one run and fails another,
that's a regression introduced in Phase B.

### E. No-mocks regression check

```
grep -rn 'unittest.mock\|MagicMock\|@patch\|monkeypatch' tests/ | wc -l
```

Compare to brief 01 baseline of 553. The number must not increase.

### F. Source-untouched check

```
git diff --stat origin/dev -- sgit_ai/
```

Phase B was not supposed to touch `sgit_ai/` at all. The diff must be
empty (or limited to whatever pre-existed before Phase B started — record
the comparison precisely).

---

## Acceptance matrix

| # | Metric | Brief 01/02 baseline | Phase B target | Phase B actual | Pass? |
|---|---|---:|---:|---:|---|
| 1 | Suite wall clock (warm serial) | 124s | ≤ 80s | … | … |
| 2 | Suite wall clock (combined CI parallel) | n/a | ≤ 60s | … | … |
| 3 | Tests/sec serial | 16.9 | ≥ 26 | … | … |
| 4 | Tests/sec parallel | n/a | ≥ 35 | … | … |
| 5 | Test pass count | 2,105 | 2,105 | … | … |
| 6 | Test failures | 0 | 0 | … | … |
| 7 | Test skips | 0 | 0 | … | … |
| 8 | Coverage % | 86.0% | ≥ 86.0% | … | … |
| 9 | Mock-pattern line count | 553 | ≤ 553 | … | … |
| 10 | New `__init__.py` under `tests/` | 0 | 0 | … | … |
| 11 | `sgit_ai/` source changes | 0 | 0 | … | … |
| 12 | Determinism (run twice, identical) | yes | yes | … | … |
| 13 | Slowest single file (warm serial) | 11.70s | ≤ 5s | … | … |
| 14 | Slowest single test (warm serial) | 3.29s | ≤ 2s | … | … |
| 15 | `no_parallel`-marked tests | 0 | ≤ 5 | … | … |

**Gate decision rule:**
- ALL of #5, #6, #7, #8 (correctness + coverage) must PASS unconditionally.
- AT LEAST 80% of the runtime + structural metrics (#1–4, #9–15) must PASS.
- Any FAIL on a hard metric (#5, #6, #7, #8, #9, #10, #11) is a hard
  fail. Return work to brief 04 or 05.

---

## Deliverable

A single document at:

`team/villager/devops/v0.10.30__phase-b-acceptance.md`

Sections:
1. Acceptance matrix populated with actual numbers.
2. Gate decision (PASS / FAIL) and one-paragraph rationale.
3. If FAIL: which metric(s) failed, root cause, and the brief number
   that needs another iteration.
4. If PASS: the line "Deferred queue is now unblocked. Briefs 10–20 may
   be authored and executed."
5. Comparison narrative: where the wins came from (brief 04 vs brief 05),
   and where Phase B fell short of its targets if applicable.

Target ≤ 200 lines.

---

## Out of scope

- Fixing failures. Failures return work to brief 04 / 05; this brief
  does not patch.
- Adjusting targets. Targets are fixed by briefs 04 and 05; brief 06
  does not redefine them.
- Authoring deferred-queue briefs (10–20). The orchestrator does that
  after this brief signs off PASS.
- Touching `sgit_ai/`, `tests/`, or any config file.

---

## When you finish

Return a ≤ 250-word summary stating:
1. PASS or FAIL decision.
2. The numbers that matter (suite wall clock parallel, coverage %, test
   pass count).
3. Where the wins came from, where the gaps are.
4. If FAIL: which brief needs another pass.
5. If PASS: confirmation that the deferred queue is unblocked.
