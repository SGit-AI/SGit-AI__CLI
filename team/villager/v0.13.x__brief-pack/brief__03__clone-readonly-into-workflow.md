# Brief B03 — Fold `clone_read_only` + `clone_from_transfer` into Workflow__Clone

**Owner:** **Villager Dev**
**Status:** Ready. Was v0.12.x B06b / B18.
**Estimated effort:** ~1 day
**Touches:** `sgit_ai/core/actions/clone/Vault__Sync__Clone.py`, `sgit_ai/workflow/clone/`, schemas, tests.

---

## Why this brief exists

`Vault__Sync__Clone` currently has **four clone implementations**, only one of which is workflow-driven:

| Method | Workflow-driven? | Lines |
|---|:-:|---:|
| `_clone_with_keys` (full-clone path, B06 refactor) | ✅ | thin facade |
| `clone_read_only` (Brief 05's `--read-key`) | ❌ | ~180 |
| `clone_from_transfer` (SG/Send token-based clone) | ❌ | ~80 |
| `_clone_resolve_simple_token` (share-token branch) | ❌ | ~40 |

This means: **any improvement to the workflow steps (e.g. when B08 server packs eventually land) does NOT improve read-only / share-token / transfer clones.** B06's promise was "clone is workflow-driven" — reality is "the most common clone path is workflow-driven."

This brief closes that gap.

---

## Required reading

1. This brief.
2. `sgit_ai/core/actions/clone/Vault__Sync__Clone.py` — read in full (~450 LOC).
3. `sgit_ai/workflow/clone/` — the existing 10-step pipeline.
4. `sgit_ai/schemas/workflow/clone/Schema__Clone__State.py` — the cumulative state schema.
5. `team/villager/v0.12.x__perf-brief-pack/00c__opus-mid-sprint-review.md` §2.3 — the gap diagnosis.

---

## Scope

### Step 1 — Identify what's different per clone variant

For each of `clone_read_only`, `clone_from_transfer`, `_clone_resolve_simple_token`, list:
- Which steps are SAME as full clone (most are).
- Which steps are SKIPPED (e.g., read-only skips `create_clone_branch`).
- Which steps are NEW (e.g., transfer needs an `unpack_transfer` step).
- Which steps differ in INPUT (e.g., read-only reads keys from `clone_mode.json` instead of vault_key).

Produce a small table at the top of the new brief deliverable doc.

### Step 2 — Two design options (Architect picks)

**Option A: One workflow with mode flag.** Extend `Schema__Clone__State` with a `mode: Enum__Clone_Mode` field (full / read-only / transfer / share-token). Each step checks the mode and acts accordingly. Pros: one workflow, one set of steps. Cons: steps become flag-heavy.

**Option B: Multiple workflows sharing a step library.** `Workflow__Clone__Full`, `Workflow__Clone__ReadOnly`, `Workflow__Clone__Transfer` — each composes from a shared `sgit_ai/workflow/clone/_steps/` library. Pros: each workflow is clear and linear. Cons: more boilerplate.

**Recommend Option B.** Cleaner per-workflow logic; steps stay simple; matches the "workflow-driven" mental model. Architect to confirm before Dev starts.

### Step 3 — Implementation (assuming Option B)

1. Move shared steps into `sgit_ai/workflow/clone/_steps/` (no rename of step classes; just relocate).
2. Create `Workflow__Clone__ReadOnly` (likely 6–7 steps, reusing most of the full clone pipeline minus `create_clone_branch`).
3. Create `Workflow__Clone__Transfer` (4–5 steps; transfer-specific steps for unpacking the SG/Send envelope).
4. Refactor `Vault__Sync__Clone.clone_read_only()` and `.clone_from_transfer()` to invoke the new workflows via `Workflow__Runner`.
5. Delete the ~180 + ~80 lines of parallel logic from `Vault__Sync__Clone`.
6. Tests: end-to-end round-trip for each clone variant.
7. Register all three workflows in `sgit dev workflow list`.

### Step 4 — Behaviour preservation

This is critical. Each clone variant must produce **byte-identical output** vs the pre-refactor implementation:
- `bare/` directory contents byte-identical.
- Working copy file contents byte-identical.
- Local config / vault_key / clone_mode files byte-identical.
- CLI output (progress messages) within tolerance — workflow steps may produce different progress messages, but the user-visible result must match.

---

## Hard rules

- **Behaviour preservation per clone variant.** Run pre-refactor + post-refactor against the same vault; assert byte-identical output.
- **Type_Safe** — schemas, step classes, workflow classes.
- **No mocks** — use `Vault__Test_Env` + in-memory transfer server.
- **Coverage must not regress.**
- **Suite must pass under `-n auto`** at every commit.

---

## Acceptance criteria

- [ ] Architect chose Option A or B (recommend B).
- [ ] Three workflows: `Workflow__Clone` (full), `Workflow__Clone__ReadOnly`, `Workflow__Clone__Transfer`.
- [ ] Shared step library at `sgit_ai/workflow/clone/_steps/` (or equivalent).
- [ ] `Vault__Sync__Clone` reduces by ~250+ LOC (the parallel implementations are gone).
- [ ] Each clone variant has an end-to-end round-trip test using `Vault__Test_Env`.
- [ ] Byte-identical pre-refactor / post-refactor assertion test for each variant.
- [ ] Three workflows visible in `sgit dev workflow list`.
- [ ] Suite ≥ 3,068 + ~10 new tests passing.
- [ ] Coverage delta non-negative.

---

## When done

Return a ≤ 250-word summary:
1. Option chosen (A or B) + rationale if different from recommendation.
2. Workflows shipped (3) + their step counts.
3. LOC removed from `Vault__Sync__Clone`.
4. Byte-identical assertion outcome per variant.
5. Coverage + test count delta.
