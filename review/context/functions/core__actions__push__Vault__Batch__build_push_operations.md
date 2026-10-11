## `build_push_operations` in sgit_ai/core/actions/push/Vault__Batch.py (L19-L107)

**Purpose:** Assembles the ordered list of batch operations for a push: new blobs (small ones as `write` ops, large ones uploaded immediately via presigned multipart), every commit on the chain and every tree reachable from each, and **last** the named-branch ref — as a plain `write` for `--force` or a brand-new ref, as `write-if-match` otherwise. The ref op is what decides whether a push can overwrite a teammate's.

**Inputs & Assumptions:**
- `obj_store`, `ref_manager`: local store (trusted).
- `clone_tree_entries` (list of `{'blob_id'}` dicts, from `collect_chain_blob_entries`), `named_blob_ids` (set: blobs the server already has, per the caller's reading of the remote tree / push checkpoint). Trust: derived locally from decrypted trees.
- `commit_chain` (list[str]) from `Vault__Fetch.fetch_commit_chain` (sgit_ai/core/actions/fetch/Vault__Fetch.py:L18-L76): commits reachable from the clone head but not from `named_commit_id`, **plus `named_commit_id` itself as a boundary marker** (L67-L71 there) — skipped here at L73-L74.
- `named_commit_id` (str | None): the head the server is believed to be at (the local copy of the named ref after the pull; `push` L173).
- `read_key` (bytes): to decrypt commits/trees for traversal and to encrypt the ref value.
- `named_ref_id` (str): the ref file to move; `clone_commit_id` (str): the new head.
- `expected_ref_hash` (str | None): **base64 of the bytes the server is expected to hold** for the ref (`Vault__Ref_Manager.get_ref_file_hash` L65-L76: the local ref file's raw bytes; or the server's bytes read by `_check_lease` L959 / `_remote_clone_ref` L631). `None` means "no compare-and-swap".
- `vault_id`, `write_key`: enable the large-blob path (L53).
- `force` (bool): plain write of the ref.
- `skip_missing_trees` (bool): scoped clones.
- Preconditions: every id in `commit_chain` except the boundary is in `obj_store` (`obj_store.load` raises `Vault__Object_Missing_Error` otherwise, Vault__Object_Store.py:L84-L91) — established by `push` L217-L231 (fetches the named tree when missing) and by `collect_chain_blob_entries` skipping absent blobs.

**Outputs & Effects:**
- Returns `(operations, large_uploaded)`.
- External: `_upload_large` PUTs ciphertext to host-named URLs **during** this call (L54-L55), before any batch is sent — a large blob reaches S3 even if the batch later fails or conflicts. Content-addressed, so harmless to history.
- No local writes.
- Postcondition: `operations[-1]` is the ref op (L105). `execute_batch` additionally sorts any `bare/refs/` op into the last chunk (L282-L284).

**Block-by-Block:**

```python
# L48-L63
for entry in clone_tree_entries:
    blob_id = entry.get('blob_id') if isinstance(entry, dict) else (...)
    if not blob_id or blob_id in named_blob_ids or blob_id in uploaded_ids: continue
    ciphertext = obj_store.load(blob_id)
    if vault_id and write_key and len(ciphertext) > LARGE_BLOB_THRESHOLD:
        uploaded = self._upload_large(vault_id, f'bare/data/{blob_id}', ciphertext, write_key, on_progress)
        if uploaded: uploaded_ids.add(blob_id); large_uploaded += 1; continue
    operations.append(dict(op='write', file_id=f'bare/data/{blob_id}', data=b64(ciphertext)))
    uploaded_ids.add(blob_id)
```
- **What:** every blob not already on the server becomes a write (or an immediate multipart upload above 4 MB, L19 of Vault__API.py).
- **Why here:** blobs before trees/commits so that, chunk by chunk, content lands before the objects that reference it.
- **Assumes:** `named_blob_ids` really are on the server. In `push` it is `uploaded_blob_ids = named_blob_ids ∪ push-checkpoint blobs ∪ blobs just uploaded` (Vault__Sync__Push.py:L262, L295, L317, L320); the checkpoint is a local file (`push_state.json`, `_load_push_state`) and the named set comes from flattening the local copy of the remote head's tree — both are *this clone's belief*, not a server check: `nothing found` verifying the server holds them. (A missing blob on the server is caught by the next clone's verify step, not by push.)
- **Establishes:** `uploaded_ids` ⊇ blobs in `operations`.

```python
# L65-L88
vault_commit = Vault__Commit(...)
for cid in commit_chain:
    if cid == named_commit_id: continue
    if cid not in uploaded_ids:
        operations.append(write bare/data/<cid>)
    c       = vault_commit.load_commit(cid, read_key)
    tree_id = str(c.tree_id)
    self._collect_tree_objects(tree_id, obj_store, read_key, operations, uploaded_ids, skip_missing=skip_missing_trees)
```
- **What:** each new commit object and its full tree closure.
- **Assumes:** `load_commit` (Vault__Commit.py:L78-L98) decrypts under the read key and parses — local objects, trusted.
- **Establishes:** every tree reachable from a pushed commit is in `operations` (or already uploaded / skipped as a scoped sibling).

```python
# L90-L105
ref_ciphertext = ref_manager.encrypt_ref_value(clone_commit_id, read_key)
if force:
    ref_op = dict(op='write', file_id=f'bare/refs/{named_ref_id}', data=...)
elif expected_ref_hash:
    ref_op = dict(op='write-if-match', file_id=..., data=..., match=expected_ref_hash)
else:                                   # no ref on the server yet (a new branch, a first push)
    ref_op = dict(op='write', ...)
operations.append(ref_op)
```
- **What:** the branch move. `encrypt_ref_value` is `AES-GCM(read_key, json {'commit_id': ...})` with a random IV (Vault__Ref_Manager.py:L60-L63, Vault__Crypto.encrypt L294-L299) — no associated data binds it to `named_ref_id` (TM-R03).
- **Why last:** so a CAS miss rejects the move after the objects are already present (atomic in one batch; `execute_batch` keeps refs in the final chunk).
- **Assumes (force):** the caller has authority to overwrite. `push` passes `force` straight from the CLI `--force` (CLI__Vault.py:L1204, L1211), except that `--force-with-lease` sets `force=False` again after the lease check so the write is CAS (Vault__Sync__Push.py:L204-L206). Test: `tests/unit/sync/test_Vault__Batch__Large_Blob.py::test_force_push_uses_write_op_not_cas_line_92`.
- **Assumes (CAS):** `expected_ref_hash` is what the server currently holds. Where it comes from decides the guarantee: `push` L201 uses the **local** ref file bytes (`get_ref_file_hash`) — correct only if the local named ref equals the server's, which the preceding pull establishes (L165-L173) or, for `--force-with-lease`, the server read (L205, `_check_lease` L949-L959); branch-only uses the server's bytes (L630-L631). A stale local copy makes the CAS miss (safe); the live server answers `conflict` per op (`_checked`).
- **Assumes (plain, no expected hash):** the ref really is absent on the server. In `push` this happens when `_named_ref_absent_on_server` returned True (L202-L203) — i.e. the **server said** `not_found` — or when `get_ref_file_hash` returned None because the local ref file does not exist (L201 → `Vault__Ref_Manager.get_ref_file_hash` L72-L73). TM-R33 documents the first-write race; a host answering `not_found` for an existing ref gets the same blind write: `nothing found` beyond the server's word.
- **Establishes:** the ref moves only to `clone_commit_id`; whether anyone else's move is overwritten depends on the branch taken here.

**Cross-Function Dependencies:**
- Callees: `_upload_large` (L109-L170), `_collect_tree_objects` (L218-L244), `Vault__Commit.load_commit`, `Vault__Ref_Manager.encrypt_ref_value`, `Vault__Object_Store.load`.
- Callers: `Vault__Sync__Push.push` L323-L338 (force/CAS/plain per above; on a first push the result is filtered to the ref ops only, L349-L350, the bare upload having sent the rest); `Vault__Sync__Push._push_branch_only` L665-L679 (clone ref, CAS against the server's bytes, never `force`).
- Shared state: none in this object.
- Invariant coupling: "a push that loses a race fails loudly and never overwrites the winner" (threat model §5, Push compare-and-swap) holds on the CAS branch only; `force` and the absent-ref branch are plain writes by design.

**Open Questions:**
- unclear; `push` passes `expected_ref_hash = ref_manager.get_ref_file_hash(named_ref_id)` **before** checking `_named_ref_absent_on_server` (L201-L203); when the local ref file exists but the server reports the ref absent, the CAS is dropped. Whether the local file can exist while the server legitimately has no ref (branch created locally with `branch new`) is the intended case per the comment at L203; the host-driven version is the same path.
