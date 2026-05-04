# Brief B13 — Layered Restructure: Core + Network

**Owner role:** **Architect** (split plan + boundary calls) + **Villager Dev** (mechanical relocation)
**Status:** BLOCKED until B12 lands.
**Prerequisites:** B12 (Storage layer) merged. B05 + B06 (workflow framework + clone workflow) merged.
**Estimated effort:** ~2–3 working days (substantially smaller than originally scoped — see post-v0.12.0 note)
**Touches:** **relocate** the 12 `Vault__Sync__*.py` sub-classes from `sgit_ai/sync/` to `sgit_ai/core/actions/<command>/`; `sgit_ai/api/` + `sgit_ai/transfer/` → `sgit_ai/network/`; `sgit_ai/pki/` → `sgit_ai/crypto/pki/`; many import updates; tests.

---

## Post-v0.12.0 update (read first)

This brief was originally framed as **"dissolve `Vault__Sync.py`
(3,032 LOC monolith) into `core/actions/<command>/`"** — a multi-day,
high-risk extraction.

**That work already happened in v0.12.0** (B22 of v0.10.30). The
12 sub-classes (`Vault__Sync__Base`, `Commit`, `Status`, `Pull`, `Push`,
`Clone`, `Admin`, `Lifecycle`, `Branch_Ops`, `GC_Ops`, `Sparse`, `Fsck`)
already exist under `sgit_ai/sync/`. `Vault__Sync.py` is a 258-line
facade.

So **B13's scope shrinks to two coherent pieces of work**:

1. **Relocate the 12 sub-classes** into `sgit_ai/core/actions/<command>/`
   — primarily a `git mv` exercise + import updates. Each sub-class
   moves as one commit; existing tests transfer unchanged. **Per-sub-class risk is low.**
2. **Consolidate `api/` + `transfer/` under `network/`; fold `pki/`
   under `crypto/pki/`.** Independent of the sub-class moves.

The Phase-1 Architect plan still produces a move map; it's just a much
shorter map than the original "dissolve a monolith" framing.

**Effort dropped from "3–5 days" to "~2–3 days".**

## Why this brief exists

The single biggest source-tree change in the v0.12.x sprint:
- **Relocate the 12 `Vault__Sync__*.py` sub-classes** into per-command folders under `sgit_ai/core/actions/`. Each sub-class becomes its own folder with the workflow + step classes (`core/actions/clone/`, `core/actions/push/`, …).
- **`sgit_ai/api/` + `sgit_ai/transfer/`** consolidate under `sgit_ai/network/`.
- **`sgit_ai/pki/`** folds into `sgit_ai/crypto/pki/`.

This is the "if those layers are clean before PKI lands, PKI is tractable" moment.

---

## Required reading

1. This brief.
2. `design__06__layered-architecture.md` (the migration map).
3. `design__04__workflow-framework.md` (the workflows that land in `core/actions/`).
4. The current `sgit_ai/sync/` directory listing — see the 12 `Vault__Sync__*.py` sub-classes.
5. The B22 v0.10.30 split plan (`team/villager/architect/v0.10.30__vault-sync-split-plan.md`) and addendum — explains why each sub-class lives where it does today.
6. After B06 has landed: the existing workflows under `sgit_ai/workflow/`.

---

## Scope

### Phase 1 — Architect relocation plan

Produce: `team/villager/v0.12.x__perf-brief-pack/changes__core-network-relocation-plan.md`

For each of the 12 `Vault__Sync__*.py` sub-classes (already separate
files post-v0.12.0), specify:
- New path under `sgit_ai/core/actions/<command>/`.
- Whether the sub-class becomes a `Workflow__<Command>` immediately
  (if its workflow shipped via B06 / B15) or stays as a Type_Safe
  class until its workflow lands.
- Tests file location (parallel move under `tests/unit/core/actions/<command>/`).

Suggested per-sub-class destinations:

| Current file | New location |
|---|---|
| `sgit_ai/sync/Vault__Sync__Base.py` | `sgit_ai/core/Vault__Sync__Base.py` (shared base; not under any single action) |
| `sgit_ai/sync/Vault__Sync__Commit.py` | `sgit_ai/core/actions/commit/` |
| `sgit_ai/sync/Vault__Sync__Status.py` | `sgit_ai/core/actions/status/` |
| `sgit_ai/sync/Vault__Sync__Pull.py` | `sgit_ai/core/actions/pull/` |
| `sgit_ai/sync/Vault__Sync__Push.py` | `sgit_ai/core/actions/push/` |
| `sgit_ai/sync/Vault__Sync__Clone.py` | `sgit_ai/core/actions/clone/` |
| `sgit_ai/sync/Vault__Sync__Admin.py` | `sgit_ai/core/actions/admin/` (or split further per Architect's call) |
| `sgit_ai/sync/Vault__Sync__Lifecycle.py` | `sgit_ai/core/actions/lifecycle/` |
| `sgit_ai/sync/Vault__Sync__Branch_Ops.py` | `sgit_ai/core/actions/branch/` |
| `sgit_ai/sync/Vault__Sync__GC_Ops.py` | `sgit_ai/core/actions/gc/` |
| `sgit_ai/sync/Vault__Sync__Sparse.py` | `sgit_ai/core/actions/sparse/` |
| `sgit_ai/sync/Vault__Sync__Fsck.py` | `sgit_ai/core/actions/fsck/` |
| `sgit_ai/sync/Vault__Sync.py` (facade) | `sgit_ai/core/Vault__Sync.py` (or `sgit_ai/sync/` stays as a shim that re-exports) |

For `api/` + `transfer/`:
- Final flat layout under `sgit_ai/network/`.
- `Vault__Backend__Local` and `Vault__Backend__API` placement.
- The in-memory transfer server moves under `sgit_ai/network/transfer/in_memory/`.

For `pki/`:
- Consolidate under `sgit_ai/crypto/pki/`.
- Rationale: PKI ops are crypto primitives.

Sequencing inside Phase 2: smallest move first. Suggested order:
`Branch_Ops` / `GC_Ops` (smallest) → `Sparse` / `Fsck` → `Status` /
`Commit` / `Lifecycle` → `Admin` → `Pull` / `Push` (heaviest) →
`Clone` (last, since B06's `Workflow__Clone` may have already landed
there). `Vault__Sync__Base` moves once, used by all the others.

### Phase 2 — Mechanical relocation (sub-class by sub-class)

For each sub-class:
1. Create `sgit_ai/core/actions/<command>/` folder.
2. `git mv sgit_ai/sync/Vault__Sync__<Command>.py sgit_ai/core/actions/<command>/Vault__Sync__<Command>.py` — preserves git history.
3. Update imports inside the moved file (e.g., `from sgit_ai.sync.Vault__Sync__Base` → `from sgit_ai.core.Vault__Sync__Base`).
4. Update the facade (`Vault__Sync.py`) to import from the new location.
5. Update test imports (`tests/unit/sync/test_Vault__Sync__<Command>*.py` → `tests/unit/core/actions/<command>/test_<…>.py` — also via `git mv`).
6. Run full suite. Must pass.
7. Commit. Push.
8. Move to the next sub-class.

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
