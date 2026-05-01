# Brief 18 — Coverage push: API layer

**Owner role:** **Villager QA** (primary; uses brief 19 to add tests
without mocks) + **Villager Dev** (technical review)
**Status:** Ready to execute.
**Prerequisites:** None within deferred queue. Phase B test infra in
place (it is).
**Estimated effort:** ~4–6 hours
**Touches:** new tests under `tests/unit/api/` and `tests/unit/sync/`;
no source under `sgit_ai/`.

---

## Why this brief exists

Brief 01 (coverage baseline) flagged the API layer as the single largest
coverage hole that's NOT just the new sync surface:

| File | Coverage | Lines | Note |
|---|---:|---:|---|
| `sgit_ai/api/Vault__Backend__API.py` | **0%** | 21 | new file, never tested |
| `sgit_ai/api/Vault__API.py` | 33.9% | 186 | core HTTP-bridge class |
| `sgit_ai/api/API__Transfer.py` | 46.5% | 198 | transfer endpoints |
| `sgit_ai/sync/Vault__Diff.py` | 61.4% | 285 | local diff machinery |
| `sgit_ai/cli/CLI__Diff.py` | 62.0% | 142 | diff CLI handler |

The crypto / sync paths get good coverage from indirect testing. The API
layer doesn't, because most CLI tests use the **in-memory transfer
server** as a stand-in for the real server, which means many API code
paths (auth headers, error mapping, retry, timeout) are never executed.

This brief targets a meaningful coverage push specifically on the API
layer, with no-mocks testing against the in-memory server PLUS at least
one real-server integration test path (Python 3.12 venv).

---

## Required reading

1. This brief.
2. `team/villager/qa/qa__ROLE.md`.
3. `team/villager/qa/v0.10.30__coverage-baseline.md` — for the gap data.
4. `team/villager/appsec/v0.10.30/F05__delete-on-remote.md` and `F12__dependency-audit.md`
   — flagged a real-server integration gap (M10 in the mutation matrix).
5. `CLAUDE.md` — Type_Safe rules, **no mocks**.
6. `sgit_ai/api/Vault__API.py`, `API__Transfer.py`, `Vault__Backend__API.py`
   — read structure, identify untested branches.

---

## Scope

**In scope:**
- Add tests for `Vault__Backend__API.py` (currently 0%) — even small
  smoke tests get this to a baseline.
- Push `Vault__API.py` to ≥ 70%, focusing on:
  - Auth-header construction (especially `x-sgraph-vault-write-key`
    header which mutation M10 targets).
  - Error mapping (HTTP 4xx/5xx → typed exceptions).
  - Timeout / retry behaviour if any.
- Push `API__Transfer.py` to ≥ 70%.
- Push `Vault__Diff.py` to ≥ 75% — sample uncovered methods, not
  exhaustive.
- One **real-server integration test** for `delete_vault` write-key
  enforcement (closes mutation M10). Use the Python 3.12 venv per
  `CLAUDE.md` integration testing section.

**Out of scope:**
- Refactoring source. If you find a code smell that prevents testing,
  document it as a Dev follow-up.
- The remaining sync-layer gaps (those are covered by briefs 14, 20,
  21, and the `Vault__Sync.py` split in brief 22).
- Hitting 95% (the role-doc target) — that's a v0.11.x ambition.
  Realistic target for this brief: **overall coverage 86% → 89% (+3pp)**.

**Hard rules:**
- **No mocks. No patches. No monkeypatch.** Existing rule; non-negotiable.
- Use the in-memory server for unit tests; use the real `sgraph-ai-app-send`
  server (Python 3.12 venv) for integration tests.
- Tests must run cleanly under Phase B parallel CI shape. The
  integration tests live under `tests/integration/` and run separately
  per `CLAUDE.md`.

---

## Acceptance criteria

- [ ] `Vault__Backend__API.py` ≥ 50% (from 0%).
- [ ] `Vault__API.py` ≥ 70% (from 33.9%).
- [ ] `API__Transfer.py` ≥ 70% (from 46.5%).
- [ ] `Vault__Diff.py` ≥ 75% (from 61.4%).
- [ ] Overall coverage ≥ 89% (from 86%).
- [ ] At least 1 real-server integration test for `delete_vault`
      write-key enforcement, exercised in the Python 3.12 venv.
- [ ] Mutation matrix M10 row updates from "U" to "D".
- [ ] No new mocks.
- [ ] No source changes.
- [ ] Suite ≥ 2,105 passing (will be more — note new count).
- [ ] Closeout note appended to QA coverage baseline doc as §G.

---

## Deliverables

1. Test files under `tests/unit/api/` (and `tests/unit/sync/` for
   `Vault__Diff.py`).
2. Integration test file under `tests/integration/` for the
   delete_vault auth path.
3. Mutation matrix M10 update.
4. §G note in QA coverage baseline doc.

Commit message:
```
test(qa): cover API layer to ≥ 70% (was 0–47%)

Closes major Phase-1-deep-analysis coverage gap. New tests cover
Vault__Backend__API (0% → ≥ 50%), Vault__API (34% → ≥ 70%),
API__Transfer (47% → ≥ 70%), and Vault__Diff (61% → ≥ 75%). Plus
one real-server integration test for delete_vault write-key
enforcement, closing AppSec mutation M10.

Overall coverage 86% → 89%.

https://claude.ai/code/session_<id>
```

---

## When done

Return a ≤ 250-word summary:
1. Per-file coverage delta vs targets (table).
2. Overall coverage delta.
3. Mutation matrix M10 closure status.
4. Number of tests added.
5. Anything you couldn't push to target without source changes
   (escalate as Dev follow-up).
