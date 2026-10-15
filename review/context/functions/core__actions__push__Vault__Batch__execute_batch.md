## `execute_batch` in sgit_ai/core/actions/push/Vault__Batch.py (L246-L299)

**Purpose:** Send a push's operations through `Vault__API.batch`, splitting into chunks under two limits (4 MB of base64 per request, 50 ops per request), sending plain-write chunks in parallel and **every chunk that contains a ref op or a `write-if-match` last and serially**, so the branch moves only after its objects are on the server. Every server reply passes through `_checked`.

**Inputs & Assumptions:**
- `vault_id`, `write_key`, `operations` (list of op dicts; the ref op is last by `build_push_operations`).
- `MAX_B64_BYTES = 4 MB` (L255), `MAX_BATCH_OPS = 50` (Vault__API.py:L20).

**Outputs & Effects:**
- Returns the last chunk's checked result (`{}` when there were no chunks).
- Raises `Vault__Push_Conflict_Error` on a CAS miss, `RuntimeError` on any non-ok op (both from `_checked`), or whatever `api.batch` raises (HTTP errors as `RuntimeError`, dead host as `URLError`).
- Partial effects: chunks already sent stay applied (content-addressed objects; harmless). On a failure in a parallel plain chunk, the other plain chunks still complete (the `with` waits) and the ref chunks are **never sent** (the exception propagates out of the `with` before L297).

**Block-by-Block:**

```python
# L258-L260 (fast path)
total_b64 = sum(len(op.get('data', '')) for op in operations)
if total_b64 <= MAX_B64_BYTES and len(operations) <= MAX_BATCH_OPS:
    return self._checked(self.api.batch(vault_id, write_key, operations))
```
- **What:** one request with objects **and** the ref op together.
- **Assumes:** the server applies a batch atomically when the CAS misses (docstring Vault__API.py:L117); nothing client-side depends on it beyond "the ref did not move" — see `batch` record.
- **Assumes:** a transient 502 after the server applied the batch is **retried by `_request_bytes`** (Vault__API.py:L424-L426); the retry's CAS then misses against our own bytes and `_checked` raises `Vault__Push_Conflict_Error`, which `push` re-raises (Vault__Sync__Push.py:L357-L358) without re-reading the ref. The timeout-after-apply case (a non-HTTP exception) is handled differently: `push` L359-L361 falls back to `execute_individually`, whose `_holds` check recognises the landed move (test `test_F11__a_push_whose_reply_timed_out_after_landing_succeeds`). `nothing found` for the 502-after-apply case.

```python
# L263-L277 (chunking)
for op in operations:
    op_size = len(op.get('data', ''))
    if current_chunk and (current_size + op_size > MAX_B64_BYTES or len(current_chunk) >= MAX_BATCH_OPS):
        chunks.append(current_chunk); current_chunk = [op]; current_size = op_size
    else: current_chunk.append(op); current_size += op_size
```
- **What:** greedy, order-preserving. A single op above 4 MB gets its own chunk (the `current_chunk and` guard) — Phase A in `push` keeps blobs > 4 MB out of batches via `_upload_large` when the server supports it (L288-L299 there); otherwise a 4 MB+ base64 op is sent alone and the Lambda limit is the server's problem.

```python
# L281-L284 (ordering)
cas_value    = Enum__Batch_Op.WRITE_IF_MATCH.value
last         = lambda op: op['op'] == cas_value or str(op.get('file_id', '')).startswith('bare/refs/')
plain_chunks = [c for c in chunks if not any(last(op) for op in c)]
cas_chunks   = [c for c in chunks if     any(last(op) for op in c)]
```
- **What:** any chunk holding a CAS op **or any `bare/refs/` write** (plain-write refs included — a force push or first ref) goes last.
- **Establishes:** refs land after objects, so a reader that follows the new ref finds its objects (modulo the parallel plain chunks all completing first — guaranteed by the `with` block at L289-L293 finishing before L297).
- **Depended on by:** the "verify-then-accept" discipline of readers (a ref pointing at missing objects would be refused on clone, TM-F02).

```python
# L286-L299
if len(plain_chunks) > 1:
    with ThreadPoolExecutor(max_workers=len(plain_chunks)) as executor:
        futures = {executor.submit(self.api.batch, vault_id, write_key, c): c for c in plain_chunks}
        for future in as_completed(futures):
            result = self._checked(future.result())
elif plain_chunks:
    result = self._checked(self.api.batch(vault_id, write_key, plain_chunks[0]))
for chunk in cas_chunks:
    result = self._checked(self.api.batch(vault_id, write_key, chunk))
return result
```
- **What:** parallel plain chunks (one thread each, unbounded — a 2,000-object push is 40+ concurrent POSTs sharing the pooled connections), then the ref chunk(s).
- **Assumes:** `_checked` raising on **any** non-ok op (not only conflicts) — established at L313-L318 (TM-F17: "batch per-op errors and split chunks unchecked" fixed). Tests: `test_Vault__Batch__Coverage.py::Test_Vault__Batch__ExecuteBatch` (3 chunking cases); `tests/security/test_Security__Fixed__Host_Substitution.py::Test_Fixed__Push_Results`.

**Cross-Function Dependencies:**
- Callees: `Vault__API.batch` (L107-L123), `_checked` (L301-L319).
- Callers: `Vault__Sync__Push.push` L308 (Phase A small blobs; any exception → `execute_individually`), L356 (Phase B; conflict re-raised, other exceptions → `execute_individually`); `_push_branch_only` L687; `_reconcile_cache` L523; `_upload_bare_to_server` L815; `_register_pending_branch` L880.
- Shared state: none.

**Open Questions:**
- unclear; whether the live server's per-request limits (docstring L249-L251: ~6 MB body, 100 ops) still hold; the constants are client-side margins with no server-advertised value.
