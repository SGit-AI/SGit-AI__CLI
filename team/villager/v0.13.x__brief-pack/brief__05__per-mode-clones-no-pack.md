# Brief B05 — Per-Mode Clones (sans-pack)

**Owner:** **Villager Dev**
**Status:** Ready. Was v0.12.x B09 — implements the clone-mode stubs registered in v0.12.x B03.
**Estimated effort:** ~2 days
**Prerequisites:** B03 (clone_read_only into workflow) — clone-branch builds on the workflow framework.
**Touches:** `sgit_ai/workflow/clone/`, `sgit_ai/core/actions/clone/`, tests.

---

## Why this brief exists

v0.12.x B03 registered `clone-branch`, `clone-headless`, `clone-range` as top-level CLI stubs. The original v0.12.x B09 was supposed to implement them — but assumed B08 server packs as the speed-up mechanism.

With B08 deferred, **B05 implements the high-leverage `clone-branch` mode purely client-side**: walk only HEAD's tree, skip historical trees, lazy-fetch on demand for `log -p` / `diff <past>` / `checkout <past>`. Per the B07 diagnosis, this delivers a **40–50× speedup on the case-study vault** without any backend change.

`clone-headless` and `clone-range` are smaller deliverables; we ship them too but they're less critical.

---

## Required reading

1. This brief.
2. `team/villager/v0.12.x__perf-brief-pack/changes__case-study-diagnosis.md` §"H5 — Walking historical trees is fundamentally unnecessary".
3. `team/villager/v0.12.x__perf-brief-pack/design__01__access-modes.md` (the four modes).
4. `team/villager/v0.12.x__perf-brief-pack/brief__09__per-mode-clone-impl.md` — the original.
5. `sgit_ai/workflow/clone/` — post-B03 layout (Workflow__Clone, Workflow__Clone__ReadOnly, etc.).
6. Existing CLI stubs in `sgit_ai/cli/CLI__Main.py` for `clone-branch`, `clone-headless`, `clone-range`.

---

## Scope

### Step 1 — `clone-branch` (the headline win)

A new `Workflow__Clone__Branch` that differs from `Workflow__Clone` (full) at one step:
- `Step__Clone__Walk_Trees__Head_Only` — walks ONLY the trees rooted at HEAD's commit, NOT every commit's root tree.

Plus a small lazy-fetch path:
- `Vault__Sync.fetch_tree_lazy(tree_id)` — checks if the tree is in `bare/data/`; if not, downloads it via `api.batch_read([f'bare/data/{tree_id}'])`.
- Wire this lazy fetch into `Vault__Sync__Pull._fetch_missing_objects` and into the history-traversal commands (`history log -p`, `history diff <past>`, etc.).

Each lazy fetch logs to `.sg_vault/local/lazy-fetch.log` for observability.

### Step 2 — `clone-headless`

A new `Workflow__Clone__Headless` that:
- Derives keys.
- Verifies vault exists + accessible (probe-style call).
- Creates **only** `.sg_vault/local/` with credentials (vault_id, read_key, base_url). No `bare/` directory; no working copy.
- All subsequent commands operate against the server live.

The CLI handler for `sgit clone-headless` wires this workflow.

### Step 3 — `clone-range <vault-key>:<from>..<to>`

A new `Workflow__Clone__Range`:
- Walks ONLY the commits in the requested range.
- Walks the trees + blobs reachable in that range (not the whole history).
- Materialises the range-tip's working copy.

Re-uses most of the `Workflow__Clone__Full` steps; differs at `Step__Clone__Walk_Commits__Range` and `Step__Clone__Walk_Trees__Range`.

### Step 4 — `--bare` flag

For `clone --bare`, `clone-branch --bare`, `clone-range --bare`:
- Skip `Step__Clone__Extract_Working_Copy`. Workflow ends after `setup_local_config`.
- Add a `bare: bool = False` field to each workflow's input schema.

`clone-headless --bare` errors friendly: "redundant flag" (per design D1).

### Step 5 — Tests

- One workflow-level happy-path test per mode using `Vault__Test_Env.setup_single_vault()`.
- `clone-branch` lazy-fetch tests: clone, then `history log -p`, assert lazy fetch was triggered.
- `clone-headless` test: clone, then `file cat`, assert no `bare/data/` access.
- `clone-range` test: clone a range, assert only range objects are present.
- `--bare` tests for each applicable mode.

### Step 6 — Re-measurement

After this brief lands, **re-measure the case-study vault** with `clone-branch`:
- Expected: drops from 184s tree-walk → ~5s (only ~50 trees instead of 2,375).
- Append the result to `changes__case-study-diagnosis.md` as §"Post-B05 re-measurement".

---

## Hard rules

- **Type_Safe everywhere.**
- **No mocks.**
- **Behaviour:** for `clone` (full), no change from B03. New modes are new behaviour but should be documented.
- **Coverage must not regress.**
- **Suite must pass under `-n auto`.**
- Each mode workflow has its own progress reporting.

---

## Acceptance criteria

- [ ] Three new workflows: `Workflow__Clone__Branch`, `Workflow__Clone__Headless`, `Workflow__Clone__Range`.
- [ ] `Vault__Sync.fetch_tree_lazy(tree_id)` exists; wired into history commands.
- [ ] `--bare` flag honoured for clone, clone-branch, clone-range; rejected for clone-headless.
- [ ] At least 4 happy-path tests + 4 mode-specific tests.
- [ ] `sgit dev workflow list` shows all 6 clone workflows (full / readonly / transfer / branch / headless / range).
- [ ] Coverage delta non-negative.
- [ ] Re-measurement on case-study vault: `clone-branch` ≤ 10s tree-walk (down from 184s).

---

## When done

Return a ≤ 250-word summary:
1. Workflows shipped + their step lists.
2. Lazy-fetch wiring confirmation.
3. Performance numbers per mode (clone-branch vs clone, headless vs clone, range vs clone).
4. Coverage + test count deltas.
5. Re-measurement on case-study vault.
