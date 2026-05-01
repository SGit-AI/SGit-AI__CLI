# v0.10.30 Brief-Pack — Index

**Pack location:** `team/villager/dev/v0.10.30__brief-pack/`
**Master plan:** `team/villager/v0.10.30__next-phase-plan.md`
**Deep-analysis source:** `team/villager/v0.10.30__cross-team-summary.md`

This pack contains self-contained instruction documents ("briefs") to be
executed by Sonnet agents in separate sessions. Each brief specifies its
owner role, prerequisites, scope, acceptance criteria, and deliverables.

## Strict execution order

```
[Phase A — Measure]   01 + 02   (parallel)
       │
       └─ GATE: baseline docs merged
              │
[Phase B — Improve]   03  (design first)
                       │
                       ├──► 04  (implement shared fixtures)
                       └──► 05  (parallelize)
                                   │
                       └─ GATE: 06 acceptance criteria met
                                   │
[Deferred queue]      10–20  (order TBD after Phase B exit)
```

**Brief 06's acceptance criteria gate the entire deferred queue.** Do not
start brief 10 or later until brief 06 is signed off by Dinis.

## Briefs

### Phase A — Measure (read-only, no code changes)

| # | Brief | Owner | Status | Depends on |
|---|-------|-------|--------|------------|
| 01 | `01__test-coverage-baseline.md` | Villager QA | Ready to execute | — |
| 02 | `02__test-runtime-baseline.md` | Villager DevOps | Ready to execute | — |

01 and 02 run in parallel.

### Phase B — Improve (code changes allowed, scoped)

| # | Brief | Owner | Status | Depends on |
|---|-------|-------|--------|------------|
| 03 | `03__shared-fixtures-design-spec.md` | Villager Architect + Dev | Not yet written | 01, 02 merged |
| 04 | `04__shared-fixtures-implementation.md` | Villager Dev | Not yet written | 03 merged |
| 05 | `05__test-parallelization.md` | Villager DevOps | Not yet written | 02 merged |
| 06 | `06__test-infra-acceptance.md` | Villager DevOps + QA | Not yet written | 04, 05 merged |

Briefs 03–06 will be authored by the orchestrator AFTER briefs 01 and 02
return numbers. Designing shared fixtures without knowing which tests are
slow is wasted work.

### Deferred queue (do NOT start until brief 06 is signed off)

| # | Brief | Owner | Status |
|---|-------|-------|--------|
| 10 | `10__hardening-chmod-0600.md` | Villager Dev | Not yet written |
| 11 | `11__hardening-secure-unlink.md` | Villager Dev | Not yet written |
| 12 | `12__hardening-clear-kdf-cache.md` | Villager Dev + AppSec | Not yet written |
| 13 | `13__hardening-write-file-guard.md` | Villager Dev | Not yet written |
| 14 | `14__bug-delete-on-remote-push-state.md` | Villager Dev | Not yet written |
| 15 | `15__schema-push-state.md` | Villager Dev | Not yet written |
| 16 | `16__schema-clone-mode.md` | Villager Dev | Not yet written |
| 17 | `17__schema-local-config-extension.md` | Villager Dev | Not yet written |
| 18 | `18__crypto-determinism-tests.md` | Villager AppSec + Dev | Not yet written |
| 19 | `19__mutation-matrix-execution.md` | Villager AppSec + QA | Not yet written |
| 20 | `20__vault-sync-split.md` | Villager Architect + Dev | Not yet written |

Each deferred brief will be authored when its turn comes. Writing them
all up front would lock in choices that should be informed by Phase B's
results (e.g., the shared-fixtures pattern affects how the new test files
in 18 and 19 are structured).

## Reading order for an executor agent

When you are launched to execute a brief, read in this order:

1. The brief itself (`NN__<name>.md`).
2. Your role file in `team/villager/<role>/<role>__ROLE.md`.
3. `CLAUDE.md` at repo root.
4. `team/villager/CLAUDE.md`.
5. The cross-team summary `team/villager/v0.10.30__cross-team-summary.md`
   for context — but only the sections the brief points you at.

Do not read the entire deep-analysis output (32 finding files); the brief
will reference specific findings if relevant.

## Output discipline (applies to every brief)

- **Many small files. Never one big file.** Target ≤ 200 lines per markdown
  file; hard cap ~ 400 lines. Large markdown files cause creation errors.
- **Commit and push every 2–3 deliverables** so partial progress is safe.
- **Leave the working tree clean at the end of each brief.** No stray
  files, no uncommitted state.
- **Read-only briefs (Phase A) MUST NOT change source or tests.** They
  produce documentation only.
