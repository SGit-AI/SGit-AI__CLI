# Sonnet Onboarding — v0.13.x Brief-Pack

You are a fresh Claude Code Sonnet session starting work on the **SGit-AI CLI** v0.13.x sprint. The Villager team has produced a brief-pack at `team/villager/v0.13.x__brief-pack/` covering carry-forward work from v0.12.x + a new visualisation track. **Your job is to execute one or more briefs from the pack.**

---

## 1. The 60-second context

- **Repo:** `sgit-ai/sgit-ai__cli`. Branch: as Dinis specifies.
- **Released baseline:** **v0.13.0 just shipped** (rolled up from v0.12.x — Vault__Sync split, layered architecture, plugin system, workflow framework, surgical-write CLI, 98% coverage, 3,068 tests).
- **Architecture:** `osbot_utils.type_safe` (no Pydantic), no mocks, AES-256-GCM + HKDF + PBKDF2.
- **Layers (post-B13):** `crypto / storage / core / network / plugins`. No upward imports — enforced by `tests/unit/architecture/test_Layer_Imports.py`.
- **Your sprint:** v0.13.x patch series toward v0.14.0.

## 2. What v0.13.0 delivered (don't redo this)

- 12 sub-classes under `sgit_ai/core/actions/<command>/` (clone, push, pull, status, commit, etc.).
- `Workflow__Clone` (10-step pipeline) + `Workflow__Pull/Push/Fetch` scaffolding (NOT yet wired — that's B04).
- 5 read-only plugins (`history / inspect / file / check / dev`).
- Top-level CLI: 22 commands (down from ~70).
- `tests/conftest.py` + `tests/_helpers/vault_test_env.py` shared fixtures.
- Mutation orchestrator at `tests/mutation/run_mutations.py`.

Full detail: `team/villager/v0.12.x__perf-brief-pack/`.

## 3. Required reading order

1. **The brief Dinis named** (e.g., `team/villager/v0.13.x__brief-pack/brief__01__bug-fixes-from-debrief.md`).
2. `team/villager/v0.13.x__brief-pack/01__sprint-overview.md` — locked decisions + sequencing.
3. `team/villager/v0.13.x__brief-pack/00__index.md` — pack index.
4. **For visualisation briefs**: `visualisation/00__index.md` + the three design docs (D1/D2/D3).
5. `team/villager/v0.12.x__perf-brief-pack/02__sonnet-session-update-2026-05-05.md` — the Sonnet debrief that surfaced the carry-forward bugs.
6. `CLAUDE.md` (repo root) + `team/villager/CLAUDE.md`.
7. Your role file (every brief lists an "Owner role").

## 4. The four laws

| Law | What it means |
|---|---|
| **Type_Safe always** | All data classes use `Type_Safe`. No raw `str`/`int`/`dict` fields. Use `Safe_Str__*`. |
| **No mocks, no patches** | Real objects, real fixtures, real crypto. The in-memory transfer server IS the real implementation, not a mock. |
| **Behaviour preservation** | Refactorings must produce identical bytes for identical inputs. |
| **No `__init__.py` under `tests/`** | Conftest files + `tests/_helpers/` only. |

## 5. v0.13.x-specific rules

- **No backend changes.** Everything in this sprint is client-side. B08 + B08b (server clone packs) are archived at `team/villager/v0.12.x__perf-brief-pack/archived/` — don't pick them up.
- **Visualisation lives in `sgit_show/`** (new top-level package), NOT under `sgit_ai/`. The `sgit_ai/` layer-import test enforces no imports of `sgit_show/`.
- **Visualisation = three layers:** data source → analysis → renderer. CLI / JSON / HTML renderers from one analysis. Per design D1.
- **`rich` library** is the chosen CLI rendering library. Add to dependencies.
- **B08 archived briefs** (`archived/brief__08*.md`) are durable design docs, not active work. Don't pick them up unless Dinis says so.

## 6. The execution loop

```
1. Read your brief in full.
2. Read the design docs it references.
3. Read your role file + CLAUDE.md.
4. Restate the goal back to Dinis in one sentence; wait for "go".
5. Plan with TodoWrite — one todo per acceptance criterion.
6. Execute one todo at a time.
7. Run verification commands the brief specifies.
8. Commit + push (with `git pull --rebase` first). Use the brief's commit template.
9. Return the closeout summary the brief asks for.
```

## 7. Sequencing reminder

```
[v0.13.0 baseline]
       │
       ├─► B01 bug fixes      (parallel; small wins; unblocks B04)
       │
       ├─► B02 migration       (parallel; biggest perf win for old vaults)
       │       │
       │       └─► re-measure clone perf post-migration → unblock B08 decision
       │
       ├─► B03 clone-readonly into workflow
       │       │
       │       └─► B04 push/pull/fetch wiring
       │       └─► B05 per-mode clones (clone-branch is the headline)
       │
       ├─► B06 layer cleanup (combined B16+B17+B20)
       ├─► B07 CLI cruft (BLOCKED on Dinis input)
       ├─► B08 workflow runtime polish
       │
       └─► visualisation v01 framework  (parallel from day one)
              └─► v02-v05 (parallel; independent visualisations)
                  └─► v06 webui-export-prep
```

## 8. Coordination with the reviewer

A reviewer session (`claude/cli-explorer-session-J3WqA`) is running on a separate branch. After you push:
- They review for multi-paragraph docstrings, bare instantiations, raw-`str` Type_Safe fields, layer-import violations.
- They apply fixes on their branch.
- They log the merge in the v0.13.x review log (TBD path; typically under `team/humans/dinis_cruz/claude-code-web/`).

Don't wait for them between commits — keep pushing. They batch.

## 9. Hard rules (zero tolerance)

- Never commit code that doesn't pass `pytest tests/unit/ -n auto`.
- Never introduce a new layer-import violation. The 7 known violations in `KNOWN_VIOLATIONS` are the only allowed ones (and B06 reduces them).
- Never touch any file under `archived/` — those are deferred briefs, not active.
- Never modify any file under `sgit_ai/cli/CLI__Main.py` "just to make it work" — coordinate with B04 / B07 owners.

## 10. Where things live

```
sgit_ai/                         CLI engine (post-v0.13.0)
├── crypto/                      Layer 1
├── storage/                     Layer 2
├── network/                     Layer 4
├── core/
│   ├── actions/<command>/       per-command sub-folders (12 commands)
│   ├── Vault__Sync.py           258-line facade
│   └── Vault__Sync__Base.py     shared base
├── plugins/                     Layer 5 (5 read-only plugins)
└── workflow/                    framework + per-command workflows

sgit_show/                     NEW (per visualisation v01) — parallel package
├── _base/
├── data_sources/
├── analyses/
├── renderers/{cli,json,html}/
├── visualisations/
└── cli/

tests/
├── conftest.py                  shared fixtures (post-v0.12.0)
├── _helpers/                    Vault__Test_Env etc.
├── unit/                        runs in default pytest invocation
│   ├── architecture/            layer-import enforcement
│   ├── visual/                  NEW (per v01)
│   └── ... (other layers mirror sgit_ai/ structure)
└── integration/                 needs Python 3.12 venv
```

## 11. Things that look weird but are correct

- `Vault__Sync.py` is 258 lines (a facade). The implementation lives in 12 sub-classes under `core/actions/`.
- `sgit_ai/sync/` is GONE. All tests still live under `tests/unit/sync/` though — test layout drift is tracked but not blocking.
- `tests/unit/architecture/test_Layer_Imports.py` carries 7 `KNOWN_VIOLATIONS`. B06 reduces them; don't add to them.
- Push/Pull/Fetch workflow scaffolding exists but **isn't wired to runtime yet** (that's B04). Existing `Vault__Sync__{Push,Pull}.{push,pull}()` methods are still the runtime path.
- `clone_read_only` and `clone_from_transfer` bypass `Workflow__Clone` (B03 fixes this).

## 12. Five sentences you should be able to say after onboarding

1. "I am working on the SGit-AI CLI v0.13.x sprint."
2. "I am executing brief BNN, owned by the X role."
3. "My acceptance criteria are A, B, C; my deliverables are D, E."
4. "I will not introduce mocks, raw primitives in Type_Safe classes, `__init__.py` in `tests/`, or layer-import violations."
5. "If I get stuck or find that the brief's premise is wrong, I escalate to Dinis via the closeout summary."

Welcome. Now read your brief.
