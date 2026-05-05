# v0.13.x Sprint Overview

**Date:** 2026-05-05
**Released baseline:** v0.13.0 (rolled up from v0.12.x)
**Sprint horizon:** v0.13.x patch series toward v0.14.0
**Status:** Plan only. Execution in the briefs.

This pack closes out the v0.12.x work that didn't make the v0.13.0 cut,
fixes the two known bugs surfaced in the Sonnet debrief, and opens a
new track: **visualisation / "explain what's going on" CLI commands**
architected for future FastAPI + WebUI exposure.

---

## What v0.13.0 delivered (rolled up from v0.12.x)

The v0.12.x sprint shipped the substantive architecture work:

- **Workflow framework** — `Step` / `Workflow` / `Workflow__Workspace` / `Workflow__Runner` with idempotency + resume + version-check + transaction-log emission hooks.
- **Clone refactored** — 10-step `Workflow__Clone` (full-clone path).
- **Layered architecture** — `crypto` / `storage` / `core` / `network` / `plugins` with enforced no-upward-imports (18-test layer-import suite).
- **`Vault__Sync.py`** dissolved → 12 sub-classes under `core/actions/<command>/`.
- **CLI namespaces** — 22 top-level commands (down from ~70). New: `branch / history / file / inspect / check / dev / vault / pki`.
- **Plugin system** — 5 read-only plugins (`history / inspect / file / check / dev`) with feature-flag config + loader.
- **B07 diagnosis** — confirmed H3 (random-IV trees) + H5 (historical-tree walk) as primary perf root causes; quantified the case-study at 184s tree-walk.
- **3,068 tests passing.**

Full detail in `team/villager/v0.12.x__perf-brief-pack/`.

---

## What v0.12.x deferred (rationale)

### B08 + B08b — Server clone packs

**Archived to `team/villager/v0.12.x__perf-brief-pack/archived/`.**

