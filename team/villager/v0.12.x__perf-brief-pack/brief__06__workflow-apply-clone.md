# Brief B06 — Apply Workflow Framework to `clone`

**Owner role:** **Villager Dev** (Explorer-blessed for the granularity choice)
**Status:** BLOCKED until brief B05 lands. Best after Brief 23 (E3 carry-forward) **or fold E3 in**.
**Prerequisites:** Brief B05 merged. Brief 23 E3 (Vault__Graph_Walk) folded in or already shipped.
**Estimated effort:** ~8–12 hours
**Touches:** `sgit_ai/sync/Vault__Sync__Clone.py` (refactor `_clone_with_keys` into a Workflow), new step classes, schemas, tests.

---

## Post-v0.12.0 update (read first)

The v0.12.0 release (B22 of v0.10.30) split `Vault__Sync.py` into 12
sub-classes. The `_clone_with_keys` method is now in
`sgit_ai/sync/Vault__Sync__Clone.py`, NOT in `Vault__Sync.py`.

Implications for this brief:
- **Refactor target is `Vault__Sync__Clone._clone_with_keys`**, not
  `Vault__Sync.py:1276–1410`.
- The public `Vault__Sync.clone(...)` facade method is unchanged. Its
  delegation to `Vault__Sync__Clone` keeps working; the internal
  `_clone_with_keys` becomes a `Workflow__Clone` invocation.
- The 10-step decomposition below is unchanged.
- `Workflow__Clone` lands at `sgit_ai/workflow/clone/` initially.
  Relocates to `sgit_ai/core/actions/clone/` after brief B13 (Core+Network split).
- **Fold-in opportunity for Brief 23 E3 (`Vault__Graph_Walk`)**: the
  `Step__Clone__Walk_Trees` step is the natural extraction target for
  E3. **Recommendation: B06's `walk_trees` step IS the extraction of
  `Vault__Graph_Walk`.** Reuse the same extracted class for
  `Workflow__Pull._fetch_missing_objects` later (brief B15). This
  saves a separate B23-E3 brief execution.

## Why this brief exists

Brief B05 ships the workflow framework. Brief B06 makes the first **real** workflow: refactor the existing `_clone_with_keys` (now in `sgit_ai/sync/Vault__Sync__Clone.py`) into a `Workflow__Clone` composed of `Step__Clone__*` classes.

This is the validating proof the framework is usable. Once clone is workflow-driven, the same pattern applies to push, pull, fetch (brief B15).

---

## Required reading

