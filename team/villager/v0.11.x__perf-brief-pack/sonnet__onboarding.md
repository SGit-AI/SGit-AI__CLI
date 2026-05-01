# Sonnet Onboarding — v0.11.x Perf Brief-Pack

You are a fresh Claude Code Sonnet session starting work on the
**SGit-AI CLI** repository. The Villager team has just produced a
v0.11.x → v0.12 brief-pack covering clone performance, CLI
restructure, and a workflow framework. **Your job is to execute one
or more briefs from the pack.**

This onboarding doc is your full briefing — read it before opening
the brief Dinis pointed you at.

---

## 1. The 60-second context

- **Repo:** `sgit-ai/sgit-ai__cli` (Python CLI; encrypted-vault sync; zero-knowledge crypto).
- **Branch you work on:** `claude/villager-multi-agent-setup-sUBO6` (or the branch Dinis specifies for this work). Pull and rebase before each push — multiple Sonnet sessions may be active.
- **Architecture:** `osbot_utils.type_safe` (no Pydantic), no mocks, AES-256-GCM + HKDF + PBKDF2.
- **Released baseline:** v0.11.0 just promoted to main. v0.12.0 is the lock-in target.
- **Your sprint:** v0.11.x patch series → v0.12.

## 2. Required reading order

Read in this order. Stop when you have enough context for your brief.

1. **The brief you are executing** — pointed to by Dinis (e.g. `team/villager/v0.11.x__perf-brief-pack/brief__01__instrumentation-tools.md`). Read in full, twice.
2. **The pack index** — `team/villager/v0.11.x__perf-brief-pack/00__index.md` — see what's done, what depends on what.
3. **The sprint overview** — `team/villager/v0.11.x__perf-brief-pack/01__sprint-overview.md` — locked-in decisions, phase shape.
4. **The design docs** the brief references — typically 1–2 of:
   - `design__01__access-modes.md`
   - `design__02__cli-command-surface.md`
   - `design__03__context-aware-visibility.md`
   - `design__04__workflow-framework.md`
   - `design__05__clone-pack-format.md`
5. **Your role file** — every brief lists an "Owner role". Read its `*__ROLE.md`:
   - `team/villager/architect/architect__ROLE.md`
   - `team/villager/dev/dev__ROLE.md`
   - `team/villager/appsec/appsec__ROLE.md`
   - `team/villager/qa/qa__ROLE.md`
   - `team/villager/devops/devops__ROLE.md`
   - (Explorer roles live under `team/explorer/`.)
6. **Project rules:**
   - `CLAUDE.md` (repo root) — Type_Safe rules, no-mocks rule, naming conventions, integration-test-venv setup.
   - `team/villager/CLAUDE.md` — Villager team mission, methodology, working agreements.

Do not read the predecessor v0.10.30 brief-pack unless your brief explicitly references it.

## 3. The four laws (project-wide, non-negotiable)

| Law | What it means |
|---|---|
| **Type_Safe always** | All data classes use `Type_Safe` from `osbot-utils`. No raw `str`/`int`/`dict` as fields. Use `Safe_Str__*`, `Safe_UInt__*`, etc. |
| **No mocks, no patches** | No `unittest.mock`, no `MagicMock`, no `@patch`, no `monkeypatch`. Use real objects, real temp dirs, real crypto, real in-memory transfer server. |
| **Behaviour preservation** | When a brief is in Villager-mode, identical inputs produce identical outputs. When a brief explicitly changes behaviour (e.g., Explorer-mode briefs B05/B06/B08), it says so. |
| **No `__init__.py` under `tests/`** | Test directories never have `__init__.py`. Conftest files are fine; init files are not. |

## 4. Pack-specific rules

- **No command-level back-compat** (decision 2). Renamed commands get a friendly error pointing at the new name; no aliases.
- **Vault-format changes ARE allowed** (decision 3). Newer vaults may need newer binaries. Migration command (B10) is the rekey-style fallback.
- **Default `clone` is full** (Git-compatible, decision 4).
- **`sgit inspect <…>`, `sgit dev <…>`, `sgit history <…>`, `sgit file <…>`, `sgit vault <…>`, `sgit branch <…>`, `sgit check <…>`, `sgit pki <…>`** are the namespaces. Top level is primitives only.
- **Context-aware visibility** is a thing (decision 9). Inside a vault hides clone family; outside hides commit/push/pull. See design D3.
- **Workflow framework** (decision 10). Steps are Type_Safe. Workspace at `.sg_vault/work/<workflow-id>/`.

## 5. The execution loop (per brief)

```
1. Read the brief in full.
2. Read the design docs it references.
3. Read your role file + CLAUDE.md.
4. Restate the goal back to Dinis in one sentence. If you can't,
   re-read.
5. Plan with TodoWrite — one todo per acceptance criterion.
6. Execute one todo at a time. Mark complete as you go.
7. Run the verification commands the brief specifies.
8. Commit + push (with `git pull --rebase` first to integrate
   parallel sessions). Use the commit message template.
9. Return the closeout summary the brief asks for.
```

If you get stuck, **escalate** — do not paper over.

## 6. Sequencing reminder

```
B01 instrumentation tools   ← Phase 0 — runs first
        │
        ├─→ B07 diagnose       (after B01)
        │
B02, B03, B04 CLI restructure   (independent of B01)
        │
B05 workflow framework  (Explorer-led)
        │
B06 apply workflow to clone  (after B05)
        │
B08 server clone packs  (Explorer-led; after B07 + B06)
        │
B09 per-mode clone impl  (after B03 + B06 + B08)
        │
B10 migration command  (after B08)
        │
B11 push/pull/fetch  (after B06 + B08)
```

