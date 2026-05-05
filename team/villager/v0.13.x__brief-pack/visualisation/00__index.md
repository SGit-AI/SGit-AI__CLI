# Visualisation Sub-Pack — Index

**Pack location:** `team/villager/v0.13.x__brief-pack/visualisation/`
**Parent pack:** `team/villager/v0.13.x__brief-pack/`
**Status:** Plan only. Execution lives in the briefs.

This sub-pack adds **"explain / how-it-works / what's-going-on" CLI commands** to SGit. The intent: data-rich, modern, visual CLI experience for users who want to understand a vault's state — and the same code paths exposed via FastAPI + WebUI later, with no rewrites.

---

## The principle

> Every visualisation = three layers: **data source** (local + fetch-on-demand) → **analysis** (computations / graph algorithms / aggregations) → **presentation** (multiple renderers: CLI / JSON / HTML).
>
> Same code powers `sgit show` AND a future FastAPI endpoint AND a WebUI page. **No code rewrites when WebUI lands.**

This is **separate from `sgit_ai/`** — lives in a new top-level package `sgit_show/` (or `sgit_view/`, naming TBD). Independent enough to be extracted to its own pip package + repo eventually.

---

## Files

### Design docs

| # | File | Captures |
|---|------|---------|
| D1 | `design__01__architecture.md` | Three-layer model, package structure, FastAPI-readiness, library choices |
| D2 | `design__02__data-source-strategy.md` | Local-first + fetch-on-demand patterns, data classes, caching |
| D3 | `design__03__cli-visual-vocabulary.md` | ASCII / unicode / color / table / graph patterns; `rich`-library usage |

### Briefs

| # | File | Type | Effort |
|---|------|------|---|
| v01 | `brief__v01__framework.md` | Core framework + first dummy renderer | ~2 days |
| v02 | `brief__v02__commit-graph.md` | Commit DAG with merges / branches | ~1 day |
| v03 | `brief__v03__tree-explorer.md` | Interactive vault tree browser | ~1 day |
| v04 | `brief__v04__metadata-explorer.md` | Vault stats, sizes, dedup ratios, hot trees | ~1 day |
| v05 | `brief__v05__activity-timeline.md` | Per-author / per-day commit activity | ~1 day |
| v06 | `brief__v06__webui-export-prep.md` | JSON-export shape ready for FastAPI/WebUI | ~½ day |

---

## Sequencing

```
D1, D2, D3 (designs)
       │
       └──► v01 framework  (sets up the package + first end-to-end visualisation)
              │
              ├──► v02 commit-graph    (independent — simple enough to ship first real viz)
              ├──► v03 tree-explorer
              ├──► v04 metadata-explorer
              ├──► v05 activity-timeline
              │       │
              │       └──► v06 webui-export-prep  (needs the renderers from v02-v05)
```

v02–v05 can run in parallel by separate Sonnet agents — they're independent visualisations.

---

## Locked decisions

| # | Decision |
|---|---|
| 1 | **Visualisation lives in `sgit_show/`** (new top-level), NOT `sgit_ai/visual/`. Future-extractable. |
| 2 | **Three-layer architecture:** data source → analysis → presentation. Mandatory for every visualisation. |
| 3 | **Multiple renderers from one analysis:** CLI / JSON / HTML / plaintext. JSON is the contract that powers FastAPI. |
| 4 | **`rich` library** for CLI rendering (tables, trees, color, syntax). Adds a runtime dependency; well worth it. |
| 5 | **No backend changes.** Data either comes from the local vault or via existing client API. |
| 6 | **No mocks.** Real `Vault__Test_Env` fixtures, real renderer outputs. |

---

## Locked-in (per Dinis 2026-05-05)

1. **Package name:** `sgit_show` (matches the CLI invocation).
2. **CLI invocation:** `sgit show <…>`.
3. **Library:** `rich`.

No remaining open items; v01 is unblocked to start.

---

## What this sub-pack deliberately does NOT do

- Build a TUI (full-screen terminal UI). Visualisations are command-line invocations producing rendered output. A future v0.14+ might add `textual`-based interactive TUIs.
- Build the FastAPI endpoints. v06 prepares the JSON-export contracts; FastAPI itself is a future brief.
- Re-implement existing inspect / history commands. Visualisations are NEW capabilities; existing `sgit history log` keeps working.
