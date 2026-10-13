## `_checked` in sgit_ai/core/actions/push/Vault__Batch.py (L301-L319)

**Purpose:** The single interpretation of a batch reply: a compare-and-swap miss (top-level `status == 'conflict'` as the in-memory double answers, or any `results[i].status == 'conflict'` as the live server answers inside HTTP 200) raises `Vault__Push_Conflict_Error`; any other per-op status that is not `ok`, or a top-level status that is neither `ok` nor empty, raises `RuntimeError` ("never a silent success", L314).

**Inputs & Assumptions:**
- `result` (any): the parsed JSON from `Vault__API.batch` — a dict normally; `None`/`{}` for an empty body (`_request` L397-L399). Trust: **untrusted** (host-supplied).

**Outputs & Effects:** returns `result` (as a dict, `result or {}`) or raises. No state.

**Block-by-Block:**

```python
# L305-L312
result = result or {}
conflicted = str(result.get('status', 'ok')) == 'conflict' or any(
    isinstance(r, dict) and str(r.get('status', 'ok')) == 'conflict' for r in (result.get('results') or []))
if conflicted:
    raise Vault__Push_Conflict_Error('the branch moved on the server while this push was in flight ...')
```
- **What:** both conflict shapes.
- **Assumes:** the server marks a CAS miss with the word `conflict` (an HTTP 409/412 would instead arrive as a `RuntimeError` from `_api_error` and bypass this function — `execute_batch`'s callers then fall back to `execute_individually`, whose `_require_current`/`_atomic_move` re-derive the conflict; `Vault__Index_Sync.upload` L189-L191 handles 409/412 text explicitly, this class does not). `nothing found` for an HTTP-status conflict here.
- **Assumes:** `result` is a dict. A JSON list would raise `AttributeError` at `.get` (not caught) — `execute_batch`'s callers catch `Exception` and fall back.

```python
# L313-L319
failed = [r for r in (result.get('results') or []) if isinstance(r, dict) and str(r.get('status', 'ok')) != 'ok']
if failed or str(result.get('status', 'ok')) not in ('ok', ''):
    first = failed[0] if failed else result
    raise RuntimeError(f'the server did not accept part of the push ({first.get("file_id", "batch")}: {first.get("status")} {first.get("message", "")}'.rstrip() + ')')
return result
```
- **What:** every op must be `ok` (a missing per-op `status` defaults to `ok`).
- **Assumes:** absence of information is success: `{}` (empty body), `{'status': 'ok'}` with no `results`, or `results` shorter than the operations sent all pass. No check that `len(results) == len(operations)` or that each `file_id` sent appears: `nothing found`. The error message embeds the host's `status`/`message` text verbatim (→ terminal).
- **Establishes:** on return, nothing the host *said* was a failure or a conflict.

**Cross-Function Dependencies:**
- Callers: `execute_batch` L260, L293, L295, L298; `_atomic_move` L370.
- Sibling with the same contract: `Vault__Index_Sync.require_written` (sgit_ai/core/actions/index/Vault__Index_Sync.py:L246-L255) and `_cas_conflict` (L257-L268).
- Tests: `tests/security/test_Security__Fixed__Host_Substitution.py::Test_Fixed__Push_Results::test_any_op_that_is_not_ok_fails_the_push` (error → RuntimeError, per-op conflict → Push_Conflict, ok → ok); `test_Vault__Batch.py::test_batch_cas_conflict_detection` (in-memory top-level shape).

**Open Questions:**
- unclear; need the live server's exact reply for a CAS miss (HTTP 200 + per-op `conflict` per the review notes cited at L302-L304 and `Vault__Index_Sync._cas_conflict` L258-L261; the 04/16 brief `team/humans/dinis_cruz/claude-code-web/04/16/vault-batch-api-brief.md:L162` says "412"). Both are handled somewhere in the client, but not in the same function.
