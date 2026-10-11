## `_batch_read_chunk_with_fallback` in sgit_ai/network/api/Vault__API.py (L167-L185)

**Purpose:** One chunk of `batch_read`, with the Lambda-limit workaround: on `HTTP 502`/`HTTP 503` the chunk is retried file by file, and a file that still 502s is fetched through a presigned URL.

**Inputs & Assumptions:**
- `vault_id`, `chunk` (list[str]), `payloads` (shared dict), `failures` (dict | None).
- Precondition: the error text from `_request_bytes` contains `'HTTP 502'` / `'HTTP 503'` when the status was 502/503 — established by `_api_error` L484 (`f'API Error: HTTP {error.code} {error.reason}'`). Note `_request_bytes` already retried 502/503/504/429 three times with back-off (L412-L428) before this sees the error.

**Outputs & Effects:**
- Fills `payloads`/`failures` through `_batch_read_chunk` and `_presigned_read_fallback`; prints progress to stderr (L177, and inside the fallback).
- Any `RuntimeError` that is not 502/503 re-raises (L173-L174, L183-L184). A non-`RuntimeError` (e.g. `URLError` from `_send` L461, `binascii.Error` from `b64decode` at L201) propagates untouched.

**Block-by-Block:**

```python
# L170-L174
try:
    self._batch_read_chunk(vault_id, chunk, payloads, failures)
except RuntimeError as e:
    if 'HTTP 502' not in str(e) and 'HTTP 503' not in str(e):
        raise
```
- **What:** string-match the status out of the error message.
- **Assumes:** the error text is ours. `_api_error` L489-L490 appends the server's response body to the same message, so a non-502 error whose *body* contains the text `HTTP 502` would also take the fallback path. Observation; `nothing found` separating the two.

```python
# L179-L185
for fid in chunk:
    try:
        self._batch_read_chunk(vault_id, [fid], payloads, failures)
    except RuntimeError as e2:
        if 'HTTP 502' not in str(e2) and 'HTTP 503' not in str(e2): raise
        self._presigned_read_fallback(vault_id, fid, payloads, failures)
```
- **What:** per-file retry, then presigned.
- **Depended on by:** large objects pushed by an older CLI without the `large` flag (docstring L136-L140).

**Cross-Function Dependencies:**
- Callees `_batch_read_chunk` (L187-L205), `_presigned_read_fallback` (L238-L264) — both internal.
- Callers: `batch_read` L154, L160.
- Test: `test_Vault__HTTP_Pool.py::test_502_on_one_chunk_falls_back_per_file_without_touching_other_chunks`.

**Open Questions:** none.
