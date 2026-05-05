# v0.13.x Brief-Pack — Index

**Pack location:** `team/villager/v0.13.x__brief-pack/`
**Predecessor:** `team/villager/v0.12.x__perf-brief-pack/`
**Sprint horizon:** v0.13.x patch series toward **v0.14.0**
**Released baseline:** **v0.13.0** (rolled up from v0.12.x — workflow framework, layered architecture, plugin system, 12 sub-classes under `core/actions/`)

This pack contains:
- **Carry-forward briefs** from v0.12.x — work that wasn't completed before the v0.13.0 release cut.
- **Bug fixes** flagged by the Sonnet executor in `02__sonnet-session-update-2026-05-05.md`.
- **Visualisation sub-pack** — a parallel track adding "explain / how it works / what's going on" CLI commands, architected for future FastAPI + WebUI exposure.

## Files

### Meta

| # | File | Purpose |
|---|------|---------|
| 00 | `00__index.md` | This file |
| 01 | `01__sprint-overview.md` | Headline, decisions, sequencing |
| 02 | `02__carry-forward-from-v0.12.x.md` | What v0.12.x left unfinished + why |

### Carry-forward + bug-fix briefs

| # | File | Owner | Type |
|---|------|-------|---|
| B01 | `brief__01__bug-fixes-from-debrief.md` | Dev | bugs (B15-1, B04-1, B19, B22) |
| B02 | `brief__02__migration-command.md` | Dev | was v0.12.x B10; high value |
| B03 | `brief__03__clone-readonly-into-workflow.md` | Dev | was v0.12.x B06b/B18 |
| B04 | `brief__04__push-pull-fetch-wiring.md` | Dev | was v0.12.x B15 (sans-pack wiring) |
| B05 | `brief__05__per-mode-clones-no-pack.md` | Dev | was v0.12.x B09 (sans-pack) |
| B06 | `brief__06__layer-cleanup.md` | Architect + Dev | was v0.12.x B16 + B17 + B20 |
| B07 | `brief__07__cli-cruft-decisions.md` | Architect + Designer | was v0.12.x B21 |
| B08 | `brief__08__workflow-runtime-polish.md` | Dev | NEW from Sonnet §7 ideas |

### Visualisation sub-pack

| Path | Purpose |
|---|---|
| `visualisation/00__index.md` | Sub-pack TOC |
| `visualisation/design__01__architecture.md` | Top-level package layout, separation, FastAPI-ready interface |
| `visualisation/design__02__data-source-strategy.md` | Local + fetch-on-demand data layer |
| `visualisation/design__03__cli-visual-vocabulary.md` | ASCII / unicode / color / table / graph patterns |
| `visualisation/brief__v01__framework.md` | The core renderer / data-source / analysis primitives |
| `visualisation/brief__v02__commit-graph.md` | First visualisation: commit DAG with merges / branches |
| `visualisation/brief__v03__tree-explorer.md` | Interactive tree browser |
| `visualisation/brief__v04__metadata-explorer.md` | Vault stats, sizes, dedup ratios, hot trees |
| `visualisation/brief__v05__activity-timeline.md` | Per-author / per-day commit activity |
| `visualisation/brief__v06__webui-export-prep.md` | JSON-export shape ready for FastAPI/WebUI |

### Archived (from v0.12.x)

| Path | Status |
|---|---|
| `team/villager/v0.12.x__perf-brief-pack/archived/brief__08__server-clone-packs.md` | Deferred — see archived/README.md |
| `team/villager/v0.12.x__perf-brief-pack/archived/brief__08b__sg-send-backend-spec.md` | Deferred — same |

### Onboarding

| File | For |
|---|---|
| `sonnet__onboarding.md` | Fresh Sonnet sessions joining v0.13.x |

## Sequencing

```
B01 bug fixes    (parallel; small wins)
B02 migration    (independent; high value for old vaults)
       │
       └──► (post-B02 re-measurement: do we still need server packs?)
       │
B03 clone-readonly into workflow      (completes B06's promise)
       │
B04 push/pull/fetch wiring (no pack)  (depends on B03)
B05 per-mode clones (no pack)         (depends on B03)
B06 layer cleanup                     (independent)
B07 CLI cruft                         (needs Dinis input)
B08 workflow runtime polish           (independent; small)

Visualisation sub-pack runs in parallel from day one — it's a separate package.
```

## Output discipline (every brief)

- Many small files. Target ≤ 200 lines per markdown file.
- Commit + push every 2–3 deliverables.
- Type_Safe for new schemas; no raw `str` / `int` / `dict` fields.
- No mocks. Real objects, real fixtures.
- No `__init__.py` under `tests/`.
- Suite must pass under `-n auto` at every commit.
