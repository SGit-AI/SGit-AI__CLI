# Brief 02 — Test Runtime Baseline (v0.10.30)

**Phase:** A — Measure
**Owner role:** **Villager DevOps** (`team/villager/devops/devops__ROLE.md`)
**Status:** Ready to execute
**Prerequisites:** None (runs in parallel with brief 01)
**Estimated effort:** ~45–60 min
**Read-only:** YES — this brief MUST NOT modify source or tests.

---

## Why this brief exists

Per the v0.10.30 next-phase plan §2, test infrastructure is the priority,
and the central concern is **speed**: agents need fast feedback loops, CI
scales linearly with suite cost, and the team plans to add many more
scenarios (mutation matrix, crypto-determinism tests, push-checkpoint
tests, sparse-clone tests, future ones).

The Villager DevOps role doc (§Measuring Effectiveness) sets a target of
"under 60s for unit tests". We need to know where we are today and where
the time is going.

This brief captures the runtime baseline. Brief 05 (parallelization) and
brief 04 (shared fixtures) will use this baseline as input. Brief 06
(acceptance) will compare against it.

---

## Scope

You will produce a single small markdown document:

`team/villager/devops/v0.10.30__runtime-baseline.md`

**You may run pytest with timing flags. Running tests is allowed and
expected.** What you may NOT do:

- Modify any source file under `sgit_ai/`.
- Modify any test file under `tests/`.
- Modify any test config (`pytest.ini`, `pyproject.toml`, etc.).
- Install new packages permanently — see "tooling" below for what's allowed.
- Commit anything other than the new baseline doc.

---

## Tooling

You should produce:

1. **A pytest `--durations` snapshot** (no plugin install needed; built-in).
2. **Per-test-file aggregated timing** (you'll process the durations output
   yourself; do not install pytest-split or similar).
3. **Cold-vs-warm runtime samples** (kernel disk cache effects).

If `pytest-xdist` is already a dev dependency (check `pyproject.toml`
`[project.optional-dependencies].dev`), you may use it for the
parallelization sample in §C below. If not present, skip §C and note
"pytest-xdist not in dev deps; parallelization measurement deferred to
brief 05".

You may invoke `time` (the shell builtin) for wall-clock measurements.

---

## Required reading

1. This brief (in full).
2. `team/villager/devops/devops__ROLE.md` — your role.
3. `CLAUDE.md` at repo root — pytest invocation conventions.
4. `team/villager/v0.10.30__next-phase-plan.md` §2(b) — context.

Do not read the cross-team-summary or the deep-analysis findings.

---

## What to measure

### A. Cold + warm full-suite runtime

Run the full unit suite three times. The first run is "cold". Then
**without any cache-clearing**, run twice more for warm samples. Record
each time.

```bash
pytest tests/unit/ -q              # capture wall clock for each
pytest tests/unit/ -q
pytest tests/unit/ -q
```

Use `time` (or pytest's own end-of-run timing — both is fine).

Report:
- Cold run wall-clock time.
- Warm run wall-clock times (median of two).
- Number of tests run.
- Tests-per-second (warm).

### B. Top-N slowest files and tests

```bash
pytest tests/unit/ --durations=0 -q > /tmp/durations.txt
```

`--durations=0` lists every test's setup/call/teardown durations.

From that output produce two tables in your doc:

**Top-25 slowest individual tests:**

| Rank | Test | File | Phase (setup/call/teardown) | Duration |
|---:|---|---|---|---:|

**Top-15 slowest test files (sum of all tests in the file):**

| Rank | File | Test count | Total duration | Avg per test |
|---:|---|---:|---:|---:|

You will need to aggregate the per-test data into per-file data yourself.
Awk or python is fine.

### C. Parallelization sample (only if pytest-xdist is already installed)

```bash
pytest tests/unit/ -n auto -q     # let xdist pick worker count
pytest tests/unit/ -n 4 -q
pytest tests/unit/ -n 8 -q
```

Report:
- Wall-clock time at each worker count.
- Speedup factor vs warm serial baseline.
- Any tests that fail under parallel execution but pass serial — these
  are non-parallel-safe and need to be flagged for brief 05. List them
  exactly.

If pytest-xdist is not in dev deps: skip this section, note the absence,
move on. Do NOT add it to dev deps in this brief.

### D. Setup-cost concentration

For the top-15 slowest files identified in §B, look at where the time
goes. Use `--durations=0` output to break down per file:

- Total time spent in `setup` phase.
- Total time spent in `call` phase.
- Total time spent in `teardown` phase.

If `setup` dominates `call` for a file, that file is a candidate for
shared fixtures (input to brief 03).

### E. Suspected duplicate-setup hotspots

Without reading test code in detail, look at the slow files and answer:

- Which files repeatedly create a fresh vault from scratch?
- Which files repeatedly derive keys from passphrases (PBKDF2 is
  intentionally slow)?
- Which files spin up the in-memory transfer server?
- Which files use real temp directories (and how many per file)?

You can sample a few of the slowest test files (read-only) to confirm
hypotheses. For each hotspot, name the file and the suspected expensive
operation. Brief 03 will design the shared-fixture replacement.

### F. Comparison vs v0.5.11

If `team/villager/qa/v0.5.11__coverage-baseline.md` records a runtime
(it shows "~53s"), include a single-line comparison: what was the suite
runtime then, what is it now, what's the delta.

---

## Acceptance criteria

- [ ] Baseline doc exists at `team/villager/devops/v0.10.30__runtime-baseline.md`
      and is ≤ 250 lines.
- [ ] Sections A, B, D, E, F are populated with real numbers from fresh
      pytest runs.
- [ ] Section C is either populated (if xdist available) or explicitly
      skipped with a one-line reason.
- [ ] The pytest command(s), Python version, machine class (just "the
      sandbox container" is fine), and any environment notes are recorded
      at the top of the doc.
- [ ] Working tree is clean except for the new baseline doc.
- [ ] No source / test / config file was modified (verify `git diff` is
      empty against `sgit_ai/`, `tests/`, `pyproject.toml`, `pytest.ini`,
      `.coveragerc`).
- [ ] Doc is committed and pushed.

---

## Deliverable

One file: `team/villager/devops/v0.10.30__runtime-baseline.md`.

Commit message:
```
docs(villager-devops): capture v0.10.30 test runtime baseline

Headline: NN tests, cold NN.Ns / warm NN.Ns wall clock, NN tests/sec.
Top-1 slowest file: <name> at NN.Ns (NN tests).

Parallelization: <NN.Ns at -n auto> OR <skipped, xdist not in dev deps>.
Setup-dominated files: NN of top-15.
Suspected shared-fixture candidates surfaced for brief 03.

Read-only — no source / test / config changes.

https://claude.ai/code/session_<id>
```

Then `git push origin claude/villager-multi-agent-setup-sUBO6`.

---

## Out of scope

- Writing any new test or fixture (brief 04 territory).
- Adding pytest-xdist to dev deps (DevOps decision in a later brief).
- Touching `pyproject.toml`, `pytest.ini`, `.coveragerc`, GitHub Actions
  workflows.
- CI integration (separate DevOps brief, not this one).
- Coverage measurement (brief 01, run by QA in parallel).
- Integration tests (Python 3.12 venv) — note their existence at the top
  of the doc; do not run them in this brief.

---

## When you finish

Return a summary stating:
1. Cold and warm full-suite wall-clock time + tests/second.
2. Top-3 slowest individual tests + top-3 slowest files.
3. Parallelization speedup if measured, or note that it was skipped.
4. Top 3 suspected shared-fixture candidates (name + reason).
5. Anything you couldn't measure within the time budget.
