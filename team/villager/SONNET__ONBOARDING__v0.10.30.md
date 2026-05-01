# Sonnet Onboarding — v0.10.30 Villager Brief-Pack Execution

You are a fresh Claude Code Sonnet session starting work on the
**SGit-AI CLI** repository. The Villager team has just completed a
multi-angle deep analysis (Architect / Dev / AppSec) of the v0.10.30
sprint and produced a 13-brief deferred queue plus 4 already-executed
test-infrastructure briefs. **Your job is to execute briefs from the
queue.**

You did not run the analysis. The team that wrote the briefs cannot
hold context for you. **This document is your full onboarding —
read it first.**

---

## 1. The 60-second context

- **Repo:** `sgit-ai/sgit-ai__cli` (Python CLI; encrypted-vault sync;
  zero-knowledge crypto).
- **Branch you work on:** `claude/villager-multi-agent-setup-sUBO6`
  (already synced with `origin/dev`).
- **Architecture:** `osbot_utils.type_safe` (no Pydantic), no mocks,
  no boto3, AES-256-GCM + HKDF + PBKDF2.
- **You will:** pick a brief from `team/villager/dev/v0.10.30__brief-pack/`,
  read it in full, execute it, commit + push, and report.
- **You will NOT:** make architectural decisions, add features, change
  the vault format or CLI contract, work on more than one brief per
  session unless told to.

---

## 2. Required reading order (do not skip)

Read in this order. Stop when you have enough context for your brief —
you don't need to read everything.

1. **The brief you are executing** — pointed to by Dinis in his message,
   e.g. `team/villager/dev/v0.10.30__brief-pack/10__hardening-chmod-0600.md`.
   Read in full, twice.
2. **Your role file** — every brief lists an "Owner role". Read its
   `*__ROLE.md`:
   - `team/villager/architect/architect__ROLE.md`
   - `team/villager/dev/dev__ROLE.md`
   - `team/villager/appsec/appsec__ROLE.md`
   - `team/villager/qa/qa__ROLE.md`
   - `team/villager/devops/devops__ROLE.md`
3. **Project rules:**
   - `CLAUDE.md` (repo root) — Type_Safe rules, no-mocks rule, naming
     conventions, integration-test-venv setup.
   - `team/villager/CLAUDE.md` — Villager team mission, methodology,
     working agreements.
