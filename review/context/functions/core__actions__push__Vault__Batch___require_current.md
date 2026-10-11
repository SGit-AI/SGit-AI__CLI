## `_require_current` in sgit_ai/core/actions/push/Vault__Batch.py (L392-L405)

**Purpose:** The fallback's compare step: the server's copy of `file_id` must equal the bytes the CAS expected (`match`), else this push lost a race → `Vault__Push_Conflict_Error`. A read that fails is reported as "could not compare", never as "a teammate pushed" (L398-L400).

**Inputs & Assumptions:** `file_id`, `match_b64` (base64 of the expected server bytes — local ref file bytes in `push`, server-read bytes for lease/branch-only).

**Outputs & Effects:** none on success; raises `RuntimeError` (read failed, "nothing was overwritten") or `Vault__Push_Conflict_Error` (`current is None` — absent on the server, or omitted from the reply — or bytes differ, L401-L405).

**Block-by-Block:**
- L396-L400: `batch_read` of the one id; any exception → `RuntimeError` with the cause.
- L401-L405: `current = found.get(file_id)`; `None` or mismatch → conflict. Note `None` covers both "server says not_found" and "server omitted the id" (live `batch_read` does not add keys for unmentioned ids).
- **Assumes:** the server's answer is current (a stale-but-matching answer passes; the subsequent plain `write` in `execute_individually` L352 then overwrites whatever is really there — this is exactly the non-atomic window the comment at L339-L342 describes, reachable only when `_atomic_move` returned False). `nothing found` closing it without a batch endpoint.

**Cross-Function Dependencies:** callers `execute_individually` L332, L349. Callee `Vault__API.batch_read`. Test: `test_Vault__Batch.py::test_push_fallback_to_individual_when_batch_fails`; `test_the_op_by_op_fallback_never_overwrites_a_teammates_push` (exercises the atomic path first).

**Open Questions:** none.
