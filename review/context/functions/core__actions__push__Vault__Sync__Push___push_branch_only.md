## `_push_branch_only` in sgit_ai/core/actions/push/Vault__Sync__Push.py (L608-L700)

**Purpose:** `sgit push --branch-only`: upload everything reachable from the clone head that the server does not have and move **only the clone branch's ref** on the server, compare-and-swap against the server's current bytes for that ref. The named branch is untouched.

**Inputs & Assumptions:**
- `clone_meta` (branch index entry), `clone_commit_id`, keys, stores, `use_batch`.
- Server reads: the clone ref (`_remote_clone_ref`, L630).
- Precondition from `push`: first-push bare upload already done or public key ensured (L137-L142); the dirty-tree check passed (L91-L95). **No pull** precedes a branch-only push (the `branch_only` branch returns at L162 before the pull at L165) and no `require_signatures` check runs for it (L195 is after the return): a clone under `signatures-required` can publish unsigned commits on its clone ref; readers (`switch`, pull of that branch) refuse them (`tests/security/test_Security__Fixed__Verify_Then_Accept.py::test_N2__switch_to_a_never_fetched_branch_refuses_an_unsigned_head`). Observation.

**Outputs & Effects:**
- Host writes: blobs/commits/trees as plain writes; `bare/refs/<clone_ref_id>` as `write-if-match` (server bytes) or plain `write` when the server has none (or the read failed — see `_remote_clone_ref`).
- No local ref/baseline change (the clone ref is already at `clone_commit_id` locally; the named baseline is not touched).
- Returns `pushed_branch_only` with counts.

**Block-by-Block:**

```python
# L630-L631
remote_ref, remote_head = self._remote_clone_ref(vault_id, clone_ref_id, read_key)
expected_ref_hash = base64.b64encode(remote_ref).decode('ascii') if remote_ref else None
```
- **What:** the match is the **server's** bytes, not the local file's (comment L625-L629: the local clone ref moved at commit time, so its bytes are the wrong match).
- **Establishes:** a concurrent writer to the clone ref (another process of the same clone, or a host) conflicts; absence → plain write.

```python
# L638-L641
stop_at = remote_head or self._local_named_head(directory, read_key)
commit_chain = fetcher.fetch_commit_chain(obj_store, read_key, clone_commit_id, stop_at=stop_at or None)
```
- **What:** everything the server already has for this clone branch (its last pushed head) — or, before any branch-only push, the named head the clone started from — is assumed present on the server.
- **Assumes:** the server still holds the objects of `remote_head`'s history. It is the server's own ref value; `nothing found` verifying the objects exist there (they were pushed by this clone earlier).

```python
# L654-L662
if stop_at and obj_store.exists(stop_at):
    stop_commit    = vault_commit.load_commit(stop_at, read_key)
    remote_flat, _ = Vault__Scoped_Tree(...).flatten(str(stop_commit.tree_id), read_key, scope)
    remote_blob_ids = {e.get('blob_id') ...}
```
- **What:** blobs in the stop commit's tree are treated as on the server.

```python
# L664-L694
operations, large_uploaded = batch.build_push_operations(..., named_blob_ids=remote_blob_ids, commit_chain=commit_chain, named_commit_id=stop_at or None, named_ref_id=clone_ref_id, clone_commit_id=clone_commit_id, expected_ref_hash=expected_ref_hash, vault_id=vault_id, write_key=write_key, on_progress=None, skip_missing_trees=scoped)
...
if use_batch:
    try: batch.execute_batch(vault_id, write_key, operations)
    except Vault__Push_Conflict_Error: raise
    except Exception as e: batch.execute_individually(vault_id, write_key, operations)
else: batch.execute_individually(..., atomic_moves=False)
```
- **What:** `force` is never passed (default False), so the ref op is CAS or plain-on-absent only.
- **Assumes:** as in `push` Phase B.

**Cross-Function Dependencies:**
- Callees: `_remote_clone_ref` L582-L592, `_local_named_head` L597-L606, `Vault__Fetch.fetch_commit_chain`, `Vault__Batch.collect_chain_blob_entries/build_push_operations/execute_batch/execute_individually`, `Vault__Scoped_Tree.flatten`, `Vault__Commit.load_commit`.
- Caller: `push` L145-L150 when `branch_only`.
- Tests: `tests/unit/sync/test_Vault__Sync__Push__Coverage.py::Test_Vault__Sync__Push__BranchOnly` (fallback and no-batch paths).

**Open Questions:**
- unclear; whether a branch-only push is meant to bypass `signatures-required` for the clone ref (the named-branch check at L195-L198 is not reached). The clone ref is this clone's own branch; readers re-check.
