# Brief B05 — Workflow Framework (Implementation)

**Owner role:** **Explorer Architect** (framework design freeze) + **Villager Dev** (mechanical implementation)
**Status:** Ready to execute. Independent of B01–B04.
**Prerequisites:** Architect signs off on the framework design (mostly captured in `design__04`).
**Estimated effort:** ~12–20 hours (one or two working days)
**Touches:** new package `sgit_ai/workflow/`, schemas under `sgit_ai/schemas/workflow/`, CLI under `sgit_ai/cli/dev/workflow/`, tests under `tests/unit/workflow/`.

---

## Why this brief exists

Per `design__04__workflow-framework.md` + decision 10: introduce `Step` and `Workflow` Type_Safe primitives that let key commands be expressed as ordered, idempotent, individually-inspectable steps. State persists to `.sg_vault/work/<workflow-id>/`. This is a **new framework**, not a refactor — clearly **Explorer territory** for design, with Villager Dev doing the implementation under Explorer sign-off.

---

## Required reading

1. This brief.
2. `design__04__workflow-framework.md` (the design — read in full).
3. `team/villager/architect/architect__ROLE.md` and `team/villager/dev/dev__ROLE.md`.
4. `team/explorer/architect/ROLE.md` if it exists (Explorer Architect role).
5. `CLAUDE.md` Type_Safe + Safe_* + schema patterns.

---

## Scope

### Step 1 — Architect freeze

Before any code, the Explorer Architect produces a freeze doc:

`team/villager/v0.11.x__perf-brief-pack/changes__workflow-framework-spec.md`

Locks in:
- Final API for `Step` and `Workflow` base classes (method signatures, optional hooks).
- `.sg_vault/work/<workflow-id>/` exact filename convention (digit padding, separator chars).
- Workspace lifetime decision (clean-on-success default per design D4 recommendation, or override).
- Granularity policy (suggested 5–15 steps per command).
- Step-output schema versioning (semver per workflow, refuse cross-version resume).
- Shared step library policy (cross-workflow `Step__*` classes — yes/no and where they live).
- Atomic-write protocol (write-temp + rename).

Dinis reviews. Then Dev implements.

### Step 2 — Core types

Implement under `sgit_ai/workflow/`:

- `Step` — Type_Safe base class with `name`, `input_schema`, `output_schema`, `execute()`, `is_done()`, `validate_input()`, `validate_output()`.
- `Workflow` — Type_Safe base class with `name`, `version`, `steps: list[type[Step]]`, `execute()`.
- `Workflow__Workspace` — Type_Safe class managing the on-disk workspace (`workspace_dir`, `gather_input_for(step)`, `persist_output(step, output)`, `final_output()`, `has_output_for(step)`).
- `Workflow__Manifest` — Type_Safe schema for the `workflow.json` summary file.
- `Workflow__Runner` — orchestrator that runs a `Workflow` against a `Workflow__Workspace`.

### Step 3 — Schemas

Under `sgit_ai/schemas/workflow/`:
- `Schema__Workflow__Manifest` — workflow name, version, step list with status + timing per step, started/completed timestamps.
- `Schema__Step__Status` — Enum for step status (pending / running / completed / failed / skipped).
- `Safe_Str__Workflow_Name`, `Safe_Str__Step_Name`, `Safe_Str__Work_Id`.
- Round-trip invariant test for each.

### Step 4 — `sgit dev workflow <…>` CLI

Under `sgit_ai/cli/dev/workflow/`:
- `list` — discover registered workflows by class introspection.
- `show <command>` — list steps + I/O schemas (pretty-print Type_Safe field types).
- `run <command> [--step <n>] [--work-id <id>]` — invoke runner.
- `resume <work-id>` — load workspace, continue.
- `inspect <work-id>` — pretty-print manifest + per-step output sizes.
- `trace <command>` — verbose invocation (every step output streamed to stdout).
- `gc [--older-than <duration>]` — clean up old workspaces.

### Step 5 — Tests

- One test per public method on `Step`, `Workflow`, `Workflow__Workspace`, `Workflow__Runner`.
- A "synthetic 3-step workflow" fixture that exercises happy path, resume-from-step-2, and abort-on-step-2-failure.
- Atomic-write crash test (use a deliberately failing step; verify workspace state is consistent post-crash).
- Cross-version resume test (refuses with friendly error).
- CLI tests under `tests/unit/cli/dev/test_CLI__Workflow.py`.

---

## Hard constraints

- **Type_Safe everywhere.** No raw `dict` / `str` / `int` fields in workspace, manifest, step types.
- **No mocks.** Use a real synthetic workflow fixture; real temp dirs.
- **Round-trip invariant** for every workflow / step / manifest schema.
- **Atomic writes.** Every persist is write-temp + rename. Never partial state.
- **No `__init__.py` under `tests/`.**
- Test suite must pass under Phase B parallel CI shape.
- Coverage on the new framework code ≥ 90% (it's foundational; high coverage matters).

---

## Acceptance criteria

- [ ] Architect freeze doc exists and is Dinis-approved before Dev starts.
- [ ] Core types implemented with full Type_Safe compliance.
- [ ] Schemas implemented with round-trip invariant tests.
- [ ] `sgit dev workflow <…>` subcommands work end-to-end against the synthetic fixture.
- [ ] At least 15 tests covering happy path, resume, abort, atomic-write, cross-version refusal.
- [ ] Coverage on new code ≥ 90%.
- [ ] Suite ≥ existing test count + N passing; overall coverage delta non-negative.
- [ ] No source change to existing main commands (clone/push/pull etc.) — that's brief B06.
- [ ] Closeout note appended to `team/villager/v0.11.x__perf-brief-pack/01__sprint-overview.md` referencing the new framework files.

---

## Out of scope

- Applying the framework to `clone` / `push` / `pull` / `fetch` (briefs B06, B11).
- Server-side pack consumption inside steps (brief B08 + B09).
- UI / progress bars for the workflow runner — basic stdout for now.
- Distributed / async workflow execution.

---

## Deliverables

1. Architect freeze doc.
2. Source under `sgit_ai/workflow/` and `sgit_ai/schemas/workflow/`.
3. CLI under `sgit_ai/cli/dev/workflow/`.
4. Tests.
5. Closeout note.

---

## When done

Return a ≤ 300-word summary:
1. Final API signatures for `Step` / `Workflow` / `Workflow__Workspace`.
2. Synthetic-fixture test count + coverage on new code.
3. Workspace lifetime + granularity decisions made.
4. Anything in the design that changed during implementation (escalate).
5. Confirmation that the framework is consumable by brief B06.
