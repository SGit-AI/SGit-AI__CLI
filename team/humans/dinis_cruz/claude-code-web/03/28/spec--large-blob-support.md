# Spec: Large Blob Support in sgit (Upload + Download)

**Date:** 2026-03-28
**Status:** Draft
**Problem:** Files larger than ~4.7 MB fail on `sgit push`. Files larger than ~5.7 MB will fail on `sgit pull` / checkout.

---

## Root Cause

All vault read/write endpoints route through AWS Lambda (RequestResponse invocation). API Gateway **base64-encodes binary request bodies** before invoking Lambda, adding ~33% overhead.

```
Upload limit:   6,291,456 bytes (Lambda) / 1.33 (base64) ≈ 4.7 MB max safe blob
Download limit: 6,291,456 bytes (Lambda response, no base64 overhead) ≈ 5.7 MB max safe blob
```

---

## Current Flows (What Works Today)

### Normal Write (blob ≤ ~4.7 MB)

```
Client                  API Gateway             Lambda              S3
  │                         │                      │                │
  │  PUT /api/vault/write/  │                      │                │
  │  {vault_id}/{file_id}   │                      │                │
  │  Body: raw bytes 4MB    │                      │                │
  │─────────────────────────►                      │                │
  │                         │  Invoke Lambda        │                │
  │                         │  Event: {             │                │
  │                         │    body: base64(4MB)  │                │
  │                         │    = ~5.3MB event     │                │
  │                         │  }                    │                │
  │                         │──────────────────────►│                │
  │                         │                       │  s3.put(blob)  │
  │                         │                       │───────────────►│
  │                         │                       │◄───────────────│
  │                         │  { statusCode: 200 }  │                │
  │◄────────────────────────────────────────────────│                │
  │  { status: "ok" }       │                       │                │
```

### What Breaks (blob > ~4.7 MB)

```
Client                  API Gateway             Lambda
  │                         │                      │
  │  PUT /api/vault/write/  │                      │
  │  Body: raw bytes 5.2MB  │                      │
  │─────────────────────────►                      │
  │                         │  Invoke Lambda        │
  │                         │  Event: {             │
  │                         │    body: base64(5.2MB)│
  │                         │    = ~6.9MB event     │  ← EXCEEDS 6MB
  │                         │  }                    │
  │                         │──────────────────────►│
  │                         │  413 Request Entity   │
  │                         │  Too Large            │
  │◄────────────────────────│                       │
  │  HTTP 413               │                       │
```

### Normal Read (blob ≤ ~5.7 MB)

```
Client                  API Gateway             Lambda              S3
  │                         │                      │                │
  │  GET /api/vault/read/   │                      │                │
  │  {vault_id}/{file_id}   │                      │                │
  │─────────────────────────►                      │                │
  │                         │──────────────────────►│                │
  │                         │                       │  s3.get(blob)  │
  │                         │                       │───────────────►│
  │                         │                       │  5.2MB bytes   │
  │                         │                       │◄───────────────│
  │                         │  Response body: 5.2MB │                │
  │                         │  (no base64 on return)│                │
  │◄────────────────────────────────────────────────│                │
  │  5.2MB bytes            │                       │                │
  │  (works — under 6MB     │                       │                │
  │   response limit)       │                       │                │
```

### Batch Write (small objects, push flow)

```
Client                  API Gateway             Lambda              S3
  │                         │                      │                │
  │  POST /api/vault/batch/ │                      │                │
  │  Body: JSON {           │                      │                │
  │    operations: [        │                      │                │
  │      {op:"write",       │                      │                │
  │       file_id:"bare/data/abc",                 │                │
  │       data: base64(blob)},  ← already b64      │                │
  │      {op:"write-if-match",  ← CAS on ref       │                │
  │       file_id:"bare/refs/X",                   │                │
  │       data:..., match:...}  │                  │                │
  │    ]                    │                      │                │
  │  }                      │                      │                │
  │─────────────────────────►                      │                │
  │                         │─ Invoke Lambda ──────►│                │
  │                         │                       │  s3.put(×N)   │
  │                         │                       │──────────────►│
  │                         │  { status:"ok" }      │               │
  │◄────────────────────────────────────────────────│               │
```

