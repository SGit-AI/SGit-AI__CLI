# Debrief 03: Resumable Push with Blob Checkpointing

**Commits:** `ca50dfd`  
**Date:** April 24, 2026  
**Files changed:** `Vault__Sync.py`, `Vault__API.py`, tests

---

## Problem

Push operations on large vaults are not atomic and can fail partway through. Before this change, a failed push left the vault in an inconsistent state: some large blobs might have been uploaded to S3, but the commit and ref update never happened. On retry, all blobs would be uploaded again, wasting bandwidth and time — especially painful for vaults with 100+ MB blobs.

Large blobs are the highest-risk step: they go through presigned S3 URLs, which can 503 under load or timeout on slow connections. A retry should skip blobs that were already successfully delivered.

---

## Design: Two-Phase Push

Push is now split into two phases, with a checkpoint file between them.

### Phase A — Blobs (immutable, resumable)

Large blobs are uploaded first via presigned S3 URLs. Small blobs follow in a single `batch_write` call. After each successful blob upload, its `object_id` is written to a checkpoint file:

```
.sg_vault/local/push_state.json
```

Structure:
```json
{
  "vault_id:commit_id": {
    "uploaded_blobs": ["obj-cas-imm-abc123", "obj-cas-imm-def456"]
  }
}
```

The checkpoint key is `{vault_id}:{commit_id}` so different pushes of different commits never collide. On retry, `build_push_operations()` receives the already-uploaded blob IDs as `named_blob_ids` and skips them entirely.

### Phase B — Commits, trees, ref (fast, CAS-atomic)

Once all blobs are confirmed, a single batch operation uploads:
- Tree objects
- Commit objects
- The CAS ref update (write-if-match on the named branch pointer)

This batch is small (typically <1 MB) and has no S3 presigned step. It either succeeds atomically or fails without any partial state — the CAS guarantee on the ref update means no partial history is visible to other clones.

On success, the checkpoint entry is deleted.

---

## Implementation Details

### `Vault__Sync.push()`

```python
# Phase A: blobs
checkpoint = self._load_push_checkpoint(vault_id, commit_id)
uploaded_blob_ids = set(checkpoint.get('uploaded_blobs', []))

for blob_id in large_blob_ids:
    if blob_id in uploaded_blob_ids:
        _p('step', f'skipping already-uploaded blob {blob_id[12:]}')
        continue
    url = self.api.get_presigned_upload_url(vault_id, blob_id, write_key)
    self._upload_blob_to_s3(url, obj_store.load(blob_id))
    uploaded_blob_ids.add(blob_id)
    self._save_push_checkpoint(vault_id, commit_id, list(uploaded_blob_ids))

# Phase B: commits + trees + ref
ops = build_push_operations(
    ...,
    named_blob_ids=uploaded_blob_ids   # skip re-uploading
)
self.api.batch_write(ops, write_key)
self._clear_push_checkpoint(vault_id, commit_id)
```

### Checkpoint Lifecycle

- Created: after each successful blob upload in Phase A
- Appended: as additional blobs complete
- Deleted: after Phase B succeeds
- Persists across process restarts: stored on disk, not in memory

If Phase B fails (network error, CAS conflict), the checkpoint remains. The next `sgit push` picks it up, skips Phase A entirely, and retries Phase B.

---

## CAS Conflict Handling

The ref update in Phase B uses write-if-match semantics: it only succeeds if the named branch still points at the commit the push was based on. If another push landed in the meantime (race condition), Phase B returns a conflict error. The CLI reports this clearly and instructs the user to `sgit pull` first.

The checkpoint is **not** deleted on CAS conflict — the blob uploads are still valid and can be reused after the pull.

---

## Trade-offs

**Benefit:** Large vault pushes (300+ MB) can survive network interruptions. The expensive S3 phase is idempotent.

**Limitation:** Checkpoint is keyed by commit_id. If the user amends the commit or resets HEAD between retries, the checkpoint is orphaned (but harmless — blobs on S3 are deduplicated by object ID, so wasted space is minimal and cleaned up by the server GC).

**Security note:** `push_state.json` contains only object IDs (ciphertext hashes), never plaintext or keys. It's safe to leave on disk.
