# Brief B01 — Adoption Refactor

**Owner role:** **Villager Dev** (`team/villager/dev/dev__ROLE.md`)
**Status:** BLOCKED until B22 (Vault__Sync split) lands.
**Prerequisites:** B22 merged (so the new sub-class tests are part of the refactor).
**Estimated effort:** ~2–3 days
**Touches:** ~18 test files under `tests/unit/sync/` and `tests/unit/cli/`. **No source under `sgit_ai/`.**

---

## Why this brief exists

Per `design__01__current-fixtures-and-adoption.md`: ~110 raw
`Vault__Sync` setups across 18 test files that already have a fixture
(F3–F6 / `Vault__Test_Env`) they could be using. At ~400 ms per
init+commit+push cycle, that's **~30–40 seconds of redundant per-test
work** suite-wide.

This brief refactors those files to consume existing fixtures.

---

## Required reading

1. This brief.
2. `design__01__current-fixtures-and-adoption.md` (the inventory).
3. `team/villager/dev/v0.10.30__shared-fixtures-design.md` (the original F3–F6 design).
4. `tests/unit/sync/conftest.py` + `tests/unit/sync/vault_test_env.py`.
5. `tests/unit/cli/conftest.py`.
6. `team/villager/dev/dev__ROLE.md` (preserve behaviour exactly).

---

## Scope

For each file in design D1's adoption-gap inventory, refactor the raw
`Vault__Crypto()` + `Vault__Sync()` setups to consume the matching
fixture:

| Test file | Replace raw setup with |
|---|---|
| `test_Vault__Sync__Multi_Clone.py` | `Vault__Test_Env.setup_two_clones` |
| `test_Vault__Diff__Coverage.py` | `bare_vault_workspace` or `Vault__Test_Env.setup_single_vault` |
| `test_Vault__Diff.py` | `Vault__Test_Env.setup_single_vault` |
| `test_Vault__Branch_Switch.py` | `Vault__Test_Env.setup_two_clones` |
| `test_Vault__Sync__Uninit.py` | `Vault__Test_Env.setup_single_vault` |
| `test_Vault__Sync__Remote_Failure.py` | `Vault__Test_Env.setup_two_clones` |
| `test_Vault__Sync__Helpers.py` | `bare_vault_workspace` |
| `test_Vault__Sync__Probe_Artefacts.py` | `probe_vault_env` (F5) — already exists, just adopt |
| `test_Vault__Stash.py` | `Vault__Test_Env.setup_single_vault` |
| `test_Vault__Ignore.py` | `bare_vault_workspace` |
| 7+ more sync files (2 setups each) | choose per-file |
| `test_CLI__Commands.py` | `Vault__Test_Env.setup_single_vault` (post-D4 relocation) |
| `test_Vault__Inspector__Coverage.py` | `bare_vault_workspace` or NF2 once B02 lands |

**Important:** if `test_CLI__Commands.py` uses `Vault__Test_Env`, this
brief must run **after** brief B03 (which relocates `Vault__Test_Env`
to `tests/_helpers/`). Until then, leave that file's adoption to a
post-B03 follow-up commit.

---

## Process

For each file:
1. Identify the raw setups (run `grep -n 'Vault__Crypto()\|Vault__Sync(' <file>`).
2. Pick the matching fixture from D1's table.
3. Replace the setup; assertions stay identical.
4. Run the affected file: `pytest <file> -q`. Must pass.
5. Run the full suite: `pytest tests/unit/ -q`. Must pass.
6. Commit. Push.
7. Move to next file.

Commit cadence: one commit per file (or one per closely-related pair).

---

## Hard constraints

- **Behaviour preservation.** Identical inputs, identical outputs, same assertions.
- **No mocks.** Fixtures use snapshot+copytree; no `unittest.mock` introduced.
- **No `__init__.py` under `tests/`.**
- **Coverage must not regress.**
- **Suite must pass under `-n auto`** at every commit.
- **Each commit independently revertible.**

---

## Acceptance criteria

- [ ] All 18+ test files in design D1's table refactored to use existing fixtures (or NF2 if B02 has landed).
- [ ] Suite ≥ existing test count passing; coverage delta non-negative.
- [ ] Suite warm runtime drops by ≥ 25% on whichever runner is the reference (proportional to baseline).
- [ ] No source change to `sgit_ai/`.
- [ ] No new mocks (mock-pattern line count unchanged or lower).
- [ ] Closeout note appended to `team/villager/dev/v0.10.30__shared-fixtures-design.md` as §9 with before/after timings per file.

---

## Out of scope

- Adding new test scenarios.
- The 5 new fixtures from D2 (brief B02).
- The redundancy pass (brief B04).

---

## When done

Return a ≤ 250-word summary:
1. Files refactored (count + per-file before/after timing).
2. Suite warm runtime: before / after.
3. Coverage delta.
4. Mock-pattern line count delta.
5. Anything that surfaced about a fixture's API while adopting it (escalate to the design owner).