> **Note:** Batch bodies are JSON with base64-encoded blobs (already 33% larger). A batch containing a 4 MB blob sends ~5.3 MB of JSON, then API Gateway base64-encodes the *JSON body itself* → ~7 MB Lambda event → also 413. So large blobs fail in batch even faster than in individual writes.

---

## Server-Confirmed Capabilities

`GET /api/presigned/capabilities` returns:

```json
{
  "presigned_upload":   true,
  "multipart_upload":   true,
  "presigned_download": true,
  "direct_upload":      true,
  "max_part_size":      10485760,
  "min_part_size":       5242880,
  "max_parts":           10000
}
```

These already exist for the share/token flow (`transfer_id`). We need vault-scoped equivalents.

---

## Proposed New Server Endpoints

Three new vault-scoped endpoints, mirroring the existing `/api/presigned/` surface:

```
POST   /api/vault/presigned/initiate/{vault_id}
POST   /api/vault/presigned/complete/{vault_id}
GET    /api/vault/presigned/read-url/{vault_id}/{file_id}
```

---

## Proposed Flows (Large Blob)

### Large Blob Upload (blob > 4 MB, single part)

```
Client              API Gateway          Lambda             S3
  │                      │                  │               │
  │ POST /api/vault/      │                  │               │
  │ presigned/initiate/   │                  │               │
  │ {vault_id}            │                  │               │
  │ { file_id,            │                  │               │
  │   file_size_bytes,    │                  │               │
  │   num_parts: 1 }      │                  │               │
  │──────────────────────►│─── Invoke ──────►│               │
  │                       │                  │ CreateMulti-  │
  │                       │                  │ partUpload()  │
  │                       │                  │──────────────►│
  │                       │                  │ {upload_id}   │
  │                       │                  │◄──────────────│
  │                       │                  │ GeneratePresigned
  │                       │                  │ UploadPartUrl │
  │                       │                  │──────────────►│
  │                       │                  │ {upload_url}  │
  │                       │                  │◄──────────────│
  │ { upload_id,          │                  │               │
  │   parts: [{           │                  │               │
  │     part_number: 1,   │                  │               │
  │     upload_url: "https://s3.../..."      │               │
  │   }] }                │                  │               │
  │◄──────────────────────│◄─────────────────│               │
  │                       │                  │               │
  │  PUT {upload_url}     │                  │               │
  │  Body: 5.2MB blob     │                  │               │  ← direct to S3,
  │───────────────────────────────────────────────────────── ►│     no Lambda!
  │                       │                  │               │
  │  ETag: "abc123"       │                  │               │
  │◄──────────────────────────────────────────────────────── │
  │                       │                  │               │
  │ POST /api/vault/      │                  │               │
  │ presigned/complete/   │                  │               │
  │ {vault_id}            │                  │               │
  │ { file_id,            │                  │               │
  │   upload_id,          │                  │               │
  │   parts: [{           │                  │               │
  │     part_number: 1,   │                  │               │
  │     etag: "abc123"    │                  │               │
  │   }] }                │                  │               │
  │──────────────────────►│─── Invoke ──────►│               │
  │                       │                  │ CompleteMulti-│
  │                       │                  │ partUpload()  │
  │                       │                  │──────────────►│
  │                       │                  │◄──────────────│
  │  { status: "ok" }     │                  │               │
  │◄──────────────────────│◄─────────────────│               │
```

### Large Blob Upload (multipart, blob > 10 MB)

