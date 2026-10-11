## `_classify_per_file_status` in sgit_ai/network/api/Vault__API.py (L207-L236)

**Purpose:** Turns a per-file batch result that is not `ok` into a `Schema__Fetch_Failure` (ABSENT / FORBIDDEN / TRANSIENT) so pull/fetch can say "missing on the server" vs "retry". The classification is what later code uses to decide, for a ref, whether a compare-and-swap can be dropped.

**Inputs & Assumptions:**
- `file_id` (str), `status` (any, host-supplied), `raw_result` (dict, host-supplied). Trust: **untrusted** text; it is copied into `Safe_Str__Error_Message` (max 2048, no regex, Safe_Str__Error_Message.py:L3-L7) and later printed by callers.

**Outputs & Effects:** returns a `Schema__Fetch_Failure` (file_id as `Safe_Str__Object_Id` or None when the id does not match `^obj-cas-imm-(12|32 hex)$`, L228-L231 — so a ref or key file id yields `file_id=None`).

**Block-by-Block:**
- L219: strips the `bare/data/` prefix.
- L220-L221: `status_str`, message from `message`/`error`/status.
- L222-L227: `'not_found'`/`'404'` → ABSENT; `'forbidden'`/`'403'` → FORBIDDEN; else TRANSIENT. A missing status (`None`) becomes `'unknown'` → TRANSIENT.
- **Assumes:** the host's status word is truthful (see `_batch_read_chunk`). `nothing found`.

**Cross-Function Dependencies:**
- Callers: `_batch_read_chunk` L205; `Vault__API__Static._record_absent` L183 (passes `'not_found'` for a 404/missing file).
- Consumers: `Vault__Sync__Push._named_ref_absent_on_server` L912-L914 (ABSENT → no CAS); pull's user-facing message (outside slice).
- Tests: `test_Vault__API__Failure_Classification.py::Test_Vault__API__Classify_Per_File_Status` (5 tests).

**Open Questions:** none.
