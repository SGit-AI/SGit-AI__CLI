# Brief B02 — New Fixtures Implementation

**Owner role:** **Villager Dev**
**Status:** Ready (independent of B22).
**Prerequisites:** None hard. Best **after B03** so the new fixtures can land in `tests/conftest.py` (root) directly. If B03 hasn't shipped, land them in `tests/unit/sync/conftest.py` and B03 relocates.
**Estimated effort:** ~1.5 days
**Touches:** new fixtures + their tests. **No source under `sgit_ai/`.**

---

## Why this brief exists

Per `design__02__new-fixtures-catalog.md`: five new fixtures fill the
gaps F1–F6 + `Vault__Test_Env` don't cover. Combined with B01's
adoption pass, expected suite-wide savings ~50–70 seconds.

---

## Required reading

1. This brief.
2. `design__02__new-fixtures-catalog.md` (the five fixtures).
3. `design__04__pre-derived-keys-and-helpers.md` (where they live post-D4).
4. `tests/unit/sync/conftest.py` + `tests/unit/sync/vault_test_env.py` (the existing fixture pattern to follow).

---

## Scope — five new fixtures

Implement each per design D2:

| # | Fixture | Scope | Pre-builds |
|---|---|---|---|
| NF1 | `two_clones_pushed` (snapshot) + `two_clones_workspace` (factory) | module + function | Alice init+commit+push, Bob clone |
| NF2 | `vault_with_N_commits_snapshots` + `vault_with_N_commits` (factory) | module + function | Linear history of N=1, 5, 20 commits with deterministic content |
| NF3 | `vault_with_pending_changes_snapshot` + `vault_with_pending_changes` (factory) | module + function | Vault with working-copy modifications (added/modified/deleted) |
| NF4 | `vault_with_branches_snapshot` + `vault_with_branches` (factory) | module + function | Vault with two branches diverged from common base |
| NF5 | `read_only_clone_snapshot` + `read_only_clone` (factory) | module + function | Read-only clone (clone_mode.json with read_key only) |

For each fixture:
1. Build the snapshot once at module/session scope.
2. Per-test factory uses `shutil.copytree` for working directory + `copy.deepcopy` for in-memory API store.
3. Mutation contract: snapshot is read-only; every mutation lands in the per-test workspace.

---

## Tests for each fixture

Each new fixture ships with at least 3 tests under `tests/unit/_fixtures/`:

| Test | Asserts |
|---|---|
| `test_<fixture>_builds_correctly` | The pre-built state is what we claim (commit count, branch count, etc.) |
| `test_<fixture>_per_test_isolation` | Two consumer tests don't see each other's mutations |
| `test_<fixture>_factory_returns_fresh_workspace` | Each factory call produces a distinct workspace |

---

## Hard constraints

- **Type_Safe** for any new helper class. No raw dict/str/int fields if it's a class.
- **No mocks.** Snapshot + copytree only.
- **No `__init__.py` under `tests/`** (except the one in `tests/_helpers/` if D4's exception was approved by Dinis — check `design__04` §"_helpers/__init__.py" for status).
- **Snapshot is read-only.** A regression test (per-fixture isolation) catches accidental shared-state mutations.
- **Suite must pass under `-n auto`.**
- **Coverage must not regress.**

---

## Acceptance criteria

- [ ] All five fixtures implemented per D2 signatures.
- [ ] Each fixture has ≥ 3 tests (build + isolation + factory).
- [ ] Suite ≥ existing test count + ~15 (the new fixture tests) passing.
- [ ] Coverage delta non-negative.
- [ ] Closeout note appended to `team/villager/dev/v0.10.30__shared-fixtures-design.md` as §10 listing the five new fixtures + their consumer tests added in B04.

---

## Out of scope

- Adopting the new fixtures into existing tests (brief B04).
- The pre-derived key cache (brief B03).
- The relocation to `tests/_helpers/` (brief B03).

---

## When done

Return a ≤ 250-word summary:
1. Fixtures shipped + their location.
2. Test count + isolation-test outcomes.
3. Coverage delta.
4. Anything in D2's signatures that needed adjustment during implementation (escalate).
