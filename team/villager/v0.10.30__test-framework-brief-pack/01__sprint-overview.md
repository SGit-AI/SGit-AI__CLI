# Test Framework Improvement Brief-Pack — Sprint Overview

**Date:** 2026-05-01
**Status:** Plan only. No source changes from this doc.
**Pack location:** `team/villager/v0.10.30__test-framework-brief-pack/`
**Predecessor work:** v0.10.30 Phase A+B (`team/villager/dev/v0.10.30__shared-fixtures-design.md`,
`team/villager/devops/v0.10.30__phase-b-acceptance.md`).

This pack extends the v0.10.30 test infrastructure work (which shipped
F1–F6 fixtures + parallel CI). The single big finding from the chat
analysis: **infrastructure is good, adoption is patchy.** New tests
land that don't use the existing fixtures; per-test cost is rising
faster than the test count.

---

## Headline numbers

| Metric | v0.10.30 Phase B baseline | Now | Direction |
|---|---:|---:|---|
| Tests | 2,105 | 2,367 | +262 (+12%) |
| Suite warm | 124s | 285s | +161s (host variance + setup-heavy new tests) |
| Tests/sec | 16.9 | 8.3 | **−51%** |
| Coverage | 86% | 88% (per B22 plan) | +2pp |

The 285s figure is on a slower runner; the 124s baseline machine would
proportionally see ~150–160s today. Either way: **per-test cost is
rising** and v0.11.x will add another wave (instrumentation tools,
workflow framework, server packs, per-mode clones). Time to harden the
framework now.

---

## Sprint goal

1. Cut suite warm runtime by **≥ 25%** without adding mocks or
   compromising coverage.
2. Push coverage from 88% → **high-90s** by closing concrete gaps.
3. Keep the framework lean as the test count grows toward 3,000+.

---

## Pack contents

### Design docs (the WHAT and WHY)

| File | Captures |
|---|---|
| `design__01__current-fixtures-and-adoption.md` | Existing F1–F6 + `Vault__Test_Env`; 18-file adoption gap |
| `design__02__new-fixtures-catalog.md` | Five new fixtures (`two_clones_pushed`, `vault_with_N_commits`, `vault_with_pending_changes`, `vault_with_branches`, `read_only_clone`) |
| `design__03__redundancy-patterns.md` | Five patterns where encryption is incidental + remediation |
| `design__04__pre-derived-keys-and-helpers.md` | `known_test_keys` session fixture + `Vault__Test_Env` relocation to `tests/_helpers/` |
| `design__05__coverage-roadmap.md` | Path from 88% to ≥ 95% |

### Executor briefs (the HOW and WHO)

| # | File | Owner | Phase |
|---|------|-------|-------|
| B01 | `brief__01__adoption-refactor.md` | Villager Dev | Refactor 18 test files to use existing fixtures |
| B02 | `brief__02__new-fixtures-impl.md` | Villager Dev | Implement the 5 new fixtures |
| B03 | `brief__03__key-cache-and-helpers-relocation.md` | Villager Dev | `known_test_keys` + move `Vault__Test_Env` |
| B04 | `brief__04__redundancy-cleanup.md` | Villager Dev | Apply fixtures across the redundancy patterns |
| B05 | `brief__05__coverage-push-error-paths.md` | Villager Dev + QA | Long-tail `except Exception:` etc. |
| B06 | `brief__06__coverage-push-cli-handlers.md` | Villager Dev + QA | Direct CLI handler tests |

---

## Sequencing

```
B22 in flight      ← Vault__Sync split lands ~10 sub-classes + ≥50 direct tests
       │
       └──► B01 adoption refactor    (refactor including new B22 sub-class tests)
                │
                ├──► B02 new fixtures
                │       │
                │       └──► B04 redundancy cleanup (uses new fixtures)
                │
                └──► B03 key cache + helpers relocation
                              │
                              └──► B05/B06 coverage push (after framework is fast)

End state: fast, well-fixtured suite ready for v0.11.x B05 (workflow framework)
```

**Key sequencing constraint:** B01 (adoption refactor) lands **after**
B22 (Vault__Sync split) so it can refactor the new sub-class tests too.
Otherwise B01 has to redo work.

B05/B06 (coverage push) lands **after** B01–B04 so it operates on a
clean, fast framework.

---

## Locked constraints (apply across every brief in this pack)

| Rule | Source |
|---|---|
| **No mocks, no patches.** Real objects, snapshots, copytree. | CLAUDE.md, dev/qa role docs |
| **No `__init__.py` under `tests/`.** | CLAUDE.md |
| **Type_Safe everywhere** for new fixture / helper classes. | CLAUDE.md |
| **Coverage must not regress** at every commit boundary. | v0.10.30 Phase B gate |
| **Suite must pass under `-n auto`.** | Phase B parallel CI shape |

---

## What this pack deliberately does NOT do

- Add new test scenarios beyond fixture refactors and coverage closures.
- Touch `sgit_ai/` source code beyond what coverage paths require.
- Replace any v0.10.30 brief that's already in flight (B22 stays as
  designed).
- Pre-decide v0.11.x test infra. v0.11.x will use whatever this pack
  produces as its starting point.

---

## Document index

See `00__index.md` for the full file list with execution status.