4. **Phase context (skim, don't deep-read):**
   - `team/villager/v0.10.30__cross-team-summary.md` — the deep
     analysis. Read §§ 1–4 only unless the brief pulls you elsewhere.
   - `team/villager/v0.10.30__next-phase-plan.md` — the locked-in
     decisions and sequencing.
5. **Brief-pack index:**
   - `team/villager/dev/v0.10.30__brief-pack/00__index.md` — see
     what's done, what depends on what.
6. **Specific findings** the brief points you at (it will name them
   explicitly — e.g. "AppSec finding F03"). Read only those, not all 32
   findings.

**Do not** read the full deep-analysis output (32 finding files) up
front. The brief tells you what's relevant.

---

## 3. The four laws (project-wide, non-negotiable)

These are everywhere in the codebase rules. Internalise them now.

| Law | What it means | Where it bites |
|---|---|---|
| **Type_Safe always** | All data classes use `Type_Safe` from `osbot-utils`. No Pydantic. Use `Safe_Str__*`, `Safe_UInt__*`, etc. — never raw `str`/`int`/`dict` as fields. | Schemas, helper classes, anywhere data is modelled. |
| **No mocks, no patches** | No `unittest.mock`, no `MagicMock`, no `@patch`, no `monkeypatch`. Use real objects, real temp dirs, real crypto, real in-memory transfer server. | Every test you write. |
| **Behaviour preservation** | Villager mode is hardening, not redesign. Refactorings must produce identical outputs for identical inputs. If you'd change a CLI command's output, stop and escalate. | Every refactor. |
| **No `__init__.py` under `tests/`** | Test directories never have `__init__.py`. Conftest files are fine; init files are not. | When adding a new test directory. |

If a brief seems to ask you to violate one of these, re-read the brief.
If it really does, escalate to Dinis before acting.

---

## 4. The execution loop (per brief)

```
1. Read the brief in full.
2. Read the role file + CLAUDE.md.
3. Read the specific findings the brief points at.
4. Restate the goal back to yourself in one sentence. If you can't,
   re-read.
5. Plan with TodoWrite — one todo per brief acceptance criterion.
6. Execute one todo at a time. Mark complete as you go.
7. Run the verification commands the brief specifies.
8. Commit + push. Use the commit message template the brief provides.
9. Return the closeout summary the brief asks for.
```

If you get stuck, **escalate** — do not paper over. The brief will
usually tell you who to escalate to (Architect, AppSec, etc.).

---

## 5. Suggested execution order for the deferred queue

Per `team/villager/dev/v0.10.30__brief-pack/00__index.md`. Numeric
order = execution order. **Do not skip ahead.**

```
10–13  hardening pack       (small, parallelizable — assign to separate sessions)
14     bug fix              (real correctness bug — early)
15–17  schemas              (after 14)
18     coverage push        (independent; can run in parallel)
19     mock cleanup         (best after 18)
20     crypto determinism   (independent; can run in parallel with 18 or 19)
21     mutation matrix exec (after 12, 13, 15, 18, 20)
22     Vault__Sync.py split (LAST — multi-day; only after all others)
```

Briefs 10–13 (hardening) are small and independent — Dinis may launch
multiple sessions in parallel, one per brief. If you receive one of
those, do NOT spread into another brief's scope.

---

## 6. Test-infrastructure context (already in place)

Phase A + Phase B briefs are done. The current state:

- Suite runs **2,105 tests** clean, **86% coverage**, **~71s combined
  CI parallel** (gate ≤ 80s).
- Shared fixtures (F1–F6) are in place under `tests/unit/`'s
  `conftest.py` files. **Use them when your brief touches the
  affected files** (PKI, Vault__Bare, Probe, Simple_Token).
- `pytest-xdist` is in dev deps. CI runs two passes: `-n auto -m "not
  no_parallel"` then `-m no_parallel`.
- No `no_parallel` markers in use today (zero tests need serial).

When you add new tests, design them to run cleanly under `-n auto`.
If you absolutely cannot, add the `@pytest.mark.no_parallel` marker
and document why.

---

## 7. Common patterns you will need

### Running tests

```
pytest tests/unit/ -q                       # full suite, serial
pytest tests/unit/ -n auto -q              # parallel
pytest tests/unit/<path>/test_<x>.py -q    # one file
pytest tests/unit/ --cov=sgit_ai           # with coverage
```

Integration tests need the Python 3.12 venv per `CLAUDE.md`:

```
/tmp/sgit-ai-venv-312/bin/python -m pytest tests/integration/ -v
```

### Type_Safe class skeleton

```python
from osbot_utils.type_safe.Type_Safe import Type_Safe

class Schema__Push_State(Type_Safe):
    vault_id  : Safe_Str__Vault_Id  = None
    blobs_done: list[Safe_Str__Blob_Id]
    started_at: Safe_Str__ISO_Timestamp = None
```

No raw primitives. Collections via type annotation only.

### Safe_* type skeleton

```python
import re
from osbot_utils.type_safe.primitives.core.Safe_Str import Safe_Str

class Safe_Str__Edit_Token(Safe_Str):
    regex           = re.compile(r'[^a-zA-Z0-9\-_]')
    max_length      = 256
    allow_empty     = False
    trim_whitespace = True
```

### Round-trip invariant test

```python
def test_round_trip(self):
    obj = Schema__Push_State(vault_id='v1', started_at='2026-05-01T...')
    assert Schema__Push_State.from_json(obj.json()).json() == obj.json()
```

---

## 8. Git practice

Each brief specifies its own commit message. Generally:

- Commit periodically (per logical unit, not at the end).
- Push after each commit: `git push origin claude/villager-multi-agent-setup-sUBO6`.
- Before push: `git pull --rebase origin claude/villager-multi-agent-setup-sUBO6`
  (other Sonnet sessions may have landed work in parallel).
- Never force-push, never rewrite shared history, never `--no-verify`.

---

## 9. Where things live

```
sgit_ai/                            source code
├── api/         ← API layer (Vault__API, API__Transfer, …)
├── cli/         ← CLI handlers (CLI__Vault, CLI__PKI, …) + main entry
├── crypto/      ← Vault__Crypto, encrypt_deterministic, KDF
├── objects/     ← Vault__Sub_Tree, Vault__Ref_Manager
├── pki/         ← PKI__Key_Store, PKI__Keyring
├── safe_types/  ← Safe_Str__*, Safe_UInt__*, Enum__*
├── schemas/     ← Schema__* Type_Safe data classes
├── secrets/     ← passphrase / vault-key handling
├── sync/        ← Vault__Sync (the 2,986-LOC monster, brief 22 splits it)
└── transfer/    ← in-memory transfer server, archive

tests/
├── unit/        ← runs in default `pytest tests/unit/`
└── integration/ ← needs Python 3.12 venv

team/villager/
├── CLAUDE.md
├── v0.10.30__cross-team-summary.md
├── v0.10.30__next-phase-plan.md
├── architect/   ← role + findings + plans
├── dev/         ← role + findings + brief-pack
├── appsec/      ← role + findings + mutation matrix
├── qa/          ← role + coverage baselines
└── devops/      ← role + runtime baselines + parallelization report
```

---

## 10. What to do RIGHT NOW

1. Identify the brief Dinis pointed you at (he will name it explicitly,
   e.g. "do brief 10").
2. Read the brief file in full.
3. Read the role file the brief names.
4. Read `CLAUDE.md` and `team/villager/CLAUDE.md`.
5. Read the specific findings the brief points at.
6. Make a TodoWrite plan from the brief's acceptance criteria.
7. Restate the goal in one sentence to Dinis. If you got it right, he
   says "go" and you proceed. If not, he corrects.
8. Execute. Commit + push. Return the closeout summary.

**Do not start coding before step 7.** Showing the plan first is the
contract.

---

## 11. Things that will look weird but are correct

- The `_version.py` says `v0.1.0` even though we call this the
  "v0.10.30 sprint". The version file lags semantics.
- `Vault__Sync.py` is huge. Yes, we know. Brief 22 splits it.
- 553 mock-pattern lines exist despite the no-mocks rule. Brief 19
  attacks the carryover.
- Coverage is 86%. The role-doc target of 95% is a v0.11.x ambition.
- `clone_mode.json` stores `read_key` in plaintext. **Per Dinis,
  intentional** (it's in `.sg_vault/local/`, treated like other local
  secrets). Do not "fix" this.
- `sgit rekey` prints the new vault_key on stdout. **Per Dinis,
  intentional UX.** Do not "fix" this either.

---

## 12. Escalation contacts

- **Architectural / boundary questions** → flag in the closeout
  summary; Dinis routes to Architect.
- **Crypto / security questions** → flag for AppSec.
- **CI / test-infra issues** → flag for DevOps.
- **Test-quality questions** → flag for QA.
- **"Should we redesign X?"** → STOP. Send back to Explorer via Dinis.
  Villager mode does not redesign.

---

## 13. The five sentences you should be able to say after onboarding

If you can say all five truthfully, you're onboarded. If not, re-read
sections 1–4.

1. "I am working on the SGit-AI CLI in Villager mode — hardening, not
   redesign."
2. "I am executing brief NN, which is owned by the Villager X role."
3. "My acceptance criteria are A, B, C; my deliverables are D, E."
4. "I will not introduce mocks, raw primitives in Type_Safe classes,
   `__init__.py` files in `tests/`, or behaviour changes."
5. "If I get stuck or find that the brief's premise is wrong, I
   escalate."

Welcome. Now read your brief.
