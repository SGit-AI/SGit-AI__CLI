## `delete_vault` in sgit_ai/network/api/Vault__API.py (L360-L365)

**Purpose:** `DELETE /api/vault/destroy/{vault_id}` with a JSON body `{vault_id}` and the write key — removes every file of a vault on the host.

**Inputs & Assumptions:** `vault_id`, `write_key`. Trust: trusted (CLI destroy / vault move flows, outside this slice).

**Outputs & Effects:** parsed JSON or `{}`; unchecked. DELETE is not resent on a stale socket; retried on 429/5xx (`_request_bytes` L424-L426). Server gate: write key (`nothing found` client-side).

**Cross-Function Dependencies:** `tombstone_vault` L367-L368 aliases it. Not routed through `Vault__API__Auto._call` (Vault__API__Auto.py L214-L233 lists read/batch_read/presigned_read_url/list_files/write/delete/batch only), so on a resolved static transport this method still targets the live endpoint; `Vault__API__Static` aliases it to `_read_only` (Vault__API__Static.py:L250) when the static class is used directly.

**Open Questions:** none.
