# Resumable Push — Blob Checkpointing

## Problem

Large vault pushes (300 MB+, files including `.mp4` videos ~40 MB each) failed
consistently with HTTP 503 at the multipart finalisation step:

```
▸ Uploading large blob (40.3 MB) part 5/5
error: network or I/O failure — HTTP Error 503: Service Unavailable
  at /usr/lib/python3.12/urllib/request.py:639 in http_error_default
```

The push was monolithic — one failure aborted everything. Small files in the same
commit (markdown, JSON) could not be pushed either. Retrying started from scratch
and re-uploaded all parts of every blob.

## Root Cause

`build_push_operations()` in `Vault__Batch` uploaded large blobs (presigned S3
multipart) and small blobs (batch) and commits/trees/ref all in a single pass with
no checkpoint state. A 503 at `presigned_complete` — after all S3 parts landed —
left no record of partial success. The next retry re-initiated the multipart upload
from the beginning.

## Solution: Two-Phase Push with Per-Blob Checkpoint

Push is now split into two phases:

### Phase A — Blobs (immutable, resumable)

1. Compute the full set of new blobs (not already in the named branch).
2. Upload **large blobs first** via presigned S3 multipart — highest 503 exposure.
3. Upload **small blobs** together in a single batch.
4. After each large blob's `presigned_complete` succeeds, checkpoint its `blob_id`
   to `.sg_vault/local/push_state.json`.
5. After the small blob batch succeeds, checkpoint all their IDs.

Checkpoint format:
```json
{
  "vault_id": "find-mill-5524",
  "clone_commit_id": "obj-cas-imm-...",
  "blobs_uploaded": ["obj-cas-imm-aaa", "obj-cas-imm-bbb"]
}
```

### Phase B — Commits, Trees, Ref (fast, CAS-atomic)

`build_push_operations()` receives the already-uploaded blob IDs as `named_blob_ids`,
so it skips blob uploads entirely. Only commits, tree objects, and the CAS ref update
go into this batch. Small files are no longer blocked by large blob failures.

On success, `push_state.json` is deleted. On retry, it is reloaded and matched
against the current `vault_id + clone_commit_id` — stale state (different commit)
is discarded.

## Files Changed

| File | Change |
|------|--------|
| `sgit_ai/sync/Vault__Storage.py` | Added `push_state_path(directory)` |
| `sgit_ai/sync/Vault__Sync.py` | `push()` split into Phase A + Phase B; added `_load_push_state`, `_save_push_state`, `_clear_push_state` |
| `tests/unit/sync/test_Vault__Batch.py` | Updated batch-count assertions to reflect two-phase batching |

## Production Confirmation (24 April 2026)

Vault `find-mill-5524` on `dev.send.sgraph.ai`. Two `.mp4` files (~40 MB and ~28 MB).

**First attempt:** Failed at `presigned_complete` for the first large blob (503).

**Immediate retry:** CLI reported `1 already uploaded` — the 40.3 MB blob was
skipped. The 27.9 MB blob uploaded cleanly. All 4 pending commits (vault-screenshots,
video folder pages, infographics) pushed successfully.

```
▸ Blobs: 1/2 to upload, 1 already uploaded
▸ Uploading large blob (27.9 MB) part 1/5
...
▸ Uploading large blob (27.9 MB) part 5/5
▸ Uploading objects  4 object(s)
Pushed 4 commit(s) → branch-named-...
```

The two-phase approach (blobs first with checkpointing, then commits + ref in a
fast batch) confirmed working in a real 503-failure scenario.

## Known Gaps

1. **503 at `presigned_complete` within one blob** — all 5 parts re-upload on
   retry (no per-part checkpoint). The blob is only saved to `push_state.json`
   after `presigned_complete` succeeds. Acceptable trade-off for now.

2. **Blob already on server but not in named tree** — if a file was deleted from
   the named branch in a prior commit but its blob remains on the server, the CLI
   re-uploads it on the next push containing that content. Requires a
   "check server for existing blob" API to fix.