Multiple agents can run in parallel where the graph permits. Do **not** start a brief whose prerequisites aren't merged.

## 7. Test-infrastructure context (already in place)

Phase A + Phase B work from the v0.10.30 sprint produced:

- 86% coverage, 2,105 tests, ~71s combined CI parallel.
- Shared fixtures (F1–F6) under `tests/unit/`'s `conftest.py`.
- `pytest-xdist` in dev deps. CI runs two passes: `-n auto -m "not no_parallel"` then `-m no_parallel`.

When you add new tests, design them to run under `-n auto`. If they can't, add the `@pytest.mark.no_parallel` marker with a documented reason.

## 8. Common patterns

### Type_Safe class skeleton

```python
from osbot_utils.type_safe.Type_Safe import Type_Safe

class Schema__Step__Clone__Walk_Trees__Output(Type_Safe):
    visited_tree_ids : list[Safe_Str__Tree_Id]
    bytes_downloaded : Safe_UInt
    duration_ms      : Safe_UInt
```

### Round-trip invariant test

```python
def test_round_trip(self):
    obj = Schema__Step__Clone__Walk_Trees__Output(
        visited_tree_ids = ['t1', 't2'],
        bytes_downloaded = 1234,
        duration_ms      = 56,
    )
    assert obj.from_json(obj.json()).json() == obj.json()
```

### Running tests

```
pytest tests/unit/ -q
pytest tests/unit/ -n auto -q
pytest tests/unit/<path>/test_<x>.py -q
pytest tests/unit/ --cov=sgit_ai
```

Integration tests use the Python 3.12 venv per `CLAUDE.md`:
```
/tmp/sgit-ai-venv-312/bin/python -m pytest tests/integration/ -v
```

## 9. Git practice

- Each brief specifies its own commit message template.
- Commit per logical unit; push periodically.
- Before push: `git pull --rebase origin <branch>`.
- Never force-push, never rewrite shared history, never `--no-verify`.

## 10. Where things live

```
sgit_ai/
├── api/           HTTP API layer (Vault__API, API__Transfer)
├── cli/           CLI entry + per-namespace handlers
│   ├── dev/       NEW (per B01) — dev/perf tools
│   └── workflow/  NEW (per B05) — workflow CLI
├── crypto/        Vault__Crypto, encrypt_deterministic, KDF
├── migrations/    NEW (per B10) — vault migrations
├── objects/       Vault__Sub_Tree, Vault__Ref_Manager
├── pki/           PKI__Key_Store, PKI__Keyring
├── safe_types/    Safe_Str__*, Safe_UInt__*, Enum__*
├── schemas/       Schema__* Type_Safe data classes
│   └── workflow/  NEW (per B05) — workflow schemas
├── secrets/       passphrase / vault-key
├── sync/          Vault__Sync (slowly being decomposed)
├── transfer/      in-memory transfer server, archive
└── workflow/      NEW (per B05) — Step / Workflow / Workspace primitives
    ├── shared/    shared step library (per B11)
    └── clone/     clone-specific steps (per B06)

tests/
├── unit/        runs in default `pytest tests/unit/`
└── integration/ needs Python 3.12 venv

team/villager/
├── CLAUDE.md
├── v0.11__clone-perf-strategy.md           the strategy doc
└── v0.11.x__perf-brief-pack/               THIS PACK
    ├── 00__index.md
    ├── 01__sprint-overview.md
    ├── design__01..05__*.md
    ├── brief__01..11__*.md
    ├── changes__*.md                       (produced by some briefs)
    └── sonnet__onboarding.md               (this file)
```

## 11. Things that will look weird but are correct

- The `_version.py` says `v0.1.0`. Version file lags.
- `Vault__Sync.py` is huge (2,986 LOC). Brief B11 + a future v0.12 refactor split it.
- Default clone is **full** — slow, but Git-compatible. Faster modes are explicit (`clone-branch`, etc.).
- `clone_mode.json` stores `read_key` in plaintext. **Per Dinis, intentional.**
- `sgit rekey` prints the new vault_key on stdout. **Per Dinis, intentional UX.**
- The current Phase-4 tree walk visits every commit's root — the case-study vault has 2,375 trees serving 165 files. Server packs (B08) are the fix.

## 12. Escalation

- **Architectural / boundary questions** → flag in the closeout summary; Dinis routes.
- **Crypto / security questions** → flag for AppSec.
- **CI / test-infra issues** → flag for DevOps.
- **Test-quality questions** → flag for QA.
- **"Should we redesign X?"** → escalate. Many briefs are explicitly Explorer-mode (B05, B06, B08) — those welcome design changes within the brief's scope.

## 13. Five sentences you should be able to say after onboarding

1. "I am working on the SGit-AI CLI v0.11.x → v0.12 sprint."
2. "I am executing brief BNN, owned by the X role."
3. "My acceptance criteria are A, B, C; my deliverables are D, E."
4. "I will not introduce mocks, raw primitives in Type_Safe classes, `__init__.py` files in `tests/`, or unintended behaviour changes."
5. "If I get stuck or find that the brief's premise is wrong, I escalate."

Welcome. Now read your brief.
