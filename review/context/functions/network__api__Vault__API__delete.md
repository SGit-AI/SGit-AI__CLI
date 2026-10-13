## `delete` in sgit_ai/network/api/Vault__API.py (L102-L105)

**Purpose:** `DELETE /api/vault/delete/{vault_id}/{file_id}` with the write key. In this slice only the individual-write fallback uses it (`Vault__Batch.execute_individually` L355, for cache deletes from `_reconcile_cache` L439-L440, L482-L483, L507).

**Inputs & Assumptions:** as `write` (L103-L104); no payload.

**Outputs & Effects:** parsed JSON or `{}`; body unchecked: `nothing found`. Not idempotent-flagged (`_request_bytes` L408-L409: only GET), so not resent on a stale socket; retried on transient codes.

**Cross-Function Dependencies:** callers `Vault__Batch.execute_individually` L355; `Vault__Backend__API.delete` L20; `Vault__API__Auto.delete` L229-L230. Server gate: write key (`test_Security__Server_Boundary__Integration.py::test_reader_cannot_delete_or_add_objects`).

**Open Questions:** none.
