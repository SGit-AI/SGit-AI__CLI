# Spec: Large Blob Support in sgit (Upload + Download)

**Date:** 2026-03-28
**Status:** Draft
**Problem:** Files larger than ~4.7 MB fail on `sgit push`. Files larger than ~5.7 MB will fail on `sgit pull` / checkout for the same underlying reason.

---

## Root Cause

All vault read/write endpoints route through AWS Lambda (RequestResponse invocation). API Gateway **base64-encodes binary request bodies** before invoking Lambda, adding ~33% overhead:

```
5.2 MB file  →  encrypted blob ~5.2 MB
             →  API Gateway base64-encodes  →  ~6.9 MB Lambda event
             →  Lambda RequestResponse limit: 6,291,456 bytes (~6 MB)
             →  HTTP 413
```

Lambda **response** bodies are not base64-encoded by API Gateway (returned as-is), so the limit on reads is effectively ~5.7 MB before Lambda's 6 MB response limit is hit.

```
Threshold     Limit
─────────     ─────────────────────────────────────────────
~4.7 MB       Upload fails  (6 MB / 1.33 base64 overhead)
~5.7 MB       Download fails (6 MB response limit, no overhead)
```

The `presigned/` API already supports direct S3 upload/download (no Lambda) — confirmed via `/api/presigned/capabilities`:

```json
{
  "presigned_upload":  true,
  "multipart_upload":  true,
  "presigned_download": true,
  "max_part_size":     10485760,   // 10 MB
  "min_part_size":     5242880,    //  5 MB
  "max_parts":         10000
}
```

But those endpoints use `transfer_id` (the share/token flow). We need vault-scoped equivalents.

---

## Required: New Server API Endpoints

### Upload (write)

```
POST /api/vault/presigned/initiate/{vault_id}
  Headers: x-sgraph-access-token, x-sgraph-vault-write-key
  Body:    { "file_id": "bare/data/{blob_id}",
             "file_size_bytes": 5200000,
             "num_parts": 1 }
  Returns: { "upload_id": "...",
             "parts": [{ "part_number": 1, "upload_url": "https://s3.../..." }] }
```

Client PUTs the encrypted blob directly to the S3 presigned URL (bypasses Lambda entirely).

```
POST /api/vault/presigned/complete/{vault_id}
  Headers: x-sgraph-access-token, x-sgraph-vault-write-key
  Body:    { "file_id":   "bare/data/{blob_id}",
             "upload_id": "...",
             "parts":     [{ "part_number": 1, "etag": "..." }] }
  Returns: { "status": "ok" }
```

### Download (read)

```
GET /api/vault/presigned/read-url/{vault_id}/{file_id}
  Headers: x-sgraph-access-token
  Returns: { "url": "https://s3.amazonaws.com/...?X-Amz-Expires=...",
             "expires_in": 3600 }
```

Client GETs the encrypted blob directly from the S3 URL (bypasses Lambda entirely).

### Multipart support (files > 10 MB)

For files larger than `max_part_size` (10 MB), the client splits the encrypted blob into parts and uses multiple `upload_url` entries from the initiate response.

---

## Tree Metadata Change

### Current tree entry format

```json
{
  "path":    "report.pdf",
  "blob_id": "abc123def456...",
  "mode":    "file",
  "size":    5200000
}
```

### Proposed addition: `"large": true`

```json
{
  "path":    "report.pdf",
  "blob_id": "abc123def456...",
  "mode":    "file",
  "size":    5200000,
  "large":   true
}
```

**Why the tree is the right place:**
- The tree is committed and immutable — it captures the fact that this blob was stored via the large path, permanently.
- No expiring URLs stored (just a routing flag).
- The client reads the tree before checking out files, so it knows *proactively* which blobs need the presigned download path — no wasted attempt on the normal read path.
- The `size` field is already there; `large` is redundant but explicit and removes the need to recalculate the threshold on every read.

**Why not store the presigned URL in the tree:**
- Presigned URLs expire (typically 1 hour to 7 days).
- The tree is immutable — a commit written today would have a stale URL tomorrow.
- Always fetch a fresh URL at download time via `/api/vault/presigned/read-url/`.

### Schema change

```python
class Schema__Tree_Entry(Type_Safe):
    path    : Safe_Str__File_Path
    blob_id : Safe_Str__Object_Id = None
    mode    : Safe_Str__File_Mode
    size    : Safe_UInt__File_Size
    large   : bool = False          # NEW: blob stored via presigned S3 path
```

---

## Client Changes

### Commit time (`Vault__Sync.commit`)

When building the tree, check each file's blob size before writing:

```python
LARGE_BLOB_THRESHOLD = 4 * 1024 * 1024   # 4 MB (already defined in Vault__API)

tree_entry = {
    'path':    relative_path,
    'blob_id': blob_id,
    'mode':    'file',
    'size':    len(plaintext),
    'large':   len(plaintext) > LARGE_BLOB_THRESHOLD,
}
```

