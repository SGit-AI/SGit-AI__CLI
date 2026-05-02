# Test Framework Improvement Brief-Pack — Index

**Pack:** `team/villager/v0.10.30__test-framework-brief-pack/`
**Sprint goal:** ≥ 25% suite runtime reduction + coverage to high-90s, no mocks.

## Files

### Meta

| # | File | Purpose |
|---|------|---------|
| 00 | `00__index.md` | This file |
| 01 | `01__sprint-overview.md` | Headline numbers, goal, sequencing, constraints |

### Design (the WHAT and WHY)

| # | File | Captures |
|---|------|---------|
| D1 | `design__01__current-fixtures-and-adoption.md` | F1–F6 + `Vault__Test_Env` overview; 18-file adoption gap |
| D2 | `design__02__new-fixtures-catalog.md` | Five new fixtures with signatures + scope + isolation |
| D3 | `design__03__redundancy-patterns.md` | Five patterns where encryption is incidental |
| D4 | `design__04__pre-derived-keys-and-helpers.md` | `known_test_keys` + `tests/_helpers/` relocation |
| D5 | `design__05__coverage-roadmap.md` | Path from 88% to ≥ 95% |

### Executor briefs (the HOW)

| # | File | Owner | Status |
|---|------|-------|--------|
| B01 | `brief__01__adoption-refactor.md` | Villager Dev | BLOCKED on B22 (Vault__Sync split) |
| B02 | `brief__02__new-fixtures-impl.md` | Villager Dev | Ready (independent of B22) |
| B03 | `brief__03__key-cache-and-helpers-relocation.md` | Villager Dev | Ready (independent of B22) |
| B04 | `brief__04__redundancy-cleanup.md` | Villager Dev | BLOCKED on B02 |
| B05 | `brief__05__coverage-push-error-paths.md` | Villager Dev + QA | BLOCKED on B01 + B22 |
| B06 | `brief__06__coverage-push-cli-handlers.md` | Villager Dev + QA | BLOCKED on B01 |

## Sequencing

```
B22 (Vault__Sync split, in flight)
       │
       └──► B01 adoption refactor
                │
                ├──► B02 new fixtures ──► B04 redundancy cleanup
                │
                └──► B03 key cache + helpers relocation
                              │
                              └──► B05 / B06 coverage push
```

B02 + B03 are independent of B22; could start now in parallel.
B01 is the critical-path link between B22 and the rest.
B04 needs B02. B05 + B06 need B01.

## Output discipline (all briefs)

- Many small files. Each ≤ 200 lines target; hard cap ~ 400.
- Commit and push every 2–3 deliverables.
- Type_Safe for new fixture classes. No raw `dict`/`str`/`int` fields.
- No mocks. Real objects, real temp dirs, real crypto.
- No `__init__.py` under `tests/`.
- Suite must pass under `-n auto` at every commit.
