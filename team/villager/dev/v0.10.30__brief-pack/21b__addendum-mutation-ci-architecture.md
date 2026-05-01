# Addendum — Mutation Tests, AppSec Tests, and CI Architecture

**Date:** May 1, 2026
**Applies to:** Brief 21 (`21__mutation-matrix-execution.md`) and any future
AppSec / adversarial test work.
**Status:** Architectural decision — supersedes the manual `git stash` approach
described in brief 21's hard rules.

---

## Decision: Mutation tests run in CI as a separate parallel job

Mutation tests must be a first-class CI job, running **in parallel** with the
existing integration and QA jobs — not as a manual one-off exercise.

Updated CI pipeline shape:

```
run-tests (unit)
    │
    ├── run-integration-tests
    ├── run-qa-tests
    ├── run-appsec-tests        ← new parallel job
    └── run-mutation-tests      ← new parallel job
            │
    increment-tag → publish
```

---

## Why isolation is not optional

Brief 21 says "use `git stash` / `git checkout --` to revert mutations".
That is safe for a human agent running one mutation at a time. It is **not
safe in CI** for two reasons:

1. **Python import cache (`sys.modules`):** If a source file is mutated and
   then imported by any test in the same process tree, that mutated module
   is cached. Other tests in the same run see the mutation even after the
   file is reverted on disk.

2. **Signal interrupts leave mutations live:** If the CI runner is killed
   mid-run (timeout, OOM, spot termination), the mutation remains committed
   to the working tree. The next job picks up mutated source and produces
   false results.

The correct isolation primitive is **`git worktree`** — one per mutation,
created from HEAD, discarded immediately after the mutation run.

---

## Isolation model: git worktree per mutation

```
for each mutation M1..M10 + B1..B5:
    git worktree add /tmp/mut-MN --detach HEAD
    apply_patch(mutation_spec, root=/tmp/mut-MN)
    result = pytest /tmp/mut-MN/tests/unit/ -x --tb=no -q
    record(mutation=MN, detected=(result.returncode != 0))
    git worktree remove --force /tmp/mut-MN
```

`git worktree` shares the object store with the main repo so creation is
fast (no re-clone). The main checkout is never touched. Mutations never
appear in `git log`.

---

## Test folder structure

```
tests/
├── unit/          # existing — parallel, fast
├── integration/   # existing — Python 3.12 venv, real server
├── qa/            # existing — end-to-end scenarios
├── appsec/        # NEW — adversarial tests (normal pytest, no mutation)
│   ├── test_AppSec__Crypto.py
│   ├── test_AppSec__Clone_Mode.py
│   └── test_AppSec__Token_Handling.py
└── mutation/      # NEW — mutation orchestrator (NOT a pytest folder)
    ├── run_mutations.py    # CI entrypoint: worktree → patch → run → report
    └── mutations.py        # M1..M10 + B1..B5 as structured patch specs
```

**`tests/appsec/`** is standard pytest — adversarial inputs, boundary attacks,
auth bypass attempts, read-only clone escape attempts. Run with
`pytest tests/appsec/` exactly like unit tests. No mutation, no worktrees.

**`tests/mutation/`** is **not** a pytest folder. `run_mutations.py` is a
plain Python script that orchestrates worktrees, applies mutations,
invokes pytest as a subprocess, and produces a structured report. The CI job
calls this script directly.

---

## CI job definitions (to add to `ci-pipeline.yml`)

### `run-appsec-tests`

```yaml
run-appsec-tests:
  name: "Run AppSec / Adversarial Tests"
  runs-on: ubuntu-latest
  needs: [run-tests]
  steps:
    - uses: actions/checkout@v4
    - name: run-appsec-tests
      uses: ./.github/actions/pytest__run-tests
      with:
        test_target: "tests/appsec"
        python_version: "3.11"
        parallel: "false"
```

### `run-mutation-tests`

```yaml
run-mutation-tests:
  name: "Run Mutation Tests"
  runs-on: ubuntu-latest
  needs: [run-tests]
  steps:
    - uses: actions/checkout@v4
      with:
        fetch-depth: 0        # worktree needs full history

    - name: Set up Python
      uses: actions/setup-python@v5
      with:
        python-version: "3.11"

    - name: Install dependencies
      run: pip install -e ".[dev]"

    - name: Run mutation suite
      run: python tests/mutation/run_mutations.py --report mutation-report.json

    - name: Upload mutation report
      uses: actions/upload-artifact@v4
      with:
        name: mutation-report
        path: mutation-report.json
```

**Gate:** `increment-tag` adds `run-appsec-tests` and `run-mutation-tests`
to its `needs` list so a mutation regression blocks the release.

---

## What brief 21 should produce (updated scope)

Brief 21's original scope (execute each row, verify detected/undetected,
write missing tests, update M00) is unchanged. What changes is **how** the
mutations are applied and where the results live:

1. **Implement `tests/mutation/mutations.py`** — catalogue of M1..M10 + B1..B5
   as structured specs (file path, line number or regex, old text, new text).

2. **Implement `tests/mutation/run_mutations.py`** — the worktree orchestrator.
   Each mutation: create worktree → apply spec → run `pytest tests/unit/ -x`
   → record → destroy worktree. Emit a JSON report and a human-readable
   summary to stdout.

3. **Add any missing closer tests** to `tests/unit/` as before — these are
   the tests that catch the mutation and make `run_mutations.py` report D.

4. **Update M00** with live-observed statuses as before.

The manual `git stash` / `git checkout --` steps in brief 21 are
**replaced** by the worktree orchestrator. The hard rule "never commit a
mutation" is enforced structurally: mutations are only ever applied inside
a worktree that is discarded, so they cannot reach the main working tree.

---

## What to build in brief 21 vs later

| Work item | Where |
|---|---|
| `mutations.py` catalogue (M1–M10, B1–B5) | Brief 21 |
| `run_mutations.py` orchestrator | Brief 21 |
| Missing closer tests for U-rows | Brief 21 |
| M00 update with live results | Brief 21 |
| `tests/appsec/` folder + initial adversarial tests | Follow-on (brief 22 or separate) |
| CI job additions in `ci-pipeline.yml` | Brief 21 (add `run-mutation-tests`) |
| `run-appsec-tests` CI job | When `tests/appsec/` has content |
| `increment-tag` needs updated to gate on both new jobs | Brief 21 |
