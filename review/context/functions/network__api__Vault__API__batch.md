## `batch` in sgit_ai/network/api/Vault__API.py (L107-L123)

**Purpose:** `POST /api/vault/batch/{vault_id}` with `{'operations': [...]}` and the write key. Every push, index write, ref move and cache reconcile goes through this (via `Vault__Batch.execute_batch` L260, L290, L295, L298, `_atomic_move` L370; `Vault__Index_Sync.upload` L184; `Vault__Sync__Push._ensure_public_key` L931). It is where compare-and-swap (`write-if-match`) reaches the host.

**Inputs & Assumptions:**
- `vault_id` (str): raw in the path (L119).
- `write_key` (str): header (L121).
- `operations` (list of dicts): `op`, `file_id`, `data` (base64), `match` (base64 of the expected current bytes — docstring L114 says "SHA256 hash", `Vault__Ref_Manager.get_ref_file_hash` L65-L76 and the in-memory double L63-L66 say raw bytes base64; the live server's contract is the raw bytes per the d3b8eef/eed8084 review notes cited in `Vault__Index_Sync._cas_conflict` L257-L261). Trust: trusted (built locally).
- Docstring L117: "If any write-if-match fails, the entire batch is rejected." Nothing in the client verifies atomicity; it is a property of the host. `nothing found` on the client side. The in-memory double is **not** atomic: `Vault__API__In_Memory.batch` applies earlier ops and returns `conflict` mid-loop (L46-L67), so a batch `[write obj, write-if-match ref]` leaves `obj` written and the ref untouched — the same observable outcome the client relies on (objects are content-addressed; the ref did not move).

**Outputs & Effects:**
- Returns parsed JSON or `{}` for an empty body (`_request` L397-L399).
- What the host can return that is accepted downstream: `{}` or `{'status': 'ok'}` with no `results` is taken as success by `Vault__Batch._checked` (L305-L319) and `Vault__Index_Sync.require_written` (L246-L255) — both only raise when a `status` is present and not `ok`/`''`, or a per-op result is not `ok`. A host that answers 200 with an empty body to a CAS write is believed to have applied it: `nothing found`.
- Conflict shapes recognised by callers: top-level `status == 'conflict'` (in-memory) and per-op `results[i].status == 'conflict'` (live; optional `current` bytes) — `Vault__Batch._checked` L306-L307, `Vault__Index_Sync._cas_conflict` L257-L268, test `tests/unit/review/test_Format_Gate_And_Integrity.py::test_upload_sees_the_live_server_conflict_shape_and_merges`.
- POST → not resent on a stale keep-alive (`_send` L459; `_request_bytes` L408-L409); **is** retried on 429/502/503/504 (`_request_bytes` L424-L426). A CAS op resent after the server applied it will come back `conflict` (the current bytes are now ours); `Vault__Batch._atomic_move` L372-L374 and `execute_individually` L346-L348 handle that case by re-reading (`_holds`). `execute_batch`'s fast path (L260) does not: a 502-after-apply there raises `Vault__Push_Conflict_Error` to `push` (L357-L358), which re-raises. Test `tests/security/test_Security__Fixed__Index_Overwrite.py::test_F11__a_push_whose_reply_timed_out_after_landing_succeeds` covers a *timeout* (non-HTTP exception → fallback), not a 502 retry.

**Block-by-Block:** L119 URL; L120-L121 headers; L122 `json.dumps({'operations': operations})`; L123 `_request('POST', ...)`.

**Cross-Function Dependencies:**
- Callee `_request` (internal).
- Callers: `Vault__Batch.execute_batch` L260, L290, L295, L298; `Vault__Batch._atomic_move` L370; `Vault__Index_Sync.upload` L184; `Vault__Sync__Push._ensure_public_key` L931; `Vault__Backend__API.batch` L29; `Vault__API__Auto.batch` L232-L233.
- Server gate: write key, per op (`test_Security__Server_Boundary__Integration.py::test_reader_cannot_move_the_named_ref_by_batch`, both `write` and `write-if-match`).
- `Vault__API__Auto._resolve_from_error` (Vault__API__Auto.py:L180-L194) treats a 404/405/501 **on this URL** as "no live API" and flips the transport to static permanently (L205-L211).

**Open Questions:**
- unclear; need the server's behaviour on a batch with mixed `write` and `write-if-match` when the CAS misses: are the plain writes rolled back? The client's correctness does not depend on it (objects are content-addressed, refs only move via CAS) but the docstring claims it.
