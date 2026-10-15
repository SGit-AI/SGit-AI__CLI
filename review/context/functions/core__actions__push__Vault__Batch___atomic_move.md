## `_atomic_move` in sgit_ai/core/actions/push/Vault__Batch.py (L360-L382)

**Purpose:** Land one compare-and-swap op as its own one-operation batch so the server applies it atomically. True when the server now holds the move; raises `Vault__Push_Conflict_Error` when the branch moved under us (unless the server already holds exactly our bytes — a timed-out earlier attempt that landed, review 0a0707d F11); False when the server has no usable batch endpoint so the caller falls back to compare-then-write.

**Inputs & Assumptions:** `op` (a `write-if-match` dict with `file_id`, `data`, `match`).

**Outputs & Effects:** one `batch_read` (via `_holds`) up front, one single-op `batch`, up to two more `batch_read`s on failure; stderr warning on the False path (L380-L381).

**Block-by-Block:**
```python
# L367-L368
if self._holds(vault_id, op): return True
```
- **What:** idempotence — our bytes are already there.
- **Assumes:** byte-equality of the server's copy with `op['data']` means *this* move landed. The ref ciphertext has a random IV (`Vault__Crypto.encrypt` L295-L296), so equal bytes can only come from this very op (or a host replaying them). `nothing found` beyond that.

```python
# L369-L375
try:
    self._checked(self.api.batch(vault_id, write_key, [op]))
    return True
except Vault__Push_Conflict_Error:
    if self._holds(vault_id, op): return True
    raise
```
- **What:** the atomic move; a conflict is re-examined once against our own bytes (a 502-retry or a timeout may have applied the first attempt).
- **Depended on by:** `execute_individually` L343; test `test_F11__a_push_whose_reply_timed_out_after_landing_succeeds` (the multi-op batch raises `TimeoutError` after applying, `push` falls back here, `_holds` sees the landed move).

```python
# L376-L382
except Exception:
    if self._holds(vault_id, op): return True
    print('  warning: this server has no atomic batch write; the branch moves by compare-then-write', file=sys.stderr)
    return False
```
- **What:** every other exception → "no batch endpoint".
- **Assumes:** that is the only reason a single-op batch can fail without conflicting. A 401/403 (wrong write key), a dead host (`URLError`), a 5xx after retries, or a malformed reply (`AttributeError` in `_checked`) all take this branch and lead to `_require_current` + `api.write` in the caller. `nothing found` distinguishing them.

**Cross-Function Dependencies:** callees `_holds`, `_checked`, `Vault__API.batch`. Caller: `execute_individually` L93. The in-memory double's `batch` returns top-level `conflict` (Vault__API__In_Memory.py:L66-L67), which `_checked` raises on, so the conflict branch is what unit tests exercise.

**Open Questions:** see `execute_individually`.
