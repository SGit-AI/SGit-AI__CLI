# Vault Batch API — Implementation Brief

**Date:** 16 April 2026
**From:** SGit/CLI team
**To:** Any agent or client making vault API calls
**Purpose:** Replace individual per-file API calls with the batch endpoint to reduce round-trips, latency, and rate-limit exposure

---

## The Problem This Solves

Every individual vault read/write is a full HTTP round-trip: ~150–400 ms each on the live server. A clone of a 50-file vault with individual reads takes 50 × 200 ms = 10+ seconds. The same clone with batch reads takes 2–3 requests = under 1 second. Any agent that calls `GET /api/vault/read/{vault_id}/{file_id}` or `PUT /api/vault/write/{vault_id}/{file_id}` in a loop should switch to batch.

---

## The Endpoint

```
POST /api/vault/batch/{vault_id}
Content-Type: application/json
x-sgraph-vault-write-key: {write_key}   ← required only for write/delete ops
x-sgraph-access-token: {access_token}   ← required only for write/delete ops
```

**Request body:**
```json
{
  "operations": [
    { "op": "read",          "file_id": "bare/data/obj-cas-imm-abc123" },
    { "op": "write",         "file_id": "bare/data/obj-cas-imm-def456", "data": "<base64>" },
    { "op": "write-if-match","file_id": "bare/refs/ref-pid-muw-xyz",    "data": "<base64>", "match": "<base64-of-current-content>" },
    { "op": "delete",        "file_id": "bare/data/obj-cas-imm-old789" }
  ]
}
```

**Response body:**
```json
{
  "status": "ok",
  "results": [
    { "file_id": "bare/data/obj-cas-imm-abc123", "status": "ok", "data": "<base64>" },
    { "file_id": "bare/data/obj-cas-imm-def456", "status": "ok" },
    { "file_id": "bare/refs/ref-pid-muw-xyz",    "status": "ok" },
    { "file_id": "bare/data/obj-cas-imm-old789", "status": "ok" }
  ]
}
```

---

## Operation Types

### `read`
Fetch a file. No write key required. The response `data` field is the raw file bytes, base64-encoded.

```json
{ "op": "read", "file_id": "bare/data/obj-cas-imm-abc123" }
```

Result: `{ "status": "ok", "data": "<base64-bytes>" }` or `{ "status": "not_found" }`.

### `write`
Idempotent overwrite. Requires write key. `data` is base64-encoded bytes.

```json
{ "op": "write", "file_id": "bare/data/obj-cas-imm-def456", "data": "<base64>" }
```

Used for immutable content-addressed objects (data blobs, commit objects, tree objects) where idempotency is safe. Never use `write` for mutable refs — use `write-if-match` instead.

### `write-if-match` (CAS)
Compare-and-swap. Atomically updates a file only if its current content matches `match`. If `match` is omitted, the write succeeds only if the file **does not exist** (create-only).

```json
{
  "op": "write-if-match",
  "file_id": "bare/refs/ref-pid-muw-abc",
  "data": "<base64-of-new-content>",
  "match": "<base64-of-current-content>"
}
```

If the CAS check fails, the **entire batch is rejected** (HTTP 412). All writes in the batch are rolled back. This is how the CLI prevents concurrent push conflicts: only one client can win.

### `delete`
Remove a file. Requires write key.

```json
{ "op": "delete", "file_id": "bare/data/obj-cas-imm-old789" }
```

---

## Server Limits

| Limit | Value | Consequence |
|-------|-------|-------------|
| Max operations per batch | **100** | HTTP 400 `{"detail":"Too many operations (max 100)"}` |
| Max request body | ~6 MB | HTTP 413 or Lambda timeout |
| Base64 data budget (CLI uses) | 4 MB per chunk | Safe margin under body limit |

**Rule of thumb:** keep each batch to **≤ 50 operations** and **≤ 4 MB of base64 data**. The CLI uses 50 as its cap (half the server limit) to leave headroom.

---

## How the CLI Uses Batch

### Reading: `batch_read(vault_id, file_ids)`

All read operations go through `Vault__API.batch_read()`, which auto-chunks any list of file IDs at 50 per request:

```python
# Vault__API.batch_read() — simplified
def batch_read(self, vault_id, file_ids):
    payloads = {}
    for chunk in chunks_of(file_ids, MAX_BATCH_OPS):  # MAX_BATCH_OPS = 50
        ops    = [{'op': 'read', 'file_id': fid} for fid in chunk]
        result = self.api.batch(vault_id, write_key=None, operations=ops)
        for r in result['results']:
            payloads[r['file_id']] = base64.b64decode(r['data']) if r['status'] == 'ok' else None
    return payloads
```

**Clone uses batch_read in 6 phases:**

