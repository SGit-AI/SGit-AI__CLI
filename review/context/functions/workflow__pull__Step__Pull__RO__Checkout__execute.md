## `execute` in sgit_ai/workflow/pull/Step__Pull__RO__Checkout.py (L31-L125)

**Purpose:** Read-only pull step 4: straight checkout of the named head's tree, then — "verified and checked out: now accept it" (L94) — write the local named ref and the baseline.

**Inputs & Assumptions:** `named_commit_id`, `clone_commit_id` (= cached accepted head), `remote_reachable`, `named_ref_id`; scope from local config (L58-L62, failures → whole).

**Outputs & Effects:**
- **Working copy:** `_checkout_flat_map(directory, new_map, …)` (L85) then `_remove_deleted_flat(directory, disk_map, new_map)` (L86). Deletion baseline is the **disk scan** (L83), so anything on disk not in the new head (and not gitignored) is removed — there is no dirty-tree guard on this path.
- **Accept (L94-L100):** `ref_manager.write_ref(named_ref_id, named_commit_id, read_key)` (re-encrypted, reflog appended) and `_write_remote_baseline` (exceptions swallowed L96-L100). Condition: `named_commit_id and input.remote_reachable and input.named_ref_id` — runs even when `named == old` ("already up to date", L48-L50) as a refresh; never offline.
- Order within the step: checkout (L85-L86) **before** accept (L94-L100). Across steps: the policy (`Step__Pull__Fetch_Missing` L69) ran before both.

**Block-by-Block (the checkout):**

```python
# L69-L78
named_commit = workspace.vc.load_commit(named_commit_id, read_key)
new_map      = flat_of(named_commit.tree_id)
old_map = {} ; if old_commit_id: old_map = flat_of(load_commit(old_commit_id).tree_id)
disk_map = workspace.sync_client._scan_local_directory(directory)
```
- **Assumes:** `new_map` paths are author-chosen; `_checkout_flat_map` applies `is_protected` + `safe_join` per path (`Vault__Sync__Base.py:L511-L518`) and swallows per-file exceptions (L524-L525) — a blob the host withheld leaves that path unwritten *and* undeleted silently on sparse clones; on non-sparse clones `Step__Pull__Fetch_Missing` already refused the pull for a missing blob (L91-L98 of that step).

**Cross-Function Dependencies:**
- Callees: `Vault__Sync__Base._checkout_flat_map`, `_remove_deleted_flat`, `_scan_local_directory` (raises `Vault__Unreadable_File_Error` for an unreadable working-copy file — so the RO pull refuses before deleting anything when a file cannot be read, L442-L445 of Base), `Vault__Ref_Manager.write_ref`, `_write_remote_baseline`.
- Callers: `Workflow__Pull__ReadOnly` L35 (last step).
- Tests: `test_K2__a_refused_read_only_pull_refuses_again` (accept is after the policy), `test_TM_R05__read_only_clone_refuses_a_rollback` (accept-rewind path then follows).

**Open Questions:**
- unclear; the accept condition does not require that the checkout wrote every file (a per-file failure in `_checkout_flat_map` is silent). On a sparse reader the policy and the accept both happen while blobs are absent by design.
