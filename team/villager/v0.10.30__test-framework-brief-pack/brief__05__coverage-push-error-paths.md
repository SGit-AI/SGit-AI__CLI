# Brief B05 — Coverage Push: Long-Tail Error Paths

**Owner role:** **Villager Dev** + **Villager QA**
**Status:** BLOCKED until B01 lands (refactor first, then add new tests on the clean base) and B22 lands (sub-class direct tests are part of Path A; this brief picks up Path B residual).
**Prerequisites:** B01 + B22 merged.
**Estimated effort:** ~2 days
**Touches:** new tests under `tests/unit/`. **No source under `sgit_ai/`.**

---

## Why this brief exists

Per `design__05__coverage-roadmap.md` Path B: many `sgit_ai/sync/` and
`sgit_ai/api/` methods have `except Exception:` catch-alls that no test
exercises. After B22 sub-class tests close ~150–200 of the 374 missed
`Vault__Sync.py` lines (Path A), Path B picks up the remaining
long-tail error paths.

Expected delta: **+2 percentage points** (88% → ~92%).

---

## Required reading

1. This brief.
2. `design__05__coverage-roadmap.md` (paths A–D).
3. `team/villager/qa/v0.10.30__coverage-baseline.md`.
4. `team/villager/qa/qa__ROLE.md` (no mocks).
5. `team/villager/dev/dev__ROLE.md`.

---

## Scope

### Step 1 — Enumerate uncovered error paths

Run:
```
pytest tests/unit/ --cov=sgit_ai --cov-report=term-missing > /tmp/coverage-report.txt
```

Filter output to `except` blocks. Specifically look for:
- `except Exception:` catch-alls.
- `except HTTPError:` branches.
- `except (FileNotFoundError, PermissionError):` etc.
- Specific exception subclasses we raise but never catch in tests (e.g., `Vault__Read_Only_Error`, `Vault__Clone_Mode_Corrupt_Error` from B13).

Produce inventory at `team/villager/v0.10.30__test-framework-brief-pack/changes__error-paths-inventory.md`:
- File:line
- Exception type
- Triggering condition
- Proposed test approach (real failure mode, not a mock).

### Step 2 — Targeted error-path tests

For each entry, write a real-world test that triggers the exception:
- Corrupt the file on disk before reading → `JSONDecodeError`.
- Truncate a vault file → `Schema__*.from_json` failure.
- Use a non-existent path → `FileNotFoundError`.
- Use the in-memory transfer server's failure-injection hooks (if any) for HTTP error paths.
- Permission errors via `os.chmod(path, 0o000)` then read.

**No mocks. No `monkeypatch` on `requests` etc.** Real disk state, real
in-memory server.

### Step 3 — Verify coverage delta

After each batch of tests, re-run `coverage report` and verify the
target lines are covered.

---

## Hard constraints

- **No mocks. No patches. No monkeypatch.**
- **No source change to `sgit_ai/`.**
- **Each new test asserts behaviour, not just "code ran".** A test that
  triggers an `except` block and asserts nothing about the result is a
  coverage-only test — flag it for review.
- **Suite must pass under `-n auto`.**
- **Coverage delta non-negative on every commit.**

---

## Acceptance criteria

- [ ] Inventory doc at `changes__error-paths-inventory.md`.
- [ ] At least 25 new error-path tests landing.
- [ ] Overall coverage ≥ 91% (from 88%).
- [ ] No new mocks.
- [ ] Each new test has a behaviour assertion (not just an exception trigger).
- [ ] Closeout note appended to `team/villager/qa/v0.10.30__coverage-baseline.md` as §H.

---

## Out of scope

- CLI handler tests (brief B06).
- Plugin-specific coverage (v0.11.x B14).
- Coverage of code we plan to delete (per D5 §"Out-of-scope": skip
  `Vault__Sync.py` corners that don't survive v0.11.x B13).

---

## When done

Return a ≤ 250-word summary:
1. Inventory size + tests added.
2. Coverage delta (per-file + overall).
3. Anything you couldn't write a real-failure test for (escalate as a Dev source-change brief).
4. Mock-pattern line count delta (must be 0 or negative).
