# Brief 19 — Mock cleanup

**Owner role:** **Villager Dev** + **Villager QA**
**Status:** Ready to execute. Recommended after brief 18 lands so the
mock-removed test set is final before scrubbing.
**Prerequisites:** None hard.
**Estimated effort:** ~6–10 hours (the 553 mock-pattern lines are spread
across many files; this is a sustained effort, not a single PR)
**Touches:** tests under `tests/unit/`; no source under `sgit_ai/`.

---

## Why this brief exists

The "no mocks, no patches" rule is core to both Villager Dev and Villager
QA roles. Brief 01's count revealed the spirit of the rule is being
widely violated:

- 553 mock-pattern lines total across `tests/`.
- 34 lines of `unittest.mock` / `MagicMock` / `@patch` across 9 files.
- 519 lines of `monkeypatch` across 19 files.
- The v0.10.30 sprint introduced **0** new `unittest.mock` imports + 4
  homemade `FakeArgs` stubs — not the new code's fault.
- The 553 is **all carryover** from before the sprint.

This brief is a sustained chip-away at the carryover. It will not
finish in one pass; the goal is meaningful reduction with zero coverage
regression.

---

## Required reading

1. This brief.
2. `team/villager/dev/v0.10.30/02__mocks-and-patches.md` — Dev's
   inventory of carryover mocks.
3. `team/villager/qa/qa__ROLE.md` — "no mocks" rule.
4. `team/villager/dev/dev__ROLE.md` — same.
5. `CLAUDE.md` — same.

---

## Scope

**In scope:**
- Audit the 553 lines into categories:
  - **Replaceable** (mock can become a real object trivially — e.g.,
    real temp dir, real Type_Safe instance, real in-memory server).
  - **Replaceable with effort** (needs a real fixture; estimate effort).
  - **Hard to replace** (e.g., environment-variable monkeypatch, system-
    clock monkeypatch — document these and propose a real-object
    pattern; defer the actual replacement if non-trivial).
- Replace the **Replaceable** category in this brief — target ≥ 60% of
  carryover lines removed (~330 lines).
- Replace at least 5 instances from the **Replaceable with effort**
  category as proof-of-concept patterns.
- Document the **Hard to replace** category as a follow-up brief
  (probably v0.11.x).
- Replace the 4 `FakeArgs` homemade stubs in `test_CLI__Vault__Write.py`
  with a real `argparse.Namespace` factory or a Type_Safe `Schema__CLI__Args`
  class.

**Out of scope:**
- Source changes to `sgit_ai/`. If a test cannot be de-mocked without a
  source change, escalate as a Dev follow-up — do not modify source in
  this brief.
- Removing tests. If a test is only meaningful with a mock, that's a
  smell to flag, not a test to delete.
- Adding `pytest-randomly` or anything similar.

**Hard rules:**
- Coverage must not regress (Phase B gate is permanent: ≥ 86%).
- All 2,105 tests must continue to pass throughout. Test suite
  must remain deterministic.
- No new mocks introduced as a side effect.

---

## Acceptance criteria

- [ ] Audit document at `team/villager/dev/v0.10.30__mock-cleanup-audit.md`
      categorising the 553 lines (≤ 200 lines audit doc).
- [ ] At least 60% of the 553 lines removed (~330 lines) in this brief.
- [ ] All 4 `FakeArgs` homemade stubs replaced.
- [ ] Suite ≥ 2,105 passing (more is fine), coverage ≥ 86%.
- [ ] Phase B parallel CI shape still passes.
- [ ] Final mock-pattern line count documented and ≤ 220 lines.
- [ ] Closeout note appended to Dev finding 02.

---

## Deliverables

1. Audit doc (`team/villager/dev/v0.10.30__mock-cleanup-audit.md`).
2. Modified test files (only `tests/`).
3. Possibly new helper/fixture files for replacement patterns
   (under `tests/`).
4. Closeout note on Dev finding 02.

Commit cadence: one commit per category or per-file group, pushed
periodically. Avoid one giant commit.

Commit message template:
```
test(no-mocks): remove monkeypatch from <file>

Replaces N monkeypatch uses in <file> with <real-object pattern>.
Coverage unchanged. Part of brief 19 mock-cleanup against the 553-line
v0.10.30 carryover.

https://claude.ai/code/session_<id>
```

---

## When done

Return a ≤ 250-word summary:
1. Final mock-pattern line count.
2. Per-category counts (replaceable / with-effort / hard).
3. Coverage delta.
4. Test count delta.
5. The top 3 patterns you used as replacements (real object / fixture /
   factory).
6. The follow-up brief proposal for the "hard to replace" category.