1. This brief.
2. `design__04__workflow-framework.md` (the design).
3. `team/villager/v0.12.x__perf-brief-pack/changes__workflow-framework-spec.md` (Architect freeze from B05).
4. `sgit_ai/sync/Vault__Sync__Clone.py` `_clone_with_keys` (read in full).
5. `team/villager/dev/v0.10.30__brief-pack/23__e3-e4-bfs-walk-and-blob-download-dedup.md` (E3 design — fold into this brief's `walk_trees` step).
6. `team/villager/dev/dev__ROLE.md` — behaviour preservation rule.

---

## Scope

### Step 1 — Step inventory (sketch in design D4 §"Granularity")

10 candidate steps:

| # | Step | Input | Output |
|---|---|---|---|
| 1 | `derive_keys` | vault_key | vault_id, read_key, write_key, branch_index_file_id |
| 2 | `check_directory` | directory | directory_status |
| 3 | `download_index` | vault_id, branch_index_file_id | branch_index |
| 4 | `download_branch_meta` | branch_index | branch_metadata |
| 5 | `walk_commits` | head_ref_id | commit_ids[], root_tree_ids[] |
| 6 | `walk_trees` | root_tree_ids | visited_tree_ids[] |
| 7 | `download_blobs` | head_tree_id | blob_count, bytes_downloaded |
| 8 | `create_clone_branch` | branch_metadata | clone_branch |
| 9 | `extract_working_copy` | head_tree_id, blobs | files_written |
| 10 | `setup_local_config` | clone_state | local_config |

Each step gets:
- A class `Step__Clone__<Name>` extending `Step`.
- Input schema `Schema__Step__Clone__<Name>__Input`.
- Output schema `Schema__Step__Clone__<Name>__Output`.
- `execute()` method.

### Step 2 — `Workflow__Clone`

Class composing the 10 steps in order. Lives under `sgit_ai/workflow/clone/` initially; relocates to `sgit_ai/core/actions/clone/` after brief B13 (Core+Network split) lands.

### Step 3 — Refactor `_clone_with_keys`

Replace the body of `_clone_with_keys` with:

```python
def _clone_with_keys(self, vault_key, directory, on_progress=None, sparse=False):
    workflow  = Workflow__Clone()
    workspace = Workflow__Workspace.create(workflow, vault_path=...)
    input     = Schema__Workflow__Clone__Input(vault_key=vault_key,
                                               directory=directory,
                                               sparse=sparse)
    runner = Workflow__Runner(progress_callback=on_progress)
    output = runner.execute(workflow, input, workspace)
    return output.json()
```

The existing public API of `_clone_with_keys` stays identical (input args, return shape). All consumers (CLI, tests) continue to work without changes.

### Step 4 — Behaviour preservation

This is critical. Per Villager Dev role: identical inputs → identical outputs. After refactor:
- All existing clone tests must pass without modification.
- The `on_progress` callback must fire at the same logical points (each step boundary corresponds to a progress event).
- Output bytes must match for the same vault.
- Performance must not regress (or only marginally — workflow overhead < 200ms total acceptable).

Verify behaviour preservation:
1. Run the full clone test suite before and after. Diff outputs.
2. Run `_clone_with_keys` against a fixture vault, capture `bare/` directory; do the same after; assert byte-identical.

### Step 5 — Tests

- Unit tests for each step class (10 steps × 2–3 tests = ~25 tests).
- Workflow-level tests: full-clone happy path, resume-from-step-N, abort-on-step-N.
- Behaviour-preservation regression test: identical-output assertion.

### Step 6 — Closeout

Each step's `Schema__Step__Clone__<Name>__Output` is now a stable contract that brief B15 (push/pull/fetch generalisation) and brief B09 (per-mode clones) will compose against.

---

## Hard constraints

- **Behaviour preservation is non-negotiable.** Identical bytes for identical inputs.
- **Type_Safe** for every step + every schema.
- **No mocks.**
- **No `__init__.py` under `tests/`.**
- **Round-trip invariant** for every step input/output schema.
- **Workflow overhead** (framework cost beyond raw work) must be < 200ms total per clone.
- Suite must pass under Phase B parallel CI shape.
- Coverage delta non-negative.

---

## Acceptance criteria

- [ ] 10 step classes implemented.
- [ ] `Workflow__Clone` composes them.
- [ ] `_clone_with_keys` refactored to use the workflow.
- [ ] All existing clone tests pass without modification.
- [ ] Byte-identical output assertion against a fixture vault passes.
- [ ] At least 25 step-level tests + 3 workflow-level tests.
- [ ] Coverage on new step/workflow code ≥ 85%.
- [ ] Suite ≥ existing test count + N passing.
- [ ] `sgit dev workflow show clone` lists the 10 steps with their schemas.
- [ ] `sgit dev workflow trace clone <vault-key> <dir>` runs the clone with verbose per-step output.

---

## Out of scope

- Performance fixes inside the steps (still single-threaded BFS for trees, no packs yet — those land in brief B08).
- Per-mode clones (brief B09).
- Push / pull / fetch refactor (brief B15).

---

## Deliverables

1. New step classes under `sgit_ai/workflow/clone/`.
2. New schemas under `sgit_ai/schemas/workflow/clone/`.
3. Refactored `_clone_with_keys`.
4. Tests.
5. Closeout note in sprint overview.

---

## When done

Return a ≤ 300-word summary:
1. Step count + their public output schemas.
2. Behaviour preservation: confirmed byte-identical? performance delta?
3. Test count + coverage delta.
4. Workflow runtime overhead measured.
5. Anything that surfaced about the framework that should be reflected back into B05's design (escalate).