```
Phase 1: batch_read([index_fid])                      ← 1 op: branch index
Phase 2: batch_read([ref_fid, key_fid, ...])           ← N ops: all branch refs + public keys
Phase 3: batch_read([commit_fid, ...])                 ← BFS wave: commits
Phase 4: batch_read([tree_fid, ...])                   ← BFS wave: tree objects
Phase 5: (local) flatten trees to collect blob IDs
Phase 6: batch_read(blob_fids, chunked by 3 MB resp)   ← parallel chunks: file blobs
Phase 7: presigned S3 GET for blobs > 4 MB             ← parallel: large blobs
```

Total requests for a 50-file vault with ~10 commits: **~10–15 requests** instead of 60+.

### Writing: `execute_batch(vault_id, write_key, operations)`

Push builds a single operations list and hands it to `Vault__Batch.execute_batch()`, which handles chunking:

```python
# Vault__Batch.execute_batch() — chunking logic
MAX_B64_BYTES = 4 * 1024 * 1024   # 4 MB per chunk
MAX_BATCH_OPS = 50                  # 50 ops per chunk

for op in all_operations:
    if chunk is full (size OR count):
        flush chunk
    add op to chunk

# Plain write chunks → parallel via ThreadPoolExecutor
# write-if-match chunks → sequential (must be last, atomicity)
```

**Push sends in one batch:**
```
[write blob1, write blob2, ..., write tree, write commit, write-if-match ref]
```

If the write-if-match fails (someone else pushed first), the whole batch is rejected → 412 → CLI prompts to pull first.

**Fallback:** if the batch endpoint is unavailable, `execute_individually()` sends each operation as a separate API call. No atomicity guarantees in fallback mode.

---

## Practical Guidance for Agents

### Doing a read-only vault scan

Instead of:
```python
for path in file_list:
    data = api.read(vault_id, path)   # 1 request per file → very slow
```

Do:
```python
# All at once, auto-chunked at 50
results = api.batch_read(vault_id, file_list)
for path, data in results.items():
    if data:
        process(path, data)
```

### Downloading a commit + its tree in one shot

```python
batch_result = api.batch_read(vault_id, [
    f'bare/data/{commit_id}',
    f'bare/data/{tree_id}',
    f'bare/refs/{named_ref_id}',
])
commit_bytes = batch_result[f'bare/data/{commit_id}']
tree_bytes   = batch_result[f'bare/data/{tree_id}']
ref_bytes    = batch_result[f'bare/refs/{named_ref_id}']
```

### Writing multiple files + updating the ref atomically

```python
import base64

operations = []
for blob_id, ciphertext in new_blobs.items():
    operations.append({
        'op':      'write',
        'file_id': f'bare/data/{blob_id}',
        'data':    base64.b64encode(ciphertext).decode()
    })

# CAS ref update must be last; the batch is atomic
operations.append({
    'op':      'write-if-match',
    'file_id': f'bare/refs/{named_ref_id}',
    'data':    base64.b64encode(new_ref_ciphertext).decode(),
    'match':   base64.b64encode(current_ref_bytes).decode()  # omit for first write
})

# POST /api/vault/batch/{vault_id}
response = api.batch(vault_id, write_key, operations)
```

If the CAS fails (HTTP 412), fetch the latest ref and retry.

---

## What NOT to Do

| Anti-pattern | Why | Instead |
|---|---|---|
| `GET /api/vault/read/{id}` in a loop | 1 round-trip per file | `batch_read([id1, id2, ...])` |
| `PUT /api/vault/write/{id}` in a loop | Same; no atomicity | `batch([write, write, write-if-match])` |
| Batch with > 100 ops | HTTP 400 | Split into ≤ 50-op chunks |
| Plain `write` for mutable refs | Silent overwrite, data loss | `write-if-match` with CAS |
| Ignore 412 on write-if-match | Silently overwrites another push | Pull, re-merge, retry |

---

## The `file_id` Namespace

All file IDs are relative paths within the vault's `bare/` directory:

| Path prefix | Contents | Mutability |
|---|---|---|
| `bare/data/obj-cas-imm-{hash}` | Encrypted blobs, commits, trees | Immutable (write once) |
| `bare/refs/ref-pid-{type}-{id}` | Branch head pointers | Mutable — always use `write-if-match` |
| `bare/indexes/{id}` | Branch index | Mutable — always use `write-if-match` |
| `bare/keys/{id}` | Public keys | Write once, then immutable |

The `obj-cas-imm-` prefix in data object IDs is the CLI's signal that the object is immutable and safe to cache and to `write` idempotently.

---

## Quick Reference

```
POST /api/vault/batch/{vault_id}
Headers:
  Content-Type: application/json
  x-sgraph-vault-write-key: {key}   ← write/delete only
  x-sgraph-access-token: {token}    ← write/delete only

Body: { "operations": [ ... ] }

Ops:
  read            → no key required, returns data in result
  write           → requires key, idempotent overwrite
  write-if-match  → requires key + match field, atomic CAS, 412 on mismatch
  delete          → requires key

Limits:
  ≤ 50 ops per request (server hard limit: 100)
  ≤ 4 MB base64 data per request (server hard limit: ~6 MB)

On 412: another client won the CAS — pull and retry
On 400 "Too many operations": split into smaller chunks
```
