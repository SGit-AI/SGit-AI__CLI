## `execute` in sgit_ai/workflow/pull/Step__Pull__Fetch_Remote_Ref.py (L65-L125)

**Purpose:** Step 3 of the writable pull: read the server's named ref, run the rewind guard, and carry the decrypted head and the raw bytes forward **without writing anything** (comment L102-L105, review d3b8eef N3).

**Inputs & Assumptions:** state from step 2 (`named_ref_id`, `clone_commit_id`, `read_key_hex`); `workspace.accept_rewind`.

**Outputs & Effects:**
- `named_commit_id` = the server's head, else the local ref (L106) — so offline, the pull proceeds from the local copy of the named ref (which, under the N3 rule, was itself written only by an earlier accept).
- `remote_reachable` True only when the ref decrypted (L95).
- `workspace.remote_ref_data` = the server's exact bytes when readable (L96), for `_accept` to store verbatim so push's compare-and-swap matches.
- Raises `Vault__Ref_Rewind_Error` (from `_accepted_head` L78-L82 on a damaged record, or from `_guard_rewind`) and `Vault__Unreadable_Ref_Error` (L91-L94). Any other exception from the server read is a warning (L99-L100) and the pull continues offline.

**Block-by-Block:**

```python
# L77-L84
accept_rewind = bool(getattr(workspace, 'accept_rewind', False))
try:
    last_known = workspace.sync_client._accepted_head(str(input.directory), workspace.storage, accept_rewind, named_ref_id)
except Vault__Ref_Rewind_Error:
    raise
except Exception:
    last_known = ''
```
- **What:** The per-branch baseline. A damaged/missing-after-recorded record refuses (L1) unless `--accept-rewind` (then `''`).
- **Assumes:** `_accepted_head` semantics (see Base record). Any *other* exception ⇒ `''` ⇒ the rewind guard is skipped (L23-L24 of `_guard_rewind`). What else can `_remote_baselines` raise? It wraps the file read in `try/except Exception → Vault__Ref_Rewind_Error` (L171-L181); `_remote_heads_file_recorded` swallows (L202-L206); `_read_last_remote_head` swallows (L131-L135); `_tracked_named_ref_id` swallows (L264-L271). So the generic `except` at L83 is a safety net; nothing found that reaches it.

```python
# L87-L100
remote_ref_data = workspace.sync_client.api.read(vault_id, named_ref_file_id)
if remote_ref_data:
    self._guard_rewind(workspace, input, read_key, remote_ref_data, last_known)
    remote_head = self._parse_ref(...)
    if not remote_head: raise Vault__Unreadable_Ref_Error(...)
    remote_reachable = bool(remote_head)
    workspace.remote_ref_data = remote_ref_data if remote_head else None
```
- **What:** Guard first, then decrypt for the state. (The guard decrypts internally too.)
- **Why here:** The guard runs on the raw bytes before `remote_head` is even assigned, so a refused rewind leaves `remote_head=''`… but the exception propagates anyway.
- **Assumes:** `api.read` returns `b''`/`None` for an absent ref (a branch with no commits) → `remote_reachable=False`, no error. A 403/5xx raises → caught at L99 as "Could not fetch remote ref" → offline behaviour.

```python
# L106
named_commit_id = remote_head or workspace.ref_manager.read_ref(named_ref_id, read_key) or ''
```
- **What:** fallback to the local named ref when offline.
- **Assumes:** the local named ref was written only by an accept (N3). `test_N3__status_writes_no_ref` establishes `status` does not write it; `Vault__Branch_Switch` writes clone refs only (L91, L107 of Branch_Switch) and `branch_new` writes a *new* named ref for a branch it creates (L223).

**Cross-Function Dependencies:**
- Callee `_guard_rewind`, `_parse_ref` (L58-L63, swallow-all → `''`).
- Callee `Vault__Sync__Base._accepted_head` (L227-L237): see record.
- Callee `Vault__API.read` (L98-L100): GET with token headers.
- Callers: `Workflow__Pull` step order L18-L24.
- Shared state: reads `remote_heads.json`, `config.json`, local ref; writes none (objects aside, via the guard).

**Open Questions:** none beyond those in `_guard_rewind`.
