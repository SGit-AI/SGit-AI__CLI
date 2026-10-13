## `_register_pending_branch` in sgit_ai/core/actions/push/Vault__Sync__Push.py (L820-L885)

**Purpose:** First push after a clone: publish the clone branch to the shared **branch index** (merge with the server's copy, write with compare-and-swap, never a blind overwrite), write the clone ref and the clone's public key, then delete `local/pending_registration.json`. The index write is the one place push touches a file every other clone and the web UI also write.

**Inputs & Assumptions:**
- `local/pending_registration.json`: `{index_id, head_ref_id, public_key_id, commit_id}` written by `Step__Clone__Create_Clone_Branch` (sgit_ai/workflow/clone/Step__Clone__Create_Clone_Branch.py:L43-L54). Trust: local file; its `head_ref_id`/`public_key_id` are interpolated into `file_id`s (L864, L873) without re-validation: `nothing found` (the writer stored `str(Safe_Str__Ref_Id)`/`str(Safe_Str__Key_Id)`).
- Server: the current index bytes (`read_remote`).

**Outputs & Effects:**
- Host writes: `bare/indexes/<index_id>` by CAS (`Vault__Index_Sync.upload`, retried up to 3 times with re-read + merge, Vault__Index_Sync.py:L169-L198); `bare/refs/<head_ref_id>` plain `write` (the clone ref, first write — TM-R33 shape); `bare/keys/<public_key_id>` plain `write`.
- Local: the merged index saved when it differs from the local copy (L850-L851); the pending file removed (L885) — **only reached when every step succeeded**; a failed registration repeats next push.
- Raises `Vault__Push_Conflict_Error` when the index cannot be merged/written for any reason other than `Vault__Client_Too_Old_Error` (L852-L858; review d3b8eef N5; test `tests/security/test_Security__Fixed__Index_Overwrite.py::test_N5__a_lost_index_race_fails_the_push_and_keeps_the_policy`).

**Block-by-Block:**

```python
# L838-L858
if os.path.isfile(index_file_path):
    try:
        c     = self._init_components(directory)
        sync  = Vault__Index_Sync(crypto=self.crypto, api=self.api)
        local = c.branch_manager.load_branch_index(directory, index_id, read_key)
        raw, remote = sync.read_remote(vault_id, index_id, read_key)
        merged = sync.merge(local, remote) if remote is not None else local
        sync.upload(vault_id, index_id, read_key, write_key, merged, expected_raw=raw)
        if not sync.same(merged, local): c.branch_manager.save_branch_index(...)
    except Vault__Client_Too_Old_Error: raise
    except Exception as error: raise Vault__Push_Conflict_Error(...)
```
- **What:** read → merge → CAS write.
- **Assumes (read_remote):** `(None, None)` when the index is absent **or unreadable or the read errored** (Vault__Index_Sync.py:L44-L52: any exception → `(None, None)`; undecryptable → `(raw, None)`). With `remote is None`, `merged = local` and `upload(..., expected_raw=raw)`: `raw=None` → **plain write** of the local index (L178: `'write' if expected is None`); `raw` present but undecryptable → CAS against those bytes with the local index as content, i.e. the server's unreadable index is replaced by ours if nobody else wrote in between. An offline read therefore produces a blind index write when the server is reachable again within the same call — only possible if `read` failed transiently and `batch` then succeeded. `nothing found` distinguishing "absent" from "error" in `read_remote`.
- **Assumes (merge):** `Vault__Index_Sync.merge` keeps every branch by id and takes the server's gate (format never lowered; TM-R29: features/min_client follow the server copy). The merged index written to the server is first passed through `server_copy` (drops name-clashing entries, L180 there).
- **Assumes (upload):** the conflict shapes recognised in `_cas_conflict` (top-level or per-op `conflict`, optional `current` bytes) and `409`/`412`/`conflict` in an HTTP error text (L189-L191); a reply that is neither conflict nor `ok` raises via `require_written` (L187). Test: `tests/unit/review/test_Format_Gate_And_Integrity.py::test_upload_sees_the_live_server_conflict_shape_and_merges`.
- **Establishes:** the server's index carries this clone's branch (and public key id) or the push fails before any ref/key is written.

```python
# L860-L874
if commit_id:
    batch_ops.append(dict(op='write', file_id=f'bare/refs/{pending["head_ref_id"]}', data=b64(ref_manager.encrypt_ref_value(commit_id, read_key))))
pub_key_path = storage.key_path(directory, pub_key_id)
if os.path.isfile(pub_key_path):
    batch_ops.append(dict(op='write', file_id=f'bare/keys/{pub_key_id}', data=b64(pub_key_data)))
```
- **What:** the clone ref at the clone's starting commit (`commit_id` = named head at clone time) and the public key — plain writes.
- **Assumes:** `bare/keys/<pub_key_id>` holds a **public** key (the clone's `.pem` private key lives under `local/`, threat model §2 "Clone signing keys"). The file is read and uploaded as-is: `nothing found` checking it is a public key (TM-R27 for the legacy named private key lives in the same folder but under a different id).

```python
# L876-L885
if batch_ops:
    try: batch.execute_batch(vault_id, write_key, batch_ops)
    except Exception as e: batch.execute_individually(vault_id, write_key, batch_ops)
os.remove(pending_path)
```
- **What:** then forget the pending file. If `execute_individually` raises, the file stays and registration retries next time (the index having already been written — idempotent by merge).

**Cross-Function Dependencies:**
- Callees: `Vault__Index_Sync.read_remote/merge/upload/same` (sgit_ai/core/actions/index/Vault__Index_Sync.py), `Vault__Branch_Manager.load_branch_index/save_branch_index`, `Vault__Ref_Manager.encrypt_ref_value`, `Vault__Batch.execute_batch/execute_individually`, `Vault__Storage.local_dir/index_path/key_path`.
- Caller: `push` L88, before the clean-tree check and before any "nothing to push" return.
- Shared state: the branch index with every clone's `_register_pending_branch`, `Vault__Index_Sync.refresh` (pull), `vault format`, tag create/delete, the web UI.
- Test: `test_Vault__Sync__Push__Coverage.py::test_register_pending_branch_refuses_an_index_it_cannot_merge`.

**Open Questions:**
- unclear; whether `read_remote` returning `(None, None)` on a **transient read error** (vs. a true 404) can be reached in practice when the subsequent `batch` succeeds; if so the local index is written without CAS. The in-memory double raises `RuntimeError('Not found')` for absent, which is the same exception path.
