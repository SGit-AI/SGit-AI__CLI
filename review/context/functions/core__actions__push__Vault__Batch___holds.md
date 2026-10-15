## `_holds` in sgit_ai/core/actions/push/Vault__Batch.py (L384-L390)

**Purpose:** "The server's copy of op's file is exactly the bytes op writes" — the idempotence test for a move that may already have landed.

**Inputs & Assumptions:** `op` with `file_id`, `data` (base64). Reads the server through `batch_read` (no `failures` dict).

**Outputs & Effects:** bool; **any exception → False** (L389-L390), including a dead host, so a failed read is "not held" and the caller proceeds to compare/write (which then fails loudly in `_require_current`, L398-L400).

**Block-by-Block:**
```python
# L387-L388
found = self.api.batch_read(vault_id, [op['file_id']]) or {}
return found.get(op['file_id']) == base64.b64decode(op['data'])
```
- **Assumes:** the host returns its true current bytes. The comparison is to our own freshly encrypted ciphertext (random IV), so a false positive requires the host to echo exactly those bytes. A false negative (host returns stale/other bytes) makes the caller go on to the CAS batch or `_require_current`, which then conflicts: fail-safe direction. `nothing found` beyond byte equality.

**Cross-Function Dependencies:** callers `execute_individually` L331, L346; `_atomic_move` L367, L373, L377. Callee `Vault__API.batch_read` (live: omits ids the server did not mention → `.get` None → False).

**Open Questions:** none.
