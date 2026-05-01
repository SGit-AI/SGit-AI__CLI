# Brief 04 — Shared Fixtures Implementation (v0.10.30)

**Phase:** B — Improve
**Owner role:** **Villager Dev** (`team/villager/dev/dev__ROLE.md`)
**Status:** BLOCKED until brief 03 is merged.
**Prerequisites:** Brief 03's design doc must exist at
`team/villager/dev/v0.10.30__shared-fixtures-design.md` and be merged.
**Estimated effort:** ~4–6 hours (depends on size of brief 03's checklist)
**Read-only on source.** This brief touches `tests/` only — never `sgit_ai/`.

---

## Why this brief exists

Brief 03 produces the design and a hand-off checklist. Brief 04 is the
mechanical execution of that checklist: add the conftest fixtures,
refactor the named tests to consume them, prove behaviour is preserved
and runtime is reduced.

**Behaviour preservation is non-negotiable.** Per Villager Dev role
(§"Preserve behaviour exactly"): every change must produce identical
outputs for identical inputs. If you discover that a fixture causes a
test to behave differently, escalate — do not paper over it.

---

## Required reading

1. This brief.
2. `team/villager/dev/dev__ROLE.md` — your role, especially "Preserve
   behaviour exactly" and "no mocks, no patches".
3. `team/villager/dev/v0.10.30__shared-fixtures-design.md` — your spec.
   The §7 hand-off checklist drives the work.
4. `team/villager/devops/v0.10.30__runtime-baseline.md` — the numbers you
   are improving against.
5. `team/villager/qa/v0.10.30__coverage-baseline.md` — the numbers you
   must not regress.
6. `CLAUDE.md` — Type_Safe rules, no-mocks rule.

---

## Scope

**You may modify:** files under `tests/` only (new `conftest.py` files,
existing test files only to refactor setup into shared fixtures, never
to change assertions).

**You may NOT modify:**
- Any file under `sgit_ai/`.
- `pyproject.toml`, `pytest.ini`, `.coveragerc`, GitHub Actions workflows.
- Add new packages to dev deps.
- Change test names, assertions, parametrization, or skip markers.
- Remove tests, even if they look redundant — that's a separate decision.
- Add `__init__.py` anywhere in `tests/` (project rule, see `CLAUDE.md`).
- Introduce mocks, patches, monkeypatch — even temporarily. The "no mocks"
  rule applies to fixtures too.

---

## Process

For each item in brief 03's §7 checklist:

1. **Add the fixture** in the conftest location specified by the design.
   Use real objects, real temp dirs, real crypto — no mocks.
2. **Refactor consumer tests** to call the fixture instead of doing the
   expensive setup themselves.
3. **Run the affected files** to confirm no regression:
   ```
   pytest tests/unit/<path>/test_<X>.py -q
   ```
4. **Run the full suite** at least once mid-way and once at the end:
   ```
   pytest tests/unit/ -q
   ```
   All 2,105 tests must continue to pass. **No new failures, no new
   skips.**
5. **Verify behaviour preservation** by running the suite with random
   ordering once:
   ```
   pytest tests/unit/ -p no:cacheprovider -q --tb=short
   pytest tests/unit/ -q  # repeat, results should match
   ```
   If pytest-randomly is installed, also try a random seed run. If
   results differ between runs, you have introduced shared-state
   pollution — revert that fixture and escalate.

Commit and push every 2–3 fixtures so partial progress is safe.

---

## Numeric targets

These targets are calibrated against brief 03's design projection
(~111s warm serial, a 10% reduction). The headline gate (≤ 80s combined
CI parallel) is brief 05's responsibility, not brief 04's. Brief 04's
job is to remove redundant work; brief 05's job is to do remaining work
in parallel.

| Target | Current (brief 02) | Target | Stretch |
|---|---:|---:|---:|
| Suite warm runtime (serial) | 124s | **≤ 115s** | ≤ 105s |
| Tests/sec (serial) | 16.9 | **≥ 18** | ≥ 20 |
| Slowest single file (serial) | 11.70s (`test_Vault__Sync__Simple_Token.py`) | **≤ 9s** | ≤ 7s |
| Slowest single test (serial) | 3.29s | **≤ 2.5s** | ≤ 2s |
| Test pass count | 2,105 | **2,105** (no regressions) | — |
| Coverage % | 86.0% | **≥ 86.0%** (no regression) | — |

Spirit: faster is always better. If the design's full checklist lands
under 115s, that's the pass; if you can push further without expanding
scope, push. Do not invent additional fixture changes the design didn't
specify — escalate to brief 03 owners if you discover new hotspots.

---

## Acceptance criteria

- [ ] Every item in brief 03 §7 checklist is either DONE or explicitly
      NOT-DONE-with-reason.
- [ ] Full suite runs cleanly: `pytest tests/unit/ -q` passes 2,105.
- [ ] Suite passes a second time without flakiness.
- [ ] Coverage ≥ 86.0% (re-run the brief 01 command and compare).
- [ ] No new mock / patch / MagicMock / monkeypatch import introduced
      (`grep -rn 'unittest.mock\|MagicMock\|@patch\|monkeypatch' tests/`
      count must not increase vs brief 01 baseline of 553).
- [ ] No `__init__.py` files added under `tests/`.
- [ ] No source file under `sgit_ai/` modified (`git diff -- sgit_ai/`
      empty).
- [ ] No config file modified (`git diff -- pyproject.toml pytest.ini
      .coveragerc` empty).
- [ ] Commit history is clean: one logical change per commit, each
      pushable as a discrete unit.

---

## Deliverables

1. New / modified files under `tests/` only.
2. A short closeout note appended to brief 03's design doc:
   `team/villager/dev/v0.10.30__shared-fixtures-design.md`, with a §8
   "implementation log" listing what was done and what was deferred.
   (Append-only; do not rewrite the design.)
3. A measurement snippet inside the closeout note showing before/after
   runtime for each affected file.

---

## Out of scope

- Adding pytest-xdist or any dependency.
- Parallelization. That's brief 05.
- Touching `sgit_ai/` source for any reason.
- Adding new tests / scenarios — even ones that the design suggests would
  be good. Those go in briefs 18 / 19 etc.
- Removing tests.

---

## When you finish

Return a ≤ 300-word summary stating:
1. Number of fixtures added.
2. Number of test files refactored.
3. Suite runtime: before / after, per-file and aggregate.
4. Coverage: before / after.
5. Any test that became flaky or revealed pollution after refactoring
   (and how it was resolved).
6. Any item from brief 03 §7 that you skipped, with reason.
