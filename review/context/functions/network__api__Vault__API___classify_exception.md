## `_classify_exception` in sgit_ai/network/api/Vault__API.py (L266-L298)

**Purpose:** Classify an exception from fetching one file: 404/`Not found` → ABSENT, 403/`Forbidden` → FORBIDDEN, else TRANSIENT, keeping the error text verbatim.

**Inputs & Assumptions:** `file_id`, `error` (Exception; may be urllib `HTTPError` with `.code`, or a `RuntimeError` whose message is our `_api_error` text plus the host's response body).

**Block-by-Block:**
- L281: `code` from `HTTPError.code` only.
- L282-L283: substring tests on `str(error)` for `'HTTP 404'`, `'Not found'`, `'HTTP 403'`, `'Forbidden'`. Because `_api_error` embeds the response body (L489-L490), a host body containing `Not found` would classify a non-404 as ABSENT. `nothing found` separating code from body text.
- L284-L289: precedence absent > forbidden > transient.

**Cross-Function Dependencies:**
- Callers: `_presigned_read_fallback` L264; `Vault__Sync__Pull._fetch_missing_objects._save` L287 (an integrity refusal is wrapped as a `RuntimeError` and classified TRANSIENT).
- Tests: `test_Vault__API__Failure_Classification.py::Test_Vault__API__Classify_Exception` (7 tests, incl. in-memory `Not found:` → ABSENT).

**Open Questions:** none.
