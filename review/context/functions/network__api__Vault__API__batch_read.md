## `batch_read` in sgit_ai/network/api/Vault__API.py (L125-L165)

**Purpose:** Read many files in one or more `POST /api/vault/batch/{vault_id}` requests of `read` ops, chunked at `MAX_BATCH_OPS = 50` (L20), chunks in parallel (`BATCH_READ_WORKERS = 16`, L21). Returns `{file_id: bytes | None}`; with `failures`, records a `Schema__Fetch_Failure` per missing/failed id. Push uses it to read the server's copy of one file (`_named_ref_absent_on_server` L909, `_ensure_public_key` L925, `Vault__Batch._holds` L387, `_require_current` L397, `_fetch_cache_object` L62).

**Inputs & Assumptions:**
- `vault_id` (str), `file_ids` (list[str]): trusted (built locally).
- `failures` (dict | None): out-parameter; `None` opts out of classification (L142-L146).
- Implicit: `_pool`, `base_url`, `access_token`.

**Outputs & Effects:**
- Returns `payloads` keyed only by ids that were **requested** (`_batch_read_chunk` L194-L198 drops answers for ids not asked for).
- A requested id the server did not mention at all is **absent from the dict** (no `None` entry) — `_batch_read_chunk` only writes keys for results it receives. Callers that do `found.get(fid)` read that as None (`_holds` L388, `_require_current` L401, `_fetch_cache_object` L63, `_ensure_public_key` L926); `_named_ref_absent_on_server` requires `fid in found` (L913), so a silent omission is *not* "absent" there.
- Shared dict `payloads` is written from several threads (L160-L162); each key is written once per chunk, chunks are disjoint.
- Exceptions: the first chunk's exception re-raises (L163-L164, `future.result()`); other chunks keep running inside the `with`.

**Block-by-Block:**

```python
# L149-L155
if not file_ids: return payloads
chunks = [file_ids[i:i + MAX_BATCH_OPS] ...]
if len(chunks) <= 1:
    self._batch_read_chunk_with_fallback(vault_id, chunks[0], payloads, failures)
    return payloads
```
- **What:** no request for an empty list; single chunk inline.

```python
# L157-L165
with ThreadPoolExecutor(max_workers=workers) as executor:
    futures = [executor.submit(self._batch_read_chunk_with_fallback, ...) for chunk in chunks]
    for future in futures:
        future.result()
```
- **What:** parallel chunks sharing one connection pool (`_pool` is lock-guarded, L383).
- **Assumes:** `_batch_read_chunk_with_fallback` either fills `payloads` for every id in its chunk or raises. See that record: an id with `status == 'ok'` and empty `data` gets `None` plus a TRANSIENT failure.
- Tests: `tests/unit/network/api/test_Vault__HTTP_Pool.py::Test_Vault__API__Batch_Read__Parallel_Chunks` (split, inline, propagation, 502-per-chunk fallback).

**Cross-Function Dependencies:**
- Callee `_batch_read_chunk_with_fallback` (internal, L167-L185) → `_batch_read_chunk` (L187-L205) → `_request(..., idempotent=True)` (L193). The read batch is explicitly idempotent, so it is resent once on a stale keep-alive (`test_batch_read_is_treated_as_idempotent`).
- Callers that trust the bytes without a content-address check (mutable files, decrypted under the read key only): `Vault__Sync__Push._named_ref_absent_on_server` L909 (existence only), `_ensure_public_key` L925 (existence only), `Vault__Batch._holds` L387 and `_require_current` L397 (byte equality with our own bytes), `Vault__Sync__Base._fetch_cache_object` L62 (decrypt + parse). Callers that verify: `Vault__Sync__Pull._fetch_missing_objects` L296 + `_save` L281; `Vault__Sync__Status._fetch_commit_chain` L300-L304 (`writer.save` VERIFIED). Unverified writer with no callers: `Vault__Sync__Base.fetch_tree_lazy` L645-L653.
- Differences from the double: `Vault__API__In_Memory.batch_read` (L79-L105) answers every id (None for missing) and never raises; the live path can raise per chunk and can omit ids.

**Open Questions:**
- unclear; whether the live server ever answers a `read` op with `status: 'ok'` and an empty `data` for an existing zero-length file. The client would record it as `None` + TRANSIENT (`_batch_read_chunk` L200-L205). No zero-length ciphertext exists (AES-GCM adds 28 bytes, `Vault__Crypto.encrypt` L294-L299), so only a malformed host answer reaches this.