Note: `size` is the **plaintext** size (pre-encryption). AES-GCM adds 28 bytes (12-byte nonce + 16-byte tag), so the encrypted blob is `size + 28` bytes. The threshold comparison should use the encrypted size since that's what gets uploaded.

### Push time (`Vault__Batch`)

Replace the current `write_large()` workaround (vault zip endpoint) with the proper presigned flow:

```
execute_batch() / execute_individually()
  │
  ├── blob <= 4 MB  →  existing batch/write path (unchanged)
  │
  └── blob >  4 MB  →  presigned upload flow:
        1. POST /api/vault/presigned/initiate/{vault_id}
           { file_id, file_size_bytes, num_parts }
        2. For each part: PUT directly to S3 presigned URL
        3. POST /api/vault/presigned/complete/{vault_id}
           { file_id, upload_id, parts: [{part_number, etag}] }
```

Multipart threshold (splits into parts):

```
blob size            num_parts    part size
─────────            ─────────    ─────────
4 MB – 10 MB         1            full blob
10 MB – 100 MB       10           ~10 MB each
100 MB – 1 GB        100          ~10 MB each
```

### Pull / checkout time (`Vault__Fetch` / `Vault__Sync`)

When restoring files from a commit, check `tree_entry['large']`:

```python
if entry.get('large'):
    # Get a fresh presigned S3 download URL
    url_info   = api.get_presigned_read_url(vault_id, f'bare/data/{blob_id}')
    ciphertext = urllib.request.urlopen(url_info['url']).read()
else:
    ciphertext = obj_store.load(blob_id)          # existing path
```

### Backward compatibility (existing large blobs without the flag)

Blobs committed before this change have `large: False` (default). If the normal read path returns HTTP 413 for such a blob, fall back to presigned read:

```python
try:
    ciphertext = api.read(vault_id, blob_id)
except RuntimeError as e:
    if '413' in str(e):
        url_info   = api.get_presigned_read_url(vault_id, f'bare/data/{blob_id}')
        ciphertext = urllib.request.urlopen(url_info['url']).read()
    else:
        raise
```

---

## New `Vault__API` Methods

```python
def presigned_initiate(self, vault_id: str, file_id: str,
                       file_size_bytes: int, num_parts: int,
                       write_key: str) -> dict:
    """POST /api/vault/presigned/initiate/{vault_id}"""
    ...

def presigned_upload_part(self, upload_url: str, part_data: bytes) -> str:
    """PUT directly to S3 presigned URL. Returns ETag from response headers."""
    ...

def presigned_complete(self, vault_id: str, file_id: str,
                       upload_id: str, parts: list,
                       write_key: str) -> dict:
    """POST /api/vault/presigned/complete/{vault_id}"""
    ...

def presigned_read_url(self, vault_id: str, file_id: str) -> dict:
    """GET /api/vault/presigned/read-url/{vault_id}/{file_id}
    Returns { url: str, expires_in: int }"""
    ...
```

---

## Implementation Phases

**Phase 1 — Server** (server team)
- Add `/api/vault/presigned/initiate/{vault_id}`
- Add `/api/vault/presigned/complete/{vault_id}`
- Add `/api/vault/presigned/read-url/{vault_id}/{file_id}`
- These mirror the existing `/api/presigned/` endpoints but are vault-scoped

**Phase 2 — Client: upload** (can ship once Phase 1 is done)
- Replace `write_large()` (vault zip workaround) with `presigned_initiate` → S3 PUT → `presigned_complete`
- Add `Vault__Batch.execute_presigned_upload()`
- Update `LARGE_BLOB_THRESHOLD` constant (already correct at 4 MB)

**Phase 3 — Client: tree metadata**
- Add `large: bool` to `Schema__Tree_Entry`
- Set `large=True` in `Vault__Commit` when blob size > threshold

**Phase 4 — Client: download**
- In `Vault__Fetch` / checkout, check `entry['large']` → use `presigned_read_url()`
- Add 413 fallback for old commits without the flag

---

## Open Questions

1. **Does `/api/vault/zip` bypass Lambda?** — we assumed yes (that's the current workaround), but if it also invokes Lambda synchronously, blobs between 4–10 MB are still broken today. Need server team to confirm.

2. **Auth for presigned S3 upload URLs** — the client PUTs directly to S3. Does S3 need the vault write key in a header, or is the presigned URL itself the auth token?

3. **Read URL TTL** — how long should presigned read URLs be valid? 1 hour is typical for S3, but vault blobs are permanent objects. Should we cache the URL within a session?

4. **Streaming reads** — for very large files (>100 MB), holding the full ciphertext in memory before decrypting is expensive. Do we want chunked AES-GCM streaming? (Current AES-GCM requires the full ciphertext to verify the tag — would need a chunked scheme like [nonce + encrypted_chunk + tag] × N.)

5. **`size` field accuracy** — tree entry `size` currently stores plaintext size. After encryption, the blob is `size + 28` bytes. The `large` flag threshold should be checked on the encrypted size. Clarify which `size` means in the schema.
