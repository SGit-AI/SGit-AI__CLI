## `_batch_read_chunk` in sgit_ai/network/api/Vault__API.py (L187-L205)

**Purpose:** The one request behind `batch_read`: POST `read` ops, decode each per-file result into `payloads`, classify non-ok ones into `failures`. This is where the host's per-file answers are parsed and where "absent on the server" is decided.

**Inputs & Assumptions:**
- `chunk` (list[str]): ≤ 50 ids (caller), trusted.
- `payloads`, `failures`: out-dicts.
- Response shape assumed: `{'results': [{'file_id', 'status', 'data'?, 'message'?}, ...]}` (L195-L205). `result` may be `{}` (empty body) → no results → nothing recorded for the chunk.

**Outputs & Effects:**
- `payloads[fid] = b64decode(data)` for `status == 'ok'` with non-empty `data` (L200-L201).
- `payloads[fid] = None` otherwise, plus `failures[fid] = _classify_per_file_status(...)` when `failures` is given (L202-L205). `status='not_found'` → ABSENT; `'forbidden'/'403'` → FORBIDDEN; anything else (including `'ok'` with empty data, or a missing status) → TRANSIENT (`_classify_per_file_status` L222-L227).
- Ids not in the response are not written at all (see `batch_read`).
- `base64.b64decode` with default `validate=False` discards non-alphabet characters silently; a padding error raises `binascii.Error`, which is not a `RuntimeError` and so escapes `_batch_read_chunk_with_fallback` (L172) up to the caller of `batch_read`.

**Block-by-Block:**

```python
# L189-L193
operations = [{'op': 'read', 'file_id': fid} for fid in chunk]
url        = f'{self.base_url}/api/vault/batch/{vault_id}'
headers    = self._auth_headers({'Content-Type': 'application/json'})
result     = self._request('POST', url, headers, payload, idempotent=True)
```
- **What:** a read batch; no write key; marked idempotent so a stale keep-alive resends it once (`_send` L459-L460).
- **Assumes:** a `read`-only batch has no server-side effect. Not checked here; by the API's description (L111).

```python
# L194-L198
requested = set(chunk)
for r in result.get('results', []):
    fid = r.get('file_id', '')
    if fid not in requested:
        continue
```
- **What:** drop answers for ids the client did not ask for (comment L197: "the id names the on-disk path").
- **Establishes:** `payloads` keys ⊆ requested ids. Downstream writers (`Vault__Verified_Write.save`, `is_store_path` L29-L37) additionally refuse ids outside the bare store.
- **Depended on by:** every caller that iterates `payloads.items()` and writes by key (`Vault__Sync__Pull._batch_save` L308-L311; `Vault__Sync__Status._fetch_commit_chain` L303-L305).

```python
# L199-L205
status = r.get('status')
if status == 'ok' and r.get('data'):
    payloads[fid] = base64.b64decode(r['data'])
else:
    payloads[fid] = None
    if failures is not None and fid:
        failures[fid] = self._classify_per_file_status(fid, status, r)
```
- **What:** bytes or absence, as the host says.
- **Assumes:** the host is honest about `not_found`. Nothing verifies the claim; a host answering `not_found` for a file it holds makes the client treat it as ABSENT. Consequences in this slice: `Vault__Sync__Push._named_ref_absent_on_server` L912-L914 turns ABSENT into "write the ref without compare-and-swap" (TM-R33 documents the race; the host-driven version is the same code path). `nothing found` beyond the server's word.
- **Establishes:** for a returned `ok`, the bytes are whatever the host sent; content-address verification is the caller's (`Vault__Verified_Write`).

**Cross-Function Dependencies:**
- Callees: `_request` (internal), `_classify_per_file_status` (internal, L207-L236).
- Callers: `_batch_read_chunk_with_fallback` L171, L181.
- Tests: `tests/unit/api/test_Vault__API__Failure_Classification.py::Test_Vault__API__Batch_Read_Chunk__Failures` (not_found → ABSENT, mixed, no-failures-dict); the local server in `test_Vault__HTTP_Pool.py::_Handler._serve_batch` L53-L71 answers `not_found` for id `'absent'`.

**Open Questions:** none.
