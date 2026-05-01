# v0.11.x → v0.12 Sprint Overview

**Date:** 2026-05-01
**Status:** Plan only. No source changes from this doc; execution lives in the brief files.
**Predecessor:** `team/villager/v0.11__clone-perf-strategy.md` (the strategy that fed this pack)
**Sprint horizon:** v0.11.x patch series, leading to **v0.12.0**

## Why this sprint

Two motivating concerns merged into one body of work:

1. **Clone performance is bad.** Real-world case-study: 4-agent collaborative website vault clones in ~202s; tree walking alone is 184s (91%) for 2,375 trees serving 165 actual files.
2. **CLI sprawl.** 67 top-level commands; UX clarity suffers; new perf tools have nowhere clean to live.

Tackling both together makes sense:
- The new visualization / instrumentation tools (Phase 0) need a home — the new `sgit dev <…>` namespace gives them one.
- The new clone modes (clone-branch, clone-headless, clone-range) need first-class top-level slots — the CLI restructure does that.
- The workflow framework (steps + Type_Safe schemas) underpins both better observability AND modular performance work.

## Locked-in decisions (post-strategy-v1)

| # | Decision |
|---|----------|
| 1 | Sub-command namespaces: `sgit inspect <…>` (read-only inspection) and `sgit dev <…>` (dev/debug + perf tools). Plus `history`, `file`, `vault`, `branch`, `check`, `pki`. |
| 2 | **No command-level back-compat.** Clean cut at v0.11.0; no aliases for renamed commands. |
| 3 | Vault-format changes are allowed; newer vaults may require newer binaries; provide a migration command (rekey precedent). |
| 4 | Default `clone` is **full** clone (Git-compatible). |
| 5 | Backend is FastAPI; server-side packs / caches / new endpoints are all on the menu. |
| 6 | Four top-level clone commands: `clone`, `clone-branch`, `clone-headless`, `clone-range`. `--bare` is an orthogonal flag combinable with each. |
| 7 | New top-level `create` (init + remote + publish, one-shot). |
| 8 | Trim aggressively: even `log` and `diff` move to `sgit history <…>`. Top-level = primitives only. |
| 9 | **Context-aware command visibility.** Inside-vault hides clone family; outside-vault hides commit/push/pull. |
| 10 | **Workflow framework.** Key commands (clone, push, pull, fetch) split into idempotent steps; each step's input/output is a Type_Safe schema persisted to `.sg_vault/work/`. Steps are unit-testable, individually executable for debug, resumable. |
| 11 | This work spans **both Villager (hardening) and Explorer (new architecture)**. The pack tags ownership per brief. |

## High-level shape

```
PHASE 0  Instrumentation             ← Villager Dev (B01)
            │
            ├──► PHASE 3  Diagnose     ← Villager Dev (B07)
            │                                │
PHASE 1  CLI restructure              ←      │  ← Villager Architect + Dev (B02, B03, B04)
            │                                │
PHASE 2  Workflow framework           ← Explorer + Villager (B05, B06)
            │                                │
            ▼                                ▼
PHASE 4  Server-side clone packs      ← Explorer (B08) — load-bearing perf fix
            │
            ▼
PHASE 5  Per-mode clone + migration   ← Villager Dev (B09, B10)
            │
            ▼
PHASE 6  Push / pull / fetch          ← Villager Dev (B11)
```

## What this pack deliberately does NOT do

- Pre-decide the exact wire format of clone packs (B08 designs that).
- Pre-decide the exact step granularity of clone (B05 + B06 design that).
- Author detailed step-by-step migration scripts (B10 does that).
- Pre-decide where `share`/`contacts`/`send`/`receive` live in the new CLI tree (B02 inventories first).
- Touch any source code.

## Open items still owned by Dinis

1. **Sub-question on Fix A** — "default clone produces full working copy" → does that mean HEAD-only is fine (historical trees may defer) or must full history be available offline? Drives whether `clone-branch` is a separate command or the default behaviour. Captured in `design__01__access-modes.md`.
2. **Workspace lifetime** in the workflow framework — clean up on success by default, or keep for inspection? Captured in `design__04__workflow-framework.md` §6.
3. **Top-level cruft inventory** — many commands (`drop`, `wipe`, `clean`, `uninit`, `pop`, `revert`, `info`, `update`, `new`, `off`, `on`, `list`) need an inventory pass. Brief B02 does this.
4. **`share` / `contacts` / `send` / `receive` / `publish`** — message-passing namespace? Brief B02 calls this out for Dinis.

## Document index in this pack

See `00__index.md`.
