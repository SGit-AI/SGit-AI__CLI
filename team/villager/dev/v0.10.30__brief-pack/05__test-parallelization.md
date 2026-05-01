# Brief 05 — Test Parallelization (v0.10.30)

**Phase:** B — Improve
**Owner role:** **Villager DevOps** (`team/villager/devops/devops__ROLE.md`)
**Status:** Can start in parallel with brief 04 OR after it. Recommended:
**after** brief 04 lands so the timing measurements include fixture
savings.
**Prerequisites:** Brief 02 baseline (done). Brief 04 strongly preferred.
**Estimated effort:** ~2–4 hours
**Touches config files:** YES — adds `pytest-xdist` to dev deps. This is
the only brief in Phase B that touches `pyproject.toml`.

---

## Why this brief exists

Brief 02 reported parallelization was skipped because `pytest-xdist` is
not in dev deps and the brief constraint disallowed temporary install.
This brief lifts that constraint: install xdist permanently, measure
actual speedup, identify and quarantine non-parallel-safe tests.

The Villager DevOps role doc target is "under 60s for unit tests". Brief
04 alone is unlikely to hit that (target there is ≤ 80s). Parallel
execution is how we close the remaining gap.

---

## Required reading

1. This brief.
2. `team/villager/devops/devops__ROLE.md` — your role.
3. `team/villager/devops/v0.10.30__runtime-baseline.md` — section C is
   "skipped because xdist not installed"; that's what you're fixing.
4. `team/villager/qa/v0.10.30__coverage-baseline.md` — coverage must not
   regress.
5. If brief 04 has merged: re-run the full-suite warm timing first so
   your "serial" baseline is post-fixture-improvements, not the original
   124s.
6. `pyproject.toml` to identify the dev-deps section.

---

## Scope

**You may modify:**
- `pyproject.toml` — add `pytest-xdist` to dev dependencies.
- `pytest.ini` (or equivalent config) — minimal xdist defaults if
  needed.
- `tests/` files — add `@pytest.mark.no_parallel` (or equivalent) to
  individual tests / classes that are not parallel-safe. Marker name is
  your choice; suggest a project-conventional name.
- `team/villager/devops/v0.10.30__parallelization-report.md` — your
  output doc.
- GitHub Actions workflow file(s) — add the xdist invocation to the
  pytest step.

**You may NOT modify:**
- Any file under `sgit_ai/`.
- Test assertions, names, parametrization, or scenario logic.

---

## Process

### Step 1 — Install and confirm

Add to `pyproject.toml` `[project.optional-dependencies].dev`:

```
"pytest-xdist>=3.5",
```

Reinstall (`pip install -e ".[dev]"`). Confirm `python -c "import xdist;
print(xdist.__version__)"` succeeds.

### Step 2 — Naive parallel run

```
pytest tests/unit/ -n auto -q
```

Record:
- Wall-clock time.
- Worker count chosen by `auto`.
- Pass / fail counts.

If failures appear, identify which tests fail under parallel that pass
serial. Those are non-parallel-safe.

### Step 3 — Identify non-parallel-safe tests

Common causes:
- Tests that share a temp directory by name.
- Tests that write to a fixed path under `~/.sg_vault` or `/tmp/...`.
- Tests that depend on global module state (LRU cache, env vars,
  monkeypatched module).
- Tests that bind to a fixed port.
- Tests that read/write a singleton resource (a global config file).

For each failing-under-parallel test:
- Reproduce: `pytest tests/path/to/test_X.py::test_y -n 4 -q`.
- Diagnose root cause from the failure message.
- Either: tag with `@pytest.mark.no_parallel` (or equivalent) AND
  document why, OR fix the underlying isolation issue.
- **Prefer fixing the isolation issue** over tagging when the fix is
  small (e.g., use `tmp_path` instead of a hard-coded `/tmp/foo`). When
  the fix is large or risky, tag and queue for follow-up.

The marker scheme (suggested):

```python
import pytest
pytestmark = pytest.mark.no_parallel  # at module level
```

