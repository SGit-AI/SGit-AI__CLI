# Brief 03 — Shared Fixtures Design Spec (v0.10.30)

**Phase:** B — Improve (design first, code in brief 04)
**Owner role:** **Villager Architect** (primary, design ownership) + **Villager Dev** (technical review)
**Status:** Ready to execute (Phase A baselines now exist)
**Prerequisites:** Briefs 01 and 02 are merged (they are).
**Estimated effort:** ~3–4 hours
**Read-only on source/tests.** This brief produces a design document only.
No `sgit_ai/` or `tests/` edits. Brief 04 implements the design.

---

## Why this brief exists

Brief 02 (runtime baseline) shows the suite is CPU-bound at 124s warm, and
the slowest files are setup-dominated. Three concrete shared-fixture
candidates were identified:

| Candidate | Source file | Expensive operation | Current cost |
|---|---|---|---|
| PKI keypair | `tests/unit/cli/test_CLI__PKI.py` | RSA-OAEP 4096 + ECDSA-P256 generation per test | 9.20s / 28 tests |
| Pre-built bare vault | `tests/unit/objects/test_Vault__Bare.py` | Full init + commit + ref-write per test | (setup-dominated) |
| Pre-cloned simple-token vault | `tests/unit/sync/test_Vault__Sync__Simple_Token.py` + `…__Probe.py` | Simple-token key derivation + clone round-trip | 11.70s / 10 tests + similar in Probe |

These are *suspected* hotspots — your job in this brief is to **verify**
each one against the actual test code and **design** the shared-fixture
pattern that resolves them without compromising test correctness.

The non-negotiable constraint from Dinis: **pre-built state must NOT
compromise what's being tested.** No shared mutable state hiding bugs. No
fixture that masks a real failure mode. If a test relies on "fresh state
for every run", it stays fresh — only setup that is genuinely behaviour-
irrelevant gets shared.

---

## Required reading

1. This brief.
2. `team/villager/architect/architect__ROLE.md` and `team/villager/dev/dev__ROLE.md`.
3. `team/villager/qa/v0.10.30__coverage-baseline.md` — what's covered now (don't break it).
4. `team/villager/devops/v0.10.30__runtime-baseline.md` — full duration data, top-15 files.
5. `CLAUDE.md` and `team/villager/CLAUDE.md` — Type_Safe rules, no-mocks rule, `__init__.py` rule for tests.
6. The three suspected-hotspot test files (read-only):
   - `tests/unit/cli/test_CLI__PKI.py`
   - `tests/unit/objects/test_Vault__Bare.py`
   - `tests/unit/sync/test_Vault__Sync__Simple_Token.py`
   - `tests/unit/sync/test_Vault__Sync__Probe.py`
7. Existing `conftest.py` files anywhere under `tests/` — find them with
   `find tests -name conftest.py`. Honor what's already there.

---

## What you produce

A single design document at:

`team/villager/dev/v0.10.30__shared-fixtures-design.md`

Target ≤ 250 lines. Sections below.

### Section 1: Hotspot verification

For each of the three candidates from brief 02:

- Read the test file. Confirm or refute the "setup-dominated" hypothesis.
- Identify the exact expensive operation (line numbers).
- Identify whether each test mutates the expensive object or only reads
  it.
- Classify each test as: SHARE-SAFE (read-only on the expensive object),
  MUTATES-SAFELY (mutates a copy / scratch field), or NEEDS-FRESH (must
  rebuild from scratch).
- Report the share-safe percentage per file. If < 70% are share-safe, the
  shared fixture is probably not worth it for that file.

### Section 2: Fixture catalogue

For each fixture you propose to add, specify:

- **Name** (e.g., `session_pki_keypair`, `session_bare_vault`).
- **Scope** (`session`, `module`, `class`, `function`). Default to
  `session` for genuinely immutable expensive objects; downscope only
  when sharing risks correctness.
- **Build cost** estimate.
- **Mutation contract** — what callers may and may not do to the returned
  object. If the fixture returns a Type_Safe instance, document whether
  callers may mutate it. If callers commonly mutate, return a deep-copy
  factory instead of the object directly.
- **Location** (which `conftest.py`).
- **Tests it serves** (file list + estimated tests-per-file).
- **Expected runtime saving** (rough; e.g., "saves ~7s on
  `test_CLI__PKI.py`").

### Section 3: Isolation contract

For each fixture, define how a test author proves they're using it
correctly. The mechanism matters more than the words. Examples:

- **Frozen objects** — fixture returns a Type_Safe instance with `freeze()`
  invoked or wrapped in a read-only proxy.
- **Factory functions** — fixture returns a `def make_x() -> X` callable
  so each test gets a fresh instance built from cached intermediate state
  (e.g., cached PBKDF2 result, fresh vault wrapping it).
- **Snapshot + clone** — fixture builds once, then `copy.deepcopy()` per
  use.

Pick one (or a small mix) and justify. The criterion: **a future agent
should not be able to write a passing test that relies on a previous
test having mutated the fixture.**

### Section 4: Carve-outs

List tests / test files that will NOT use the shared fixtures and why.
Examples:
- Tests that intentionally exercise key generation itself.
- Tests that depend on temporal uniqueness (timestamps, random IVs in
  non-deterministic paths).
- Tests that verify init/cleanup behaviour.

### Section 5: Conftest layout proposal

Concrete file plan:

- Where do new `conftest.py` files live?
- What does the directory tree look like?
- How are fixtures namespaced to avoid collision?
- Is there a top-level `tests/conftest.py`, per-subdir, or both?

Honor the project rule: **no `__init__.py` files anywhere in `tests/`**
(see `CLAUDE.md`). Conftest files are fine; `__init__.py` files are not.

### Section 6: Risks and verification

- What could go wrong? (Stale fixture, hidden mutation, ordering coupling,
  cross-test pollution.)
- How do we detect those? (Run the suite under `pytest -p no:randomly` AND
  with random ordering; if results differ, there's pollution.)
- How does brief 04's executor verify they didn't introduce a regression?
  Specify the exact verification commands.

### Section 7: Brief 04 hand-off

A bulleted checklist that brief 04's executor can follow without re-doing
the design work. Each item: "add fixture X in file Y; refactor test
Z to consume it; expect runtime saving W". Brief 04's effort is bounded
by the size of this checklist.

---

## Acceptance criteria

- [ ] Design doc exists at `team/villager/dev/v0.10.30__shared-fixtures-design.md`,
      ≤ 250 lines.
- [ ] All seven sections populated with verified data (not speculation).
- [ ] Each proposed fixture has a named isolation mechanism.
- [ ] Carve-outs explicitly listed.
- [ ] Brief 04's checklist is concrete enough to execute without
      re-reading the test files.
- [ ] Read-only constraint verified — `git diff -- sgit_ai/ tests/` is
      empty.
- [ ] Doc is committed and pushed.

---

## Out of scope

- Implementation. That's brief 04.
- Parallelization. That's brief 05. (But: note in the design any fixture
  that would block parallel execution — pollution risks compound under
  xdist.)
- Adding dependencies. The implementation in brief 04 may use
  `pytest.fixture` only; no new packages.
- New test scenarios. This brief restructures existing setup; the
  scenario set stays identical.

---

## When you finish

Return a ≤ 250-word summary stating:
1. Hotspot verification result per candidate (share-safe % per file).
2. Number of fixtures proposed + total estimated runtime saving.
3. Isolation mechanism chosen.
4. Number of carve-outs.
5. Any candidate from brief 02 that you advise NOT to convert (and why).
