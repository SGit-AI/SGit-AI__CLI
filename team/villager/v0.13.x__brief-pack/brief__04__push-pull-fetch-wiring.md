# Brief B04 — Push/Pull/Fetch Workflow Wiring (no pack)

**Owner:** **Villager Dev**
**Status:** Ready. Was v0.12.x B15 — partially complete (scaffolding done by Sonnet); this brief wires the workflows into runtime.
**Estimated effort:** ~1.5 days
**Prerequisites:** B01 (bug fixes — the B15-1 keyword-arg fix is needed first).
**Touches:** `sgit_ai/core/actions/{push,pull,fetch}/`, `sgit_ai/workflow/{push,pull,fetch}/`, tests.

---

## Why this brief exists

Per the Sonnet debrief (`02__sonnet-session-update-2026-05-05.md` §3), the **workflow infrastructure for push / pull / fetch is shipped** — schemas, workspaces, steps, orchestrators all exist. **But nothing is wired to runtime.** The `Vault__Sync__Push.push()`, `Vault__Sync__Pull.pull()`, and `Vault__Fetch.fetch()` methods still use the existing pre-workflow implementations.

The original B15 was blocked on B08 (server packs). With B08 deferred, this brief picks up the **non-pack wiring** — switch the runtime to use the workflows, keep the existing `Vault__Batch.build_push_operations()` for actual transfers (no new wire format).

When B08 eventually un-archives, swapping `Step__Push__Upload_Objects` for `Step__Push__Upload_Pack` becomes a one-step change.

---

## Required reading

1. This brief.
2. `team/villager/v0.12.x__perf-brief-pack/02__sonnet-session-update-2026-05-05.md` §3 — what was shipped and what wasn't.
3. `team/villager/v0.12.x__perf-brief-pack/brief__15__push-pull-fetch-generalize.md` — the original B15.
4. The existing workflow scaffolding: `sgit_ai/workflow/{push,pull,fetch}/`.
5. The runtime methods to replace: `sgit_ai/core/actions/push/Vault__Sync__Push.py:push()`, `sgit_ai/core/actions/pull/Vault__Sync__Pull.py:pull()`, `sgit_ai/core/actions/fetch/Vault__Fetch.py:fetch()`.
6. **B01 must land first** — the `_p` keyword fix is required for the workflow steps to actually run.

---

## Scope

### Step 1 — Audit `Step__Pull__Merge` against `Vault__Sync__Pull.pull()`

Per Sonnet debrief §7.7: the workflow `Step__Pull__Merge` reimplements fast-forward + three-way merge logic from `Vault__Sync__Pull.pull()`. Before wiring, audit:
- Fast-forward case (LCA == clone HEAD)
- Three-way merge case
- Up-to-date case (LCA == named HEAD)
- Conflicts case (`.conflict` files + `merge_state.json`)
- Signing key loading for merge commits (the workflow currently SKIPS this — pull() loads from `key_manager`)

Fix any missing case in the workflow before wiring.

### Step 2 — Wire each workflow

For push / pull / fetch:
1. Replace the current method body (~150 LOC each) with a workflow invocation:
   ```python
   def pull(self, directory, on_progress=None) -> dict:
       wf = Workflow__Pull()
       ws = Pull__Workspace.create(wf.workflow_name(), directory)
       ws.sync_client = self
       ws.on_progress = on_progress or (lambda *a, **k: None)
       runner = Workflow__Runner(workflow=wf, workspace=ws, keep_work=False)
       return runner.run(input=Schema__Pull__State(...))
   ```
2. Run all existing pull / push / fetch tests — must pass without modification.
3. Run a **byte-identical** assertion test (clone, push, pull on a fixture vault; compare `bare/` + working tree pre vs post wiring).

### Step 3 — Register workflows in `sgit dev workflow`

Per Sonnet debrief §7.4: the dev CLI auto-discovers workflows by walking `sgit_ai/workflow/`. Make sure `sgit dev workflow list` shows `clone`, `pull`, `push`, `fetch` after this brief lands.

### Step 4 — Functional integration tests

The Sonnet debrief notes the existing tests are "structural only." This brief adds **functional** tests:
- End-to-end round trip per workflow using `Vault__Test_Env.setup_two_clones()`.
- Step-level resume tests: invoke workflow, kill at step N, resume from workspace, verify identical end state.
- Step-level inspect tests: `sgit dev workflow inspect <work-id>` after a pull shows the right per-step outputs.

---

## Hard rules

- **Behaviour preservation.** Same on-disk results post-wiring as pre-wiring.
- **No mocks.**
- **No new wire format.** Push uploads via `Vault__Batch` (existing per-object). When B08 unarchives, a separate brief swaps the upload step.
- **Coverage must not regress.**
- **Suite must pass under `-n auto`.**

---

## Acceptance criteria

- [ ] B01 has landed (the `_p` keyword fix).
- [ ] `Step__Pull__Merge` audit complete; gaps fixed.
- [ ] `Vault__Sync__Pull.pull()`, `Vault__Sync__Push.push()`, `Vault__Fetch.fetch()` are workflow-driven.
- [ ] Existing push / pull / fetch tests pass without modification.
- [ ] Byte-identical pre-wiring vs post-wiring assertion passes for a fixture vault.
- [ ] `sgit dev workflow list` shows all 4 workflows (clone, pull, push, fetch).
- [ ] At least 5 new functional integration tests per workflow.
- [ ] Suite ≥ 3,068 + ~15 new tests passing.

---

## When done

Return a ≤ 250-word summary:
1. Audit findings on `Step__Pull__Merge` (gaps + fixes).
2. LOC removed from each `Vault__Sync__<X>` runtime method.
3. Byte-identical assertion outcome.
4. Test count + coverage delta.
5. Confirmation `sgit dev workflow list` shows 4 workflows.