```
Client                                              S3
  │                                                  │
  │  1. POST /api/vault/presigned/initiate           │
  │     { file_id, size: 50MB, num_parts: 5 }        │
  │     → { upload_id, parts: [                      │
  │          {part:1, url:"s3://...?partNumber=1"},   │
  │          {part:2, url:"s3://...?partNumber=2"},   │
  │          ...                                      │
  │        ] }                                        │
  │                                                  │
  │  2. Split encrypted blob into 5 × 10MB chunks    │
  │                                                  │
  │  3. PUT {url_1} body=chunk_1 (10MB) ────────────►│ ETag1
  │     PUT {url_2} body=chunk_2 (10MB) ────────────►│ ETag2
  │     PUT {url_3} body=chunk_3 (10MB) ────────────►│ ETag3
  │     PUT {url_4} body=chunk_4 (10MB) ────────────►│ ETag4
  │     PUT {url_5} body=chunk_5 (10MB) ────────────►│ ETag5
  │     (all direct to S3 — no Lambda involved)      │
  │                                                  │
  │  4. POST /api/vault/presigned/complete           │
  │     { file_id, upload_id,                        │
  │       parts: [{part:1,etag:ETag1}, ...] }        │
  │     → { status: "ok" }   (Lambda, tiny payload)  │
```

### Large Blob Download

```
Client              API Gateway          Lambda             S3
  │                      │                  │               │
  │  GET /api/vault/     │                  │               │
  │  presigned/read-url/ │                  │               │
  │  {vault_id}/{file_id}│                  │               │
  │──────────────────────►─── Invoke ──────►│               │
  │                       │                 │ GeneratePresigned
  │                       │                 │ GetObjectUrl  │
  │                       │                 │──────────────►│
  │                       │                 │ {url, expiry} │
  │                       │                 │◄──────────────│
  │  { url: "https://s3.../...?X-Amz-...",  │               │
  │    expires_in: 3600 } │                 │               │
  │◄──────────────────────│◄────────────────│               │
  │                       │                 │               │
  │  GET {url}            │                 │               │
  │  (direct to S3,       │                 │               │
  │   no Lambda involved) │                 │               │
  │────────────────────────────────────────────────────────►│
  │                       │                 │               │
  │  5.2MB encrypted blob │                 │               │
  │◄────────────────────────────────────────────────────────│
  │                       │                 │               │
  │  decrypt → plaintext  │                 │               │
  │  write to working dir │                 │               │
```

---

## Tree Metadata Change

### Why the tree is the right place for the routing flag

The tree is read **before** any blobs are fetched. Storing `large: true` here lets the client choose the presigned download path proactively — no wasted attempt on the normal read path.

What **not** to store in the tree:
- Presigned URLs (they expire in hours; the tree is immutable forever)
- S3 paths (server-internal concern)

### Current tree entry

```json
{ "path": "report.pdf", "blob_id": "abc123...", "mode": "file", "size": 5200000 }
```

### Proposed tree entry

```json
{ "path": "report.pdf", "blob_id": "abc123...", "mode": "file", "size": 5200000, "large": true }
```

`large: true` means: *this blob was stored via the presigned upload path; use presigned download to retrieve it.*

### Schema

```python
class Schema__Tree_Entry(Type_Safe):
    path    : Safe_Str__File_Path
    blob_id : Safe_Str__Object_Id = None
    mode    : Safe_Str__File_Mode
    size    : Safe_UInt__File_Size     # plaintext bytes
    large   : bool = False             # NEW: use presigned S3 path
```

---

## Client Decision Tree

### At push time

```
for each blob in commit:
    │
    ├── len(encrypted_blob) ≤ 4 MB ?
    │       │
    │       └── YES → add to batch operations (existing path)
    │
    └── NO (large blob):
            │
            └── presigned upload flow:
                    1. POST /api/vault/presigned/initiate
                       { file_id, file_size_bytes, num_parts }
                    │
                    ├── num_parts = 1  (blob ≤ 10 MB)
                    │       PUT presigned_url ← blob
                    │
                    └── num_parts = N  (blob > 10 MB)
                            split blob into N × 10MB chunks
                            PUT presigned_url[i] ← chunk[i]  (parallel ok)
                            collect ETags
                    │
                    └── POST /api/vault/presigned/complete
                            { file_id, upload_id, parts:[{part,etag}] }

also set tree_entry["large"] = True for this blob
```