The B07 diagnosis confirmed two things: H3 (random-IV trees can't dedup) is fixable with **B10 migration command** (purely client-side), and H5 (historical trees mostly wasted) is fixable with **B05 clone-branch mode** (also purely client-side). Together those two close roughly 95% of the perf gap **without any backend change**.

Server packs deliver an additional ~5–10× on top, but for the typical vault activity (dozens of files / commit, HMAC-IV from creation) post-migration clone times land in the 10–20s range — acceptable. So B08 / B08b are deferred until we have post-migration data showing they're still needed.

The briefs are durable design docs — wire format, endpoints, cache policy, pre-warming, backward-compat are all valid when the work resumes.

**SG/Send team thread:** Dinis to graceful-pause the conversation. Suggested wording: *"We're going to validate client-side migration + thin-clone first; the brief stays valid but we may not need it. Can we put this on hold and circle back in 2–3 weeks?"*

### Other v0.12.x leftovers — carry-forward into v0.13.x

- **Bug B15-1**: `_fetch_missing_objects` keyword arg mismatch (will throw TypeError at runtime if pull/fetch workflow is invoked) — fixed in B01.
- **Bug B04-1**: `_detect_context()` shipped but `run()` never calls it — fixed in B01.
- **Bug B19**: `read_key_hex` typed as `Safe_Str__Write_Key` (no `Safe_Str__Read_Key` exists) — fixed in B01.
- **Bug B22**: `Workflow__Runner` swallows typed exceptions — fixed in B01.
- **B10** migration command — high value, B02 in this pack.
- **B06b / B18** clone_read_only into Workflow__Clone — B03.
- **B15 wiring** — push/pull/fetch workflows shipped as scaffolding but NOT wired into runtime — B04 (sans-pack wiring).
- **B09** per-mode clones — stubs registered, full impl deferred — B05 (sans-pack version).
- **B16, B17, B20** layer-cleanup follow-ups (Vault__Crypto → network dep, Vault__Transfer relocation, Graph_Walk extraction) — combined into B06.
- **B21** CLI cruft (`stash / remote / send / receive / publish / export` placement) — B07 (needs Dinis decision).

---

## What v0.13.x adds (new — visualisation track)

A **parallel sub-pack** at `visualisation/`. Independent of all the carry-forward work. Different package (`sgit_show/` as a sibling top-level, not under `sgit_ai/`).

**Why now:** v0.13.0 ships a clean architecture (workflow / steps / layered / plugins). The data is now structured + accessible. Visualisation tools that "explain what's going on" — commit graphs, tree explorers, metadata stats, activity timelines — become natural to build on top.

**Architecture principle:** every visualisation = three layers — **data source** (local + fetch-on-demand) → **analysis** (computations / aggregations / graph algorithms) → **presentation** (multiple renderers: CLI / JSON / HTML). The same code powers a `sgit show` CLI command AND a future FastAPI endpoint AND a WebUI page. **No code rewrites when WebUI lands.**

Six initial visualisations (briefs `v01`–`v06`). Each is small (1–2 days). Together they form a "first batch of users will love this" set:
- Commit DAG with merges / branches
- Interactive tree browser
- Vault stats + dedup ratios + hot trees
- Per-author / per-day activity timeline
- (And a JSON-export framework for the future WebUI)

---

## Sequencing

```
[v0.13.0 baseline]
       │
       ├─► B01 bug fixes      (parallel — small wins, unblock test correctness)
       │
       ├─► B02 migration       (parallel — independent; biggest perf win for old vaults)
       │       │
       │       └─► re-measure clone perf post-migration
       │              (if acceptable: B08 stays archived for v0.14+)
       │              (if not: pull B08 / B08b out of archive)
       │
       ├─► B03 clone-readonly into workflow   (completes B06's promise)
       │       │
       │       └─► B04 push/pull/fetch wiring (no pack)
       │       └─► B05 per-mode clones (no pack)
       │
       ├─► B06 layer cleanup (B16+B17+B20 combined)
       │
       ├─► B07 CLI cruft (needs Dinis input first)
       │
       ├─► B08 workflow runtime polish
       │
       └─► visualisation sub-pack (parallel from day one)
              │
              ├─► visualisation framework (v01)
              │
              ├─► v02 commit-graph
              ├─► v03 tree-explorer
              ├─► v04 metadata-explorer
              ├─► v05 activity-timeline
              └─► v06 webui-export-prep
```

Critical path: B01 + B02 first (small, independent). Visualisation runs in parallel.

---

## Locked decisions

| # | Decision |
|---|---|
| 1 | **Defer server clone packs** (B08/B08b archived). Re-evaluate post-migration. |
| 2 | **Visualisation lives in `sgit_show/`** (separate top-level package), not under `sgit_ai/`. Future-extractable to its own pip package. |
| 3 | **Visualisation supports CLI + JSON + HTML renderers** from day one — same code, three outputs. |
| 4 | **Visualisation CLI invocation: `sgit show <…>`** (matches the package name). |
| 5 | **Visualisation library: `rich`.** Tables / trees / DAGs / sparklines; gracefully degrades on dumb terminals. |
| 6 | **No backend changes in v0.13.x.** Everything is client-side. |
| 7 | **Bug fixes from the Sonnet debrief are top priority** — B15-1 will throw TypeError when push/pull workflow is invoked; can't ship those without the fix. |
| 8 | **B07 CLI cruft placement (option b — semantic homes):** `stash`, `remote`, `export` → `sgit vault <…>`. `send`, `receive`, `publish` → `sgit share <…>` (new namespace). No `utils` namespace. Final top-level: 16 commands + 10 namespaces. |

---

## Open items still owned by Dinis

All previously-open items resolved. New items will surface as briefs execute.

---

## What this pack deliberately does NOT do

- Pre-decide visualisation graphic styles (briefs v02–v05 design those).
- Re-spec server-side packs (archived B08 still applies if pulled back).
- Touch any source code.
- Schedule v0.14.0 — that depends on what v0.13.x produces.

---

## Document index in this pack

See `00__index.md`.
