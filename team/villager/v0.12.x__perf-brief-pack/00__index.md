# v0.12.x sprint (post-v0.12.0 release) Performance + CLI Restructure Brief-Pack — Index

**Pack location:** `team/villager/v0.12.x__perf-brief-pack/`
**Strategy doc:** `team/villager/v0.11__clone-perf-strategy.md` (predecessor)
**Sprint horizon:** v0.11.x series leading to **v0.12.0** lock-in
**Released baseline:** v0.11.0 (just promoted from `dev` to `main`)

This pack contains:
- **Design docs** capturing architecture / decisions / approach mapped in the planning sessions.
- **Executor briefs** for Sonnet sessions to pick up and execute.
- **Onboarding doc** for fresh Sonnet sessions starting work.

## Files

### Meta

| # | File | Purpose |
|---|------|---------|
| 00 | `00__index.md` | This file |
| 01 | `01__sprint-overview.md` | High-level sprint plan + sequencing + scope |

### Design docs (architecture / decisions captured)

| # | File | Captures |
|---|------|---------|
| D1 | `design__01__access-modes.md` | The 4 clone modes + `--bare` flag dimension |
| D2 | `design__02__cli-command-surface.md` | Top-level tree, namespaces, primitive principle |
| D3 | `design__03__context-aware-visibility.md` | Inside-vault / outside-vault / bare context model |
| D4 | `design__04__workflow-framework.md` | Step / Workflow architecture, `.sg_vault/work/` layout |
| D5 | `design__05__clone-pack-format.md` | Server-side pack design, per-mode catalog, FastAPI shape |
| D6 | `design__06__layered-architecture.md` | 5 layers: Crypto / Storage / Core / Network / Plugins; dependency rules; PKI prep |
| D7 | `design__07__transaction-log.md` | Append-only transaction log; OFF default; opt-in via config / `--trace` / env |
| D8 | `design__08__plugin-system.md` | Read-only namespaces as runtime-loadable plugins with feature flags |

### Executor briefs (numbered for execution order; see §Sequencing)

| # | File | Owner | Phase |
|---|------|-------|-------|
| B01 | `brief__01__instrumentation-tools.md` | Villager Dev | 0 — measure first |
| B02 | `brief__02__cli-restructure-namespaces.md` | Villager Architect + Dev | 1a — CLI cleanup |
| B03 | `brief__03__cli-restructure-clone-family.md` | Villager Architect + Dev | 1b — top-level shape |
| B04 | `brief__04__context-visibility-impl.md` | Villager Dev | 1c — UX |
| B05 | `brief__05__workflow-framework-impl.md` | **Explorer** Architect + Dev | 2a — new framework |
| B06 | `brief__06__workflow-apply-clone.md` | Villager Dev (Explorer-blessed) | 2b — refactor clone |
| B07 | `brief__07__diagnose-case-study.md` | Villager Dev + Architect | 3 — numbers |
| B08 | `brief__08__server-clone-packs.md` | **Explorer** Architect + Dev | 4 — server packs |
| B09 | `brief__09__per-mode-clone-impl.md` | Villager Dev | 5 — clone-branch / headless / range |
| B10 | `brief__10__migration-command.md` | Villager Dev | 5 — migration |
| B12 | `brief__12__layered-restructure-storage.md` | Architect + Villager Dev | 6a — Storage layer |
| B13 | `brief__13__layered-restructure-core-network.md` | Architect + Villager Dev | 6b — Core + Network split (the big one) |
| B14 | `brief__14__plugin-system-impl.md` | Architect + Villager Dev | 7 — plugin system + read-only namespace migration |
| B15 | `brief__15__push-pull-fetch-generalize.md` | Villager Dev | 8 — generalise (post-restructure) |

### Onboarding

| # | File | For |
|---|------|-----|
| Z | `sonnet__onboarding.md` | Fresh Claude Code Sonnet sessions joining this work |

## Sequencing

```
B01 instrumentation tools   (Phase 0 — runs first)
        │
        ├─→ B07 diagnose case-study  (any time after B01)
        │
B02 CLI namespaces  ───┐
B03 CLI clone family ──┤   (Phase 1 — independent of B01; can run in parallel)
B04 context visibility ┘
        │
B05 workflow framework  (Phase 2a — Explorer; independent of B01–B04)
        │
B06 apply workflow to clone  (Phase 2b — depends on B05)
        │
        ├──► B08 server clone packs  (Phase 4 — Explorer; depends on B07 + B06)
        │            │
        │            ├──► B09 per-mode clone impl  (depends on B03 + B06 + B08)
        │            └──► B10 migration command   (depends on B08)
        │
        └──► B12 Storage layer extract  (Phase 6a — depends on B06)
                     │
                     └──► B13 Core + Network split  (Phase 6b — depends on B12)
                                  │
                                  ├──► B14 plugin system  (Phase 7 — depends on B13)
                                  └──► B15 push/pull/fetch generalise  (Phase 8 — depends on B13 + B08)
```

Multiple agents can run in parallel where the graph permits.

Two critical paths run in parallel after B06:

- **Performance critical path:** `B01 → B07 → B08 → B09` (measure → diagnose → server packs → per-mode impl)
- **Architecture critical path:** `B06 → B12 → B13 → B14 → B15` (workflow → storage → core+network → plugins → push/pull)

## Scope by phase

| Phase | Goal | Briefs |
|---|---|---|
| 0 | Instrumentation: see what's slow before changing anything | B01 |
| 1 | CLI restructure: trim 67 top-level commands → ~14 + 8 namespaces; context-aware visibility | B02, B03, B04 |
| 2 | Workflow framework: Step/Workflow primitives + apply to clone | B05, B06 |
| 3 | Numbers-grounded diagnosis on case-study vault | B07 |
| 4 | Server-side clone packs (FastAPI backend, encrypted, immutable) | B08 |
| 5 | Per-mode clone implementations + migration command | B09, B10 |
| 6 | Layered architecture restructure (Storage; then Core + Network) | B12, B13 |
| 7 | Plugin system: read-only namespaces as feature-flaggable plugins | B14 |
| 8 | Generalise: push / pull / fetch (post-restructure) | B15 |

## Output discipline (all briefs)

- **Many small files. Never one big file.** Target ≤ 200 lines per markdown file. Hard cap ≈ 400.
- **Commit and push every 2–3 deliverables** so partial progress is safe.
- **Type_Safe always.** No raw primitives in data classes. No mocks in tests.
- **Behaviour preservation** unless the brief explicitly says otherwise (some briefs change behaviour by design — they call it out).
- **No `__init__.py` anywhere under `tests/`** (project rule).
