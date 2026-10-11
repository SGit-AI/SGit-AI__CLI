## `pull` in sgit_ai/core/actions/pull/Vault__Sync__Pull.py (L72-L108)

**Purpose:** Entry point for a writable clone's pull (and for `sgit branch merge <name>` via `merge_from`). It builds the 5-step `Workflow__Pull` and runs it; every check and every write of the pull lives in those steps, in this order: derive keys → load branch info (index refresh) → fetch remote ref (rewind guard, nothing written) → fetch missing (signature policy, then **accept**) → merge (dirty-tree guard, checkout, clone-ref write).

**Inputs & Assumptions:**
- `directory`: trusted.
- `on_progress`: callback.
- `accept_rewind` (bool): from `sgit pull --accept-rewind` (`CLI__Vault.cmd_pull` L968). Trust: user intent; it widens what the pull accepts (see `_guard_rewind`, `_accepted_head`).
- `merge_from` (str | None): a branch name to merge instead of the tracked one (L98-L99 → `Step__Pull__Load_Branch_Info` L77-L82).
- Precondition L77: no merge in progress (`Vault__Merge__State.check_not_in_progress`). L80-L81: an index id exists.

**Outputs & Effects:**
- Creates `.sg_vault/work/` (L91-L92) for the workflow workspace; `keep_work=False` removes it on success (`Workflow__Runner.py:L122-L123`).
- Everything else happens in the steps; returns `_pull_state_to_dict(final_state)` (L108).
- Exceptions from steps are re-raised with their original type (`Workflow__Runner.py:L126-L130`), so `Vault__Signature_Error`, `Vault__Ref_Rewind_Error`, `Vault__Unreadable_Ref_Error`, `Vault__Dirty_Working_Tree_Error` reach the CLI as themselves.

**Block-by-Block:**

```python
# L77-L81
Vault__Merge__State().check_not_in_progress(directory, 'pull')
self._auto_gc_drain(directory)
c = self._init_components(directory)
if not c.branch_index_file_id:
    raise RuntimeError('No branch index found')
```
- **What:** Preconditions; `_init_components` also applies the format gate (`_apply_vault_format`, `Vault__Sync__Base.py:L348-L362`) from the **local** index — a `Vault__Client_Too_Old_Error` refuses here before any network.

```python
# L90-L102
wf = Workflow__Pull(); ws = Pull__Workspace.create(...)
ws.sync_client = self; ws.on_progress = on_progress; ws.accept_rewind = bool(accept_rewind)
if merge_from: ws.merge_from = merge_from
runner = Workflow__Runner(workflow=wf, workspace=ws, keep_work=False)
final_dict = runner.run(input=initial)
```
- **What:** Run the steps. `ws.sync_client = self` is how steps reach `self.api`, `self.crypto`, and the Base helpers (`_accepted_head`, `_write_remote_baseline`, `_fetch_missing_objects`, `_checkout_flat_map`).
- **Depended on by:** all steps.

**Order of checks before each accept on this path (traced):**
1. `Step__Pull__Load_Branch_Info._refresh_index` (L17-L45): server index merged into local (gate from server copy; `Vault__Client_Too_Old_Error` re-raised, everything else warned and ignored, L42-L45). Teammate key files fetched (L39-L41).
2. `Step__Pull__Fetch_Remote_Ref.execute` (L65-L125): `last_known = _accepted_head(...)` (L78-L84; a damaged/missing `remote_heads.json` raises unless `accept_rewind`); server ref read (L87); `_guard_rewind` (L89) — classify; REWOUND refuses unless accepted, UNKNOWN proceeds, exceptions refuse unless accepted (L44-L56 of the step); unreadable ref refuses (L91-L94). **Nothing written** (comment L102-L105); the server's bytes are kept in `ws.remote_ref_data` (L96).
3. `Step__Pull__Fetch_Missing.execute` (L46-L121): `_enforce_signature_policy` (L69) → `Vault__Incoming_Check.require_signatures`; then `_fetch_missing_objects` (L85, verified writes of objects); then `_find_missing_blobs` and refuse if any HEAD blob is absent (L91-L98, non-sparse only); **then `_accept`** (L101): writes the server's exact ref bytes to `bare/refs/<named_ref_id>` (L37-L41) and the baseline (L44).
4. `Step__Pull__Merge.execute`: LCA (L70), rewind handling (L73-L82), `_guard_working_tree` (L96 / L126 / L233) **before** `_checkout_flat_map` (L99 / L129 / L235), then the **clone** ref write (L101 / L171 / L261).

So the named ref and baseline are written at step 3 after the policy and after the objects are local, but **before** the dirty-tree guard and the merge in step 4. A pull refused by `Vault__Dirty_Working_Tree_Error` (or a merge conflict) has already moved the local named ref and baseline. That is consistent with "nothing writes a local named ref except verify-then-accept" (the head *was* verified), and it means the next pull sees the branch as up to date at the ref level while the working copy was not merged — the merge step itself re-derives from `clone_commit_id` vs `named_commit_id` (`Step__Pull__Merge` L63-L66), both carried in state, so a re-run after fixing the tree does merge. Recorded as an ordering fact, not a verdict.

**Cross-Function Dependencies:**
- Callees: the five steps (read in full; see the `workflow__pull__*` records for `_guard_rewind`, `_accept`, `_enforce_signature_policy`, `_guard_working_tree`).
- Callers: `Vault__Sync.pull` (L243-L244), `CLI__Vault.cmd_pull` (L969), `Vault__Sync.merge_branch` (via `merge_from`, L213+, not read).
- Shared state: `bare/refs/<named>`, `local/remote_heads.json`, `local/config.json`, clone ref, working copy, object store, index.
- Tests: `tests/security/test_Security__Fixed__Verify_Then_Accept.py::test_N3__a_refused_pull_leaves_no_local_ref_for_a_switch_to_check_out`, `tests/security/test_Security__Fixed__Baselines.py::test_a_forward_move_after_status_still_pulls`, `tests/unit/workflow/pull/test_Pull__Dirty_Working_Tree.py::*`.

**Open Questions:**
- unclear; whether `_accept` before `_guard_working_tree` is intended (see ordering note above). `test_edit_to_a_file_the_incoming_commit_changes_refuses_before_writing` asserts the working copy is untouched; it does not assert the local named ref is unmoved.