### At pull/checkout time

```
for each entry in tree:
    │
    ├── entry["large"] == False (or absent)?
    │       │
    │       └── YES → GET /api/vault/read/{vault_id}/{blob_id}  (existing path)
    │
    └── NO (large blob):
            │
            └── GET /api/vault/presigned/read-url/{vault_id}/{blob_id}
                    → { url, expires_in }
                GET {url}  ← direct S3, no Lambda
                decrypt → write file

fallback: if normal read returns 413 (pre-flag blobs committed before this change):
    → retry via presigned read-url
```

---

## New `Vault__API` Methods (Client)

```python
LARGE_BLOB_THRESHOLD = 4 * 1024 * 1024   # 4 MB

def presigned_initiate(self, vault_id: str, file_id: str,
                       file_size_bytes: int, num_parts: int,
                       write_key: str) -> dict:
    """POST /api/vault/presigned/initiate/{vault_id}
    Returns { upload_id, parts: [{part_number, upload_url}] }"""

def presigned_upload_part(self, upload_url: str, data: bytes) -> str:
    """PUT directly to S3 presigned URL.
    Returns ETag from response header (needed for complete call)."""

def presigned_complete(self, vault_id: str, file_id: str,
                       upload_id: str, parts: list,
                       write_key: str) -> dict:
    """POST /api/vault/presigned/complete/{vault_id}
    parts = [{ part_number: int, etag: str }]"""

def presigned_read_url(self, vault_id: str, file_id: str) -> dict:
    """GET /api/vault/presigned/read-url/{vault_id}/{file_id}
    Returns { url: str, expires_in: int }"""

def read_large(self, vault_id: str, file_id: str) -> bytes:
    """Fetch a large blob via presigned read URL (direct S3, no Lambda)."""
    url_info = self.presigned_read_url(vault_id, file_id)
    req      = Request(url_info['url'], method='GET')
    with urlopen(req) as resp:
        return resp.read()
```

---

## Implementation Phases

**Phase 1 — Server** (server team adds 3 new endpoints)
```
POST /api/vault/presigned/initiate/{vault_id}
POST /api/vault/presigned/complete/{vault_id}
GET  /api/vault/presigned/read-url/{vault_id}/{file_id}
```

**Phase 2 — Client: upload**
- `Vault__API`: add `presigned_initiate`, `presigned_upload_part`, `presigned_complete`
- `Vault__Batch.execute_batch()`: extract large blobs, upload via presigned flow before batching small ops
- `Vault__Batch.execute_individually()`: route large blobs via presigned flow

**Phase 3 — Client: tree metadata**
- Add `large: bool` to `Schema__Tree_Entry` (default `False`)
- Set `large=True` in `Vault__Commit` when `len(encrypted_blob) > LARGE_BLOB_THRESHOLD`

**Phase 4 — Client: download**
- `Vault__API`: add `presigned_read_url`, `read_large`
- `Vault__Fetch` / checkout: check `entry['large']` → use `read_large()`
- Add 413 fallback for blobs committed before Phase 3 (no flag)

---

## Open Questions for Server Team

1. **Auth on presigned upload URLs** — the client PUTs directly to S3. Does the presigned URL embed all auth, or does the client need to include the vault write key in the S3 PUT?

2. **Read URL TTL** — how long should presigned read URLs be valid? 1 hour is S3 default. Should the client cache the URL within a session, or fetch a fresh one per checkout?

3. **Does `/api/vault/zip` bypass Lambda?** — this was our temporary workaround. Need confirmation whether it goes directly to S3 (in which case it can serve as a bridge while server implements Phase 1) or also invokes Lambda (in which case there is currently no working path for large blobs).

4. **`size` field semantics** — tree entry `size` is plaintext bytes. Encrypted blob is `size + 28` bytes (12-byte nonce + 16-byte AES-GCM tag). The threshold check should use the encrypted size. Should `size` remain plaintext-only, or should we add `encrypted_size`?
