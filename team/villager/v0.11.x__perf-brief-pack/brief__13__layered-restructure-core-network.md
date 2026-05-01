# Brief B13 — Layered Restructure: Core + Network (the big one)

**Owner role:** **Architect** (split plan + boundary calls) + **Villager Dev** (mechanical splits + moves)
**Status:** BLOCKED until B12 lands.
**Prerequisites:** B12 (Storage layer) merged. B05 + B06 (workflow framework + clone workflow) merged.
**Estimated effort:** ~3–5 working days
**Touches:** `sgit_ai/sync/Vault__Sync.py` dissolves; `sgit_ai/api/` + `sgit_ai/transfer/` → `sgit_ai/network/`; `sgit_ai/pki/` → `sgit_ai/crypto/pki/`; many import updates; tests.

---

## Why this brief exists

The single biggest source-tree change in the v0.11.x → v0.12 sprint:
- **Vault__Sync.py (2,986 LOC) dissolves** into per-action workflows under `sgit_ai/core/actions/`. Each command (clone, push, pull, fetch, init, branch, merge, commit, …) gets its own folder with a `Workflow__<Command>` and its step classes.
- **`sgit_ai/api/` + `sgit_ai/transfer/`** consolidate under `sgit_ai/network/`.
- **`sgit_ai/pki/`** folds into `sgit_ai/crypto/pki/`.

This is the "if those layers are clean before PKI lands, PKI is tractable" moment.

---

## Required reading

1. This brief.
2. `design__06__layered-architecture.md` (the migration map).
3. `design__04__workflow-framework.md` (the workflows that land in `core/actions/`).
4. `team/villager/architect/v0.10.30/04__duplication-and-pipeline-shape.md` — the duplication hit-list from the v0.10.30 review. Subsumed by this brief.
5. `team/villager/dev/v0.10.30/06__file-size-and-class-seams.md` — the eight + four candidate sub-classes.
6. After B06 + B11 (deferred to B15) have landed: the existing workflows under `sgit_ai/workflow/`.

---

## Scope

### Phase 1 — Architect split plan

Produce: `team/villager/v0.11.x__perf-brief-pack/changes__core-network-split-plan.md`

For `Vault__Sync.py`, walk every public method. For each:
- Map to a `Workflow__<Command>` already implemented (B06 / B15) OR identify it as a Core action that needs its own workflow.
- New folder under `sgit_ai/core/actions/<command>/`.
- Public-method-list to expose at the `Workflow__<Command>` level.

For `api/` + `transfer/`:
- Final flat layout under `sgit_ai/network/`.
- `Vault__Backend__Local` and `Vault__Backend__API` placement.
- The in-memory transfer server moves under `sgit_ai/network/transfer/in_memory/`.

For `pki/`:
- Consolidate under `sgit_ai/crypto/pki/`.
- Rationale: PKI ops are crypto primitives.

Sequencing inside Phase 2: extract one action at a time, smallest first. Suggested order: `init` (smallest, simplest) → `commit` → `branch` ops → `clone` (already a workflow from B06; just relocate) → `push` (heaviest).

### Phase 2 — Mechanical extraction (action by action)

For each action:
1. Create `sgit_ai/core/actions/<command>/` folder.
2. Move the workflow + step classes into it (preserving git history with `git mv`).
3. Replace the corresponding method in `Vault__Sync.py` with a thin shim that calls into the new module.
4. Update imports across the codebase + tests.
5. Run full suite. Must pass.
6. Commit. Push.
7. Move to the next action.

Once every action is extracted, `Vault__Sync.py` is just a collection of shims. Remove the file. The shims can stay as a façade (`sgit_ai/core/Vault__Sync.py` as a deprecated import path) or be deleted entirely — Architect calls. Per decision 2 (no command-level back-compat), Architect should also consider whether to delete the shim layer outright.

### Phase 3 — Network consolidation

1. Create `sgit_ai/network/`.
2. `git mv sgit_ai/api/* sgit_ai/network/` (or refined per the split plan — the structure may want sub-folders like `network/api/`, `network/transfer/`).
3. `git mv sgit_ai/transfer/* sgit_ai/network/transfer/`.
4. Update imports.
5. Run suite.

### Phase 4 — PKI fold

1. Create `sgit_ai/crypto/pki/` (likely already exists if v0.10.30 brief 12 landed; check).
2. `git mv sgit_ai/pki/* sgit_ai/crypto/pki/`.
3. Update imports.
4. Run suite.

### Phase 5 — Layer-import test extension

The test from B12 already exists. Extend it for the new boundaries:
- `core/` imports only crypto, storage, network, workflow, safe_types, schemas, secrets.
- `network/` imports only crypto, safe_types, schemas.
- `crypto/` imports only safe_types, schemas (no `pki` upward dependency).

Run on every commit during this brief; no upward imports allowed.

### Phase 6 — Verify behaviour

After all phases:
- Full suite passes (2,105+ tests).
- Coverage delta non-negative.
- Phase B parallel CI shape ≤ 80s combined.
- All existing CLI commands produce identical output bytes for identical inputs.
- Layer-import test passes.

---

## Hard constraints

- **Behaviour preservation.** Identical inputs → identical outputs. Only structure changes.
- **`git mv` not delete-and-create.** Preserves blame for every moved file.
- **One commit per logical move.** Easy to review, easy to revert one move without unwinding all.
- **Layer-import test stays green at every commit boundary.**
- **No mocks introduced.**
- Coverage must not regress.
- Suite must pass under Phase B parallel CI shape after every commit.
- **Each action's behaviour is byte-equivalent to before.** Test a fixture vault clone/push/pull pre + post; assert identical `bare/` and identical CLI output.

---

## Acceptance criteria

- [ ] Architect split plan exists and is Dinis-approved.
- [ ] Every action in `Vault__Sync.py` extracted to `core/actions/<command>/`.
- [ ] `Vault__Sync.py` is empty / removed.
- [ ] `api/` + `transfer/` consolidated under `network/`.
- [ ] `pki/` consolidated under `crypto/pki/`.
- [ ] Layer-import test passes; covers all 5 layers.
- [ ] Suite ≥ 2,105 passing throughout.
- [ ] Per-action byte-equivalence assertion passes for clone, push, pull, fetch, commit, init.
- [ ] No file content changed beyond imports (audit via `git log --diff-filter=R` for pure renames).

---

## Out of scope

- Plugin system + read-only namespace migration — brief B14.
- Performance changes inside any action (still the same behaviour, just relocated).
- Server-side restructure (only client-side `sgit_ai/`).

---

## Deliverables

1. Architect split plan.
2. Per-action extracted modules under `sgit_ai/core/actions/<command>/`.
3. `sgit_ai/network/` consolidated layer.
4. `sgit_ai/crypto/pki/` consolidated layer.
5. Extended layer-import test.
6. Closeout note in `01__sprint-overview.md`.

---

## When done

Return a ≤ 350-word summary:
1. Action count extracted (one per Core command).
2. Final per-file LOC table for `core/actions/` and `network/`.
3. Layer-import test status.
4. Suite + coverage deltas.
5. Byte-equivalence assertion outcome.
6. Anything that surfaced about the workflow framework that needs B05 follow-up.