```python
@pytest.mark.no_parallel
def test_x(): ...
```

Configure `pytest.ini` so `-n auto` skips marked tests, and a separate
serial pass picks them up.

### Step 4 — CI invocation

Update GitHub Actions workflow(s) to run:

```
pytest tests/unit/ -n auto -m "not no_parallel"
pytest tests/unit/ -m no_parallel
```

(Or your equivalent with the chosen marker name.) The combined wall-clock
time of these two passes is the real CI cost.

### Step 5 — Measure

Final timing matrix:

| Configuration | Workers | Wall clock | Notes |
|---|---:|---:|---|
| Serial (post-brief-04) | 1 | … | baseline |
| Parallel auto | … | … | xdist auto |
| Parallel -n 4 | 4 | … | |
| Parallel -n 8 | 8 | … | |
| Parallel + serial-marked split | auto + 1 | … | CI shape |

Pick the configuration that hits ≤ 80s combined wall clock with the
fewest non-parallel-safe markers. Push for the stretch target ≤ 60s if
it's reachable without adding markers. If you can't hit 80s, document
the gap.

---

## Numeric targets

| Target | Brief 02 baseline | Brief 04 target | Brief 05 target | Stretch |
|---|---:|---:|---:|---:|
| Suite wall clock | 124s | ≤ 80s | **≤ 80s combined CI** | ≤ 60s |
| Tests/sec (parallel) | 16.9 | ≥ 26 | **≥ 26** | ≥ 35 |
| Test pass count | 2,105 | 2,105 | **2,105** | — |
| Coverage % | 86.0% | ≥ 86.0% | **≥ 86.0%** | — |
| Non-parallel-safe markers | 0 | 0 | **≤ 5 tests / 2 modules** | 0 |

**Spirit:** the gate is ≤ 80s combined CI wall clock; faster is always
better. The team plans to add many more scenarios over time — every
second saved compounds. If you can hit ≤ 60s without adding more than 5
markers, do it; otherwise stop at ≤ 80s and document where the residual
cost lives.

If markers exceed 5 tests, that's a smell: either the tests have an
isolation problem worth fixing, or parallelization isn't a clean win.
Escalate before tagging.

---

## Acceptance criteria

- [ ] `pytest-xdist` is in dev deps and the version is pinned with `>=`.
- [ ] `pytest tests/unit/ -n auto -m "not no_parallel"` passes cleanly.
- [ ] `pytest tests/unit/ -m no_parallel` passes cleanly.
- [ ] Combined wall clock is at or below 80s (stretch: ≤ 60s).
- [ ] Coverage % unchanged or higher vs brief 01 baseline.
- [ ] No `sgit_ai/` source changes.
- [ ] CI workflow file(s) updated to run the two-pass invocation.
- [ ] Parallelization report doc exists at
      `team/villager/devops/v0.10.30__parallelization-report.md`.
- [ ] All `@pytest.mark.no_parallel` (or equivalent) tags have a
      documented reason in the report.

---

## Deliverables

1. `pyproject.toml` change adding xdist.
2. Marker tags in `tests/` files for non-parallel-safe tests, each with a
   short comment explaining why.
3. CI workflow update.
4. `team/villager/devops/v0.10.30__parallelization-report.md` with the
   timing matrix, marker list with rationales, and any escalations.

---

## Out of scope

- Fixing every isolation issue. Tag and queue is acceptable for
  non-trivial fixes.
- Adding tests. Brief 04's "no new tests" rule still applies.
- Touching `sgit_ai/` source. If a source change would unblock parallel
  safety, escalate to Dev — don't edit yourself.
- Cross-Python-version testing. The matrix run (3.11 / 3.12) is a
  separate DevOps concern handled at the CI level, not this brief.

---

## When you finish

Return a ≤ 300-word summary stating:
1. Wall-clock time at each configuration tested.
2. Configuration recommended for CI.
3. List of `no_parallel`-marked tests with one-line reason each.
4. Any isolation issue you fixed (and how) vs queued (and why).
5. Coverage delta after parallelization.
