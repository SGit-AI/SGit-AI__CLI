## `_upload_large` in sgit_ai/core/actions/push/Vault__Batch.py (L109-L170)

**Purpose:** Upload one > 4 MB ciphertext through the server's S3 multipart flow: `presigned_initiate` → parallel `PUT` of each part to the URL the server named → `presigned_complete`; `presigned_cancel` on any failure. Returns False when the server has no presigned support, so the caller folds the blob into the normal batch.

**Inputs & Assumptions:**
- `vault_id`, `file_id` (`bare/data/<oid>` or, from `_upload_bare_to_server`, any `bare/...` path), `ciphertext` (bytes), `write_key`, `on_progress`.
- Host-supplied (via `presigned_initiate`'s response, Vault__API.py:L301-L313): `upload_id`, `part_size` (default `LARGE_PART_SIZE` 10 MB, L12, L124), `part_urls[i]['part_number']`, `part_urls[i]['upload_url']`. Trust: **untrusted**.

**Outputs & Effects:**
- Network: one authenticated POST to initiate; N PUTs of ciphertext slices to host-chosen https (or own-host/loopback http) URLs via `urlopen` with a 300 s timeout (L140-L147), **no API headers** on the PUTs (a fresh `Request`); one authenticated POST to complete; on failure a best-effort cancel (L165-L169) and re-raise.
- Debug log: logs `PUT <upload_url>` (L142) — the presigned URL (with its signature query) goes into the debug log entry's `url`.
- Returns True on success, False only for `'presigned_not_available'` in the initiate error text (L126-L128).

**Block-by-Block:**

```python
# L120-L129
try:
    result    = self.api.presigned_initiate(vault_id, file_id, len(ciphertext), num_parts, write_key)
    upload_id = result['upload_id']
    part_size = result.get('part_size', LARGE_PART_SIZE)
    part_urls = result['part_urls']
except RuntimeError as e:
    if 'presigned_not_available' in str(e): return False
    raise
```
- **What:** ask the server for part URLs; `num_parts` is the client's estimate (L118), the server may answer with its own count.
- **Assumes:** `result` has those keys (a `KeyError` is not a `RuntimeError` → propagates; `push` catches `Exception` around `execute_batch` but `_upload_large` in Phase A at Vault__Sync__Push.py:L289 is **not** wrapped, so a malformed initiate response aborts the push there).
- **Assumes:** the fallback signal is the literal substring `presigned_not_available` in the error (the in-memory double's message, Vault__API__In_Memory.py:L131). A live server without the feature must produce that text (or its 404 body must contain it, since `_api_error` embeds the body): `nothing found` for the live contract. Test: `test_Vault__Batch__Coverage.py::test_upload_large_presigned_not_available_returns_false`, `test_upload_large_presigned_other_error_reraises`.

```python
# L134-L148
def _put_part(part_info):
    part_num = part_info['part_number']
    start    = (part_num - 1) * part_size
    chunk    = ciphertext[start : start + part_size]
    self.api.check_presigned_url(part_info['upload_url'])
    req = Request(part_info['upload_url'], data=chunk, method='PUT')
    req.add_header('Content-Type', 'application/octet-stream')
    with urlopen(req, timeout=300) as resp:
        etag = resp.headers.get('ETag', '')
        ...
    return {'part_number': part_num, 'etag': etag}
```
- **What:** slice by the server's `part_size` and `part_number`, PUT to the server's URL after the scheme/host rule.
- **Assumes:** the server's `part_size`/`part_number` partition the ciphertext exactly; a wrong `part_size` silently produces overlapping or gapped slices and the assembled object would not hash to `file_id` — detected only by readers' `Vault__Verified_Write` later, never here: `nothing found`.
- **Assumes:** `urlopen` here uses the **default** SSL context (no `_ssl_context`), so the PUT verifies TLS even with `--no-verify-tls`; and follows redirects **without** re-checking the scheme (plain `urlopen`, no `Checked_Redirects` handler as in `fetch_presigned` L46-L51): a 3xx from the presigned host to an `http://` address would be followed for the PUT (with the ciphertext as body; urllib re-sends a PUT body? — stdlib `HTTPRedirectHandler` converts 301/302/303 to GET and drops the body, and 307/308 raise `HTTPError` for non-GET/HEAD; observation, see Open Questions). `nothing found` applying `check_presigned_url` to redirect hops on this path.
- **Establishes:** parts' ETags for `presigned_complete`.

```python
# L150-L170
try:
    if total_parts > 1:
        with ThreadPoolExecutor(max_workers=total_parts) as executor: ...
    else: completed_parts.append(_put_part(part_urls[0]))
    self.api.presigned_complete(vault_id, file_id, upload_id, completed_parts, write_key)
    return True
except Exception:
    try: self.api.presigned_cancel(vault_id, upload_id, file_id, write_key)
    except Exception: pass
    raise
```
- **What:** unbounded parallelism (one thread per part); complete; cancel-and-reraise on anything (including a refused URL `ValueError`).
- **Assumes:** `presigned_complete`'s success means the server stored the object under `file_id`; the response is not inspected (`nothing found`).

**Cross-Function Dependencies:**
- Callees: `Vault__API.presigned_initiate/complete/cancel` (L301-L337), `Vault__API.check_presigned_url` (L58-L71), `urllib.request.urlopen`.
- Callers: `build_push_operations` L54; `Vault__Sync__Push.push` L289 (Phase A, with per-blob checkpointing L291-L295); `Vault__Sync__Push._upload_bare_to_server` L808 (any large `bare/` file, including non-content-addressed ones).
- Tests: `test_Vault__Batch__Coverage.py::Test_Vault__Batch__UploadLarge` (stubbed `api`; the PUT itself is monkeypatched), `tests/unit/sync/test_Vault__Sync__Push__Coverage.py::Test_Vault__Sync__Push__LargeBlob`. No test drives a real PUT.

**Open Questions:**
- unclear; need to confirm stdlib `urllib` behaviour for a redirected `PUT` (307/308 → `HTTPError`; 301/302/303 → GET without body) to know whether the un-checked redirect on this path can deliver ciphertext anywhere other than the checked URL.
- unclear; whether the live server validates the completed object's hash against `file_id` at `presigned_complete`.
