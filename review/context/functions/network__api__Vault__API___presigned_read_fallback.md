## `_presigned_read_fallback` in sgit_ai/network/api/Vault__API.py (L238-L264)

**Purpose:** Last resort in `batch_read` for a file the API cannot return (Lambda 502): ask the server for a presigned URL and GET it with `fetch_presigned`. Fail-soft: records a failure instead of raising.

**Inputs & Assumptions:**
- `fid` (str): requested id. `payloads`, `failures`: out-dicts.
- Response of `presigned_read_url` (host-supplied dict): `url` or `presigned_url` (L251). Trust: untrusted; the URL is checked by `fetch_presigned` → `check_presigned_url`.

**Outputs & Effects:**
- Success: `payloads[fid] = data` (L258) — the bytes from the presigned host, unverified here. Prints to stderr (L248, L259).
- Any exception: `payloads[fid] = None`, `failures[fid] = _classify_exception(...)` (L260-L264). `ValueError` from a refused URL lands here too (TRANSIENT, since the text has no 404/403).
- Debug log entry when `debug_log` is set (L254-L257): logs the S3 URL (which carries the signature in its query string) to the debug log's `url` field — `CLI__Debug_Log.log_request` L11-L21 stores `url`; `_print_entry` prints `_format_path(url)` (L41). Observation.

**Block-by-Block:**
```python
# L250-L255
url_info = self.presigned_read_url(vault_id, fid)
s3_url   = url_info.get('url') or url_info.get('presigned_url', '')
if not s3_url: raise RuntimeError('no presigned URL returned')
...
data  = self.fetch_presigned(s3_url)
```
- **Assumes:** callers verify `data` against `fid` before use (same contract as `batch_read`). Established by the verifying callers listed in the `batch_read` record; `nothing found` here.

**Cross-Function Dependencies:**
- Callees: `presigned_read_url` L339-L345 (authenticated GET to own server), `fetch_presigned` L37-L56, `_classify_exception` L266-L298.
- Callers: `_batch_read_chunk_with_fallback` L185.

**Open Questions:** none.
