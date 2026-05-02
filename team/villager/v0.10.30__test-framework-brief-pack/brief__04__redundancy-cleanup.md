# Brief B04 — Redundancy Cleanup

**Owner role:** **Villager Dev**
**Status:** BLOCKED until B02 (new fixtures) and B03 (key cache + helpers) land.
**Prerequisites:** B02 + B03 merged.
**Estimated effort:** ~2 days
**Touches:** test files only — apply fixtures across the redundancy patterns. **No source under `sgit_ai/`.**

---

## Why this brief exists

Per `design__03__redundancy-patterns.md`: five patterns where
encryption is incidental to what's being tested. Each pattern maps to
a fixture that eliminates the incidental work without compromising
coverage or introducing mocks.

This brief audits the suite against the five patterns and applies the
matching fixture.

---

## Required reading

1. This brief.
2. `design__03__redundancy-patterns.md` (P1–P5).
3. `design__02__new-fixtures-catalog.md` (NF1–NF5 — needed for the remediation).
4. `design__04__pre-derived-keys-and-helpers.md` (`known_test_keys` + `precomputed_encrypted_blobs`).
5. `team/villager/dev/dev__ROLE.md` (preserve behaviour exactly).

---

## Scope

For each pattern P1–P5 from D3, identify affected tests and apply the
remediation:

| Pattern | Affected files (initial sweep) | Remediation |
|---|---|---|
| P1 — diff/log/blame full-cycle setup | `test_Vault__Diff.py`, `test_Vault__Diff__Coverage.py`, `test_Vault__Inspector__Coverage.py`, `test_Vault__Dump_Diff.py` | NF2 `vault_with_N_commits` |
| P2 — inspect tests building vaults | `test_Vault__Inspector__Coverage.py`, similar | NF2 or F4 `bare_vault_workspace` |
| P3 — CLI commands init'ing a vault | `test_CLI__Commands.py` (9 raw setups) | `Vault__Test_Env.setup_single_vault` (post-B03) |
| P4 — AppSec tests deriving keys | `test_AppSec__Vault_Security.py`, `test_Secrets__Store.py`, `test_Secrets__Store__Edge_Cases.py` | `known_test_keys` |
| P5 — object-store tests building blobs | `test_Vault__Sub_Tree__Determinism.py`, `test_Vault__Object_Store__*` | New `precomputed_encrypted_blobs` fixture (build in this brief) |

---

## Step 1 — Audit pass

Run `coverage report --show-missing` AND `pytest --durations=0` and
cross-reference with design D3's pattern list. Produce a per-test
inventory at:

`team/villager/v0.10.30__test-framework-brief-pack/changes__redundancy-audit.md`

For each test class or method affected: pattern (P1–P5), remediation
fixture, estimated savings.

---

## Step 2 — `precomputed_encrypted_blobs` fixture

Per design D3 §P5, add to `tests/conftest.py` (root):

```python
@pytest.fixture(scope='session')
def precomputed_encrypted_blobs(known_test_keys):
    crypto   = Vault__Crypto()
    keys     = known_test_keys['coral-equal-1234']
    read_key = keys['read_key_bytes']
    return {
        'small'  : crypto.encrypt(read_key, b'small content'),
        'medium' : crypto.encrypt(read_key, b'medium content' * 100),
        'large'  : crypto.encrypt(read_key, b'large content'  * 10_000),
    }
```

Tests for the fixture itself: round-trip decrypt, identity across
consumers, size assertions.

---

## Step 3 — Apply remediations

Per the audit doc, refactor each affected test. Process per file:

1. Read the test, identify the redundant encryption work.
2. Replace with the fixture from D3's table.
3. Run the affected test file → must pass.
4. Run the full suite → must pass.
5. Commit. Push.

Commit cadence: one commit per pattern (if small) or one per file (if larger).

---

## Step 4 — Closeout doc

Update `changes__redundancy-audit.md` with the post-pass status:
- Tests refactored: count.
- Tests still doing incidental encryption: enumerate (these become future-work seeds).
- Per-file timing delta.

---

## Hard constraints

- **No mocks introduced anywhere.**
- **No source change to `sgit_ai/`.**
- **Coverage must not regress.**
- **Suite must pass under `-n auto`** at every commit.
- **Behaviour preservation.** Same assertions, same outputs.
- **No `__init__.py` under `tests/`** (project rule; `tests/_helpers/` is the only exception per B03).

---

## Acceptance criteria

- [ ] Audit doc exists at `changes__redundancy-audit.md`.
- [ ] All identified tests refactored to consume the matching fixture.
- [ ] `precomputed_encrypted_blobs` fixture + tests shipped.
- [ ] Suite ≥ existing test count + ~3 (the new fixture tests) passing.
- [ ] Suite warm runtime drops by an additional ≥ 5% beyond what B01 + B02 achieved (cumulative ≥ 30% from start).
- [ ] Coverage delta non-negative.
- [ ] Mock-pattern line count unchanged or lower.
- [ ] Closeout doc lists residual redundancy for future work.

---

## Out of scope

- Adding new test scenarios.
- Coverage push (briefs B05 + B06).
- Redundancy patterns not in P1–P5 — flag them for future briefs.

---

## When done

Return a ≤ 250-word summary:
1. Audit doc location + tests refactored count.
2. New fixture (`precomputed_encrypted_blobs`) verified.
3. Cumulative suite warm-runtime reduction (start → post-B04).
4. Coverage delta.
5. Residual redundancy patterns flagged.
