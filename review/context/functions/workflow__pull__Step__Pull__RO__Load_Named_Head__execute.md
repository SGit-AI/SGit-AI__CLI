## `execute` in sgit_ai/workflow/pull/Step__Pull__RO__Load_Named_Head.py (L32-L131)

**Purpose:** Read-only pull step 2: resolve the tracked named branch, find what this reader last accepted, read the server's ref, run the rewind guard, and hand the head forward **without writing** (comment L112-L114, review K2).

**Inputs & Assumptions:**
- state from derive-keys (`read_key_hex` from `clone_mode.json`, `vault_id`, `branch_index_file_id`).
- `workspace.accept_rewind`.
- Implicit: `clone_mode.json` `branch_name` (`_tracked_branch_name`, `Vault__Sync__Base.py:L317-L329`, default `'current'`).

**Outputs & Effects:**
- `clone_commit_id` := the cached accepted head (used downstream as the "held" head and the fetch stop point); `named_commit_id` := server head or cached or local ref (L115); `clone_branch_id`/`clone_ref_id` None (L124-L125).
- Index refresh may write the local index (L45-L50; `Vault__Index_Sync.refresh` with no write key saves the merge locally, L287-L288 of Index_Sync; every exception swallowed, **including `Vault__Client_Too_Old_Error`** — contrast the writable step which re-raises it, `Step__Pull__Load_Branch_Info` L42-L43. The gate is still applied at L51-L52: `load_branch_index` → `check_client` raises there).
- Raises `Vault__Ref_Rewind_Error`, `Vault__Unreadable_Ref_Error`.

**Block-by-Block:**

```python
# L74-L83
accepted = workspace.sync_client._accepted_head(directory, workspace.storage, bool(accept_rewind), named_ref_id)
...
cached_named_commit_id = accepted or workspace.ref_manager.read_ref(named_ref_id, read_key) or ''
if cached_named_commit_id and not workspace.obj_store.exists(cached_named_commit_id):
    cached_named_commit_id = ''
```
- **What:** What the reader last ACCEPTED is the baseline and the policy's "held" head; the local ref is only a fallback for a clone with no record (comment L70-L72). A pointer to a non-local object is discarded (comment L63-L69).
- **Assumes:** the local ref was written only by an accept (N3). A pre-fix clone whose `status` had moved the local ref is covered by the object-existence check only partially (status *does* download commit objects via `_fetch_commit_chain`, so the object may exist) — hence the baseline-first order. `test_N3__status_between_read_only_pulls_does_not_get_past_the_policy` establishes current behaviour.

```python
# L90-L110
last_known = accepted
remote_ref_data = api.read(vault_id, named_ref_file_id)
if remote_ref_data:
    guard_input = Schema__Pull__State(directory=…, named_ref_id=…, clone_commit_id=cached…)
    Step__Pull__Fetch_Remote_Ref()._guard_rewind(workspace, guard_input, read_key, remote_ref_data, last_known)
    remote_head = …_parse_ref(...)
    if not remote_head: raise Vault__Unreadable_Ref_Error(...)
```
- **What:** Same guard as the writable path (TM-R05).
- **Depended on by:** `Step__Pull__Fetch_Missing` (policy with `held = cached`), `Step__Pull__RO__Checkout` (accept).

**Cross-Function Dependencies:**
- Callees: `Vault__Index_Sync.refresh`, `_accepted_head`, `_guard_rewind`, `Vault__Sync__Status._parse_ref`, `Vault__Branch_Manager.get_branch_by_name` (L55; the reader tracks by *name*, so a renamed branch changes what it follows).
- Callers: `Workflow__Pull__ReadOnly` L33.

**Open Questions:**
- unclear; swallowing `Vault__Client_Too_Old_Error` from the refresh (L49-L50) is harmless only because L51-L52 re-checks the gate on the *merged local* copy; if the refresh itself failed before saving, the local copy may be older than the server's gate. Then `min_client` from the server is not applied for a reader this run. (TM-R29 territory: `min_client` follows the server copy.)
