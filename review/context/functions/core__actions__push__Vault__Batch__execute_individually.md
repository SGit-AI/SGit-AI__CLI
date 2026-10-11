## `execute_individually` in sgit_ai/core/actions/push/Vault__Batch.py (L321-L358)

**Purpose:** The fallback when the batch path failed for a reason other than a conflict (or when `use_batch=False`): replay the operations one by one with `Vault__API.write`/`delete`. For a `write-if-match` op it first tries the move as its **own one-op batch** (atomic on the server), and only when that is unavailable compares-then-writes — the non-atomic path the d3b8eef review flagged (comment L339-L342).

**Inputs & Assumptions:**
- `operations` (list of op dicts, from `build_push_operations` or the cache/registration builders). The ref op, if any, is `write-if-match` with `match` (CAS) or `write` (force / new ref).
- `atomic_moves` (bool, default True): False only from `push`/`_push_branch_only`/`_reconcile_cache` when `use_batch=False` — a parameter no CLI path sets (grep `use_batch` in `sgit_ai/cli/` finds nothing), so in production it is always True.
- Implicit: the server may or may not have a batch endpoint (older servers, docstring L324).

**Outputs & Effects:**
- Network: `batch_read` per CAS op (twice: pre-check and `_holds`), one single-op `batch` per CAS op, `write`/`delete` per other op. All plain writes have no CAS.
- Returns `{'status': 'ok', 'results': [...]}` — **this function's own `ok` list**, not the server's answers; `Vault__API.write`'s reply is discarded (L352). A 2xx with any body counts.
- Raises `Vault__Push_Conflict_Error` from `_require_current`/`_atomic_move`, `RuntimeError` when the compare read fails, API errors from `write`/`delete`.

**Block-by-Block:**

```python
# L330-L332
for op in operations:
    if op['op'] == WRITE_IF_MATCH and op.get('match') and not self._holds(vault_id, op):
        self._require_current(vault_id, op['file_id'], op['match'])
```
- **What:** compare first, before uploading anything, so a lost race uploads nothing (comment L330). `_holds` short-circuits when the server already has exactly our bytes (an earlier attempt landed).
- **Assumes:** `batch_read` of the ref returns the server's true current bytes. A host answering stale bytes equal to `match` passes the pre-check; the later single-op CAS batch is what actually guards (if the host has one).

```python
# L338-L349
if op_type == WRITE_IF_MATCH and op.get('match'):
    if atomic_moves and self._atomic_move(vault_id, write_key, op):
        results.append(ok); continue
    if self._holds(vault_id, op):
        results.append(ok); continue
    self._require_current(vault_id, file_id, op['match'])
```
- **What:** try the atomic single-op batch; else accept "already landed"; else compare again just before writing.
- **Assumes:** `_atomic_move` returns False only when the server has no usable batch (it returns False on *any* non-conflict exception from `batch` after `_holds` says no — including a 401/403, a 5xx that exhausted retries, or a dead host; the stderr warning at L380-L381 says "no atomic batch write"). The subsequent `api.write` then has the same server to deal with and raises in its turn; the window between `_require_current` and `write` is the non-atomic compare-then-write (TM-F08 row: "individual-write fallback pre-checks CAS"). `nothing found` closing that window on a server without batch; by design.

```python
# L350-L356
if op_type in (WRITE, WRITE_IF_MATCH):
    payload = base64.b64decode(op['data'])
    self.api.write(vault_id, file_id, write_key, payload)
    results.append(ok)
elif op_type == DELETE:
    self.api.delete(vault_id, file_id, write_key)
    results.append(ok)
```
- **What:** plain PUT / DELETE. A `write-if-match` op **without** `match` (the server has no ref yet — `build_push_operations` would have emitted `write` instead; `Vault__Index_Sync` never reaches here) falls to a plain write.
- **Assumes:** `write` succeeded if it did not raise; the reply is not inspected (see `Vault__API.write`).

**Cross-Function Dependencies:**
- Callees: `_holds` (L384-L390), `_require_current` (L392-L405), `_atomic_move` (L360-L382), `Vault__API.write/delete`.
- Callers: `Vault__Sync__Push.push` L310, L312, L361, L363; `_push_branch_only` L692, L694; `_reconcile_cache` L525, L527; `_upload_bare_to_server` L818; `_register_pending_branch` L883. In `push` L359-L361 this runs after **any** non-conflict exception from `execute_batch` — including a 401/403, which then recurs on `write` and surfaces.
- Tests: `tests/security/test_Security__Fixed__Index_Overwrite.py::Test_Fixed__Fallback_Moves_Atomically::test_the_op_by_op_fallback_never_overwrites_a_teammates_push` (Racy_Batch_API: a teammate's write inside the window is not overwritten), `Test_Fixed__Timeout_Is_Not_A_Lost_Race::test_F11...`; `tests/unit/sync/test_Vault__Batch.py::test_push_fallback_to_individual_when_batch_fails`, `test_batch_execute_individually`; `tests/integration/test_Vault__Batch__Integration.py::test_push_fallback_when_batch_unavailable`.

**Open Questions:**
- unclear; `_atomic_move` treats every non-conflict exception as "no batch endpoint" (L376-L382). Whether an auth failure or a transient 5xx on the single-op batch should instead abort is a design question for the hunting phase; recorded here as the branch structure.
