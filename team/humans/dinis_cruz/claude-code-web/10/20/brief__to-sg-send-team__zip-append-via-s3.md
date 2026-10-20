# Brief to the SG/Send team: append to a vault object on S3 without re-uploading it, and conditional completes

**From:** the sgit CLI agent, 20 Oct 2026, with Dinis's go-ahead. **Server read:** `sgraph_ai_app_send`
0.34.0, `lambda__user/service/Service__Vault__Presigned.py` and `fast_api/routes/Routes__Vault__Presigned.py`.
**Why:** the CLI is going to try a storage mode where a vault's immutable objects live in one, two or three
zip files on S3, read and written **directly against S3 with presigned URLs**, with only the small
mutable objects (ref, branch index) going through the ordinary routes. The read half already works
(tested 20 Oct: `read-url` + `Range` answers `206`). The write half needs one new route and one
parameter, both below. Everything else stays as it is.

## What exists, verified on `dev.send.sgraph.ai` on 20 Oct

| Route | Does | Tested |
|---|---|---|
| `POST /api/vault/presigned/initiate/{vault_id}` | `create_multipart_upload` + one presigned `upload_part` URL per 10 MB part | 12.6 MB object, 2 parts, PUT straight to S3 |
| `POST /api/vault/presigned/complete/{vault_id}` | `complete_multipart_upload` | ok |
| `POST /api/vault/presigned/cancel/{vault_id}` | `abort_multipart_upload` | not exercised |
| `GET /api/vault/presigned/read-url/{vault_id}/{file_id}` | presigned GET | `Range: bytes=0-1023`, `bytes=-2048`, a middle slice: all `206`, bytes correct |

Not present: any `upload_part_copy`, and any `IfMatch` / `IfNoneMatch` on complete.

## Ask 1: `POST /api/vault/presigned/append/{vault_id}`

Start a multipart upload whose first bytes are **copied server-side from an existing object**
(`UploadPartCopy`), so a client can grow a large object by uploading only its new tail.

**Request** (write key header as on `initiate`):

```json
{
  "source_file_id":  "bare/pack/data-0001.zip",   // the object to copy the prefix from
  "file_id":         "bare/pack/data-0001.zip",   // the target; same as source = append in place, or a new name
  "expected_etag":   "\"43187a65…-2\"",           // the source's ETag the client last saw
  "copy_bytes":      430392414,                   // how many leading bytes of the source to keep
  "tail_size_bytes": 3100000,                     // what the client will upload after them
  "num_tail_parts":  0                            // 0 = server picks (10 MB parts), as initiate does
}
```

**Server, in order:**

1. Validate the write key (as `initiate`); validate the ids as `initiate` does.
2. `head_object(source)`; if `ETag != expected_etag` → `412 {"error": "etag_mismatch", "etag": "<current>"}`.
   If `copy_bytes > ContentLength` → `400`. If `copy_bytes < 5 MiB` → `400 {"error": "too_small_to_copy"}`
   (S3 needs every non-final part ≥ 5 MiB; the client then rewrites the object whole, which at that
   size is cheap).
3. `create_multipart_upload(target)`.
4. Split `[0, copy_bytes)` into copy parts: `k = ceil(copy_bytes / COPY_PART_MAX)` parts of
   `ceil(copy_bytes / k)` bytes each (all ≥ 5 MiB). For each, `upload_part_copy(Bucket, Key=target,
   UploadId, PartNumber=i, CopySource={'Bucket': bucket, 'Key': source_key},
   CopySourceRange='bytes=a-b', CopySourceIfMatch=expected_etag)`. Record the returned ETags.
   `COPY_PART_MAX`: start at 1 GiB, not 5 GiB. The copy is server-side but the call blocks until it
   is done; API Gateway cuts a Lambda at 29 s, and S3 copies at a few hundred MB/s. A 430 MB prefix
   is one part and a few seconds; a 20 GB one is twenty calls, which this route should do in parallel
   threads, as the existing code does nothing in parallel.
5. Generate presigned `upload_part` URLs for the tail parts, numbered after the copy parts.
6. Return:

```json
{
  "upload_id":   "…",
  "copied":      [{"part_number": 1, "etag": "…"}],             // the client passes these back on complete
  "part_urls":   [{"part_number": 2, "upload_url": "…"}],       // tail parts
  "part_size":   10485760
}
```

The client uploads the tail parts and calls `complete` with the copied parts and its own.

## Ask 2: conditional complete

`POST /api/vault/presigned/complete/{vault_id}` gains two optional fields, passed straight to
`complete_multipart_upload`:

```json
{ "file_id": "...", "upload_id": "...", "parts": [...],
  "if_match":      "\"<etag>\"",     // in-place append: fail unless the target still has this ETag
  "if_none_match": "*" }             // new immutable name: fail if it already exists
```

Map S3's `PreconditionFailed` to `412 {"error": "precondition_failed"}` and abort the multipart
upload on that path (or leave it for `cancel`; say which). These two headers are what give the
zip its compare-and-swap, the same rule the ref already has in the batch route. boto3 has
supported `IfMatch` on `CompleteMultipartUpload` since late 2024 and `IfNoneMatch='*'` since
August 2024; the current pin is likely fine, please check.

## Ask 3 (small): size and ETag with the read URL

`read-url` currently returns the URL only. Add `size` and `etag` from one `head_object` (or a
separate `GET /api/vault/presigned/head/{vault_id}/{file_id}`), so a client reading a zip's tail
by `Range` does not need its own `HEAD` first, and an appender learns the ETag it must present.
Range support needs nothing: it is S3's.

## Limits to state in the API docs

- Object size up to S3's 5 TB; parts 5 MiB to 5 GiB, 10,000 per upload; presigned URL expiry as today.
- One in-place append at a time per object: the second one fails on `if_match` and must re-read the
  ETag and copy again. That is the design, not a bug.
- `copy_bytes` under 5 MiB cannot be appended to; rewrite whole.
- Nothing about these routes is readable by the server: the objects are ciphertext; the server copies
  bytes it cannot read.

## Tests we would like to see in the server's suite

1. Append in place: a 12 MB object, append 1 MB, `if_match` current ETag → new ETag, size 13 MB,
   bytes `[0, 12 MB)` unchanged, tail present.
2. Append to a new name with `if_none_match: "*"` twice → second is `412`.
3. Stale `expected_etag` → `412` on `append`, nothing created.
4. `copy_bytes` of 1 MB → `400 too_small_to_copy`.
5. Two clients appending in place from the same ETag → exactly one succeeds.
6. `read-url` + `Range` → `206` with the right `Content-Range` (regression for what works today).

## What the CLI will do with it (so the shape fits)

Storage mode `pack`: `bare/pack/data-NNNN.zip` holds the immutable objects (`ZIP_STORED`, sorted,
deterministic, append-only, Zip64); `refs/`, `indexes/` and `cache/` stay as today. Push = `append`
of the new members plus the rewritten central directory (a few MB), `complete` with `if_match`, then
the ordinary ref CAS. Pull = `Range` for the new tail (from the last known directory offset to the end),
then the ref. Clone = one GET (or a few parallel ranges) per zip, no listing, no walk. Then the
performance tests Dinis asked for: full clone of the 35k-object vault as one GET against the batch
route; append loops at 1, 10 and 100 MB tails on a 500 MB zip; incremental pulls; two appenders racing.
