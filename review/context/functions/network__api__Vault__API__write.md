## `write` in sgit_ai/network/api/Vault__API.py (L92-L96)

**Purpose:** One plain `PUT /api/vault/write/{vault_id}/{file_id}` with the write key in a header. The individual-write fallback (`Vault__Batch.execute_individually` L352) and `Vault__Backend__API.write` (L17) are its only callers in this slice; a plain write has no compare-and-swap.

**Inputs & Assumptions:**
- `vault_id` (str): interpolated raw into the URL path (L93). Trust: trusted (derived from the vault key; `Safe_Str__Vault_Id` ⊂ `[a-zA-Z0-9_-]`, Safe_Str__Vault_Id.py:L20 via osbot `Safe_Str__Id` regex). Nothing here checks it: `nothing found`.
- `file_id` (str): percent-encoded with `quote(file_id, safe="")` (L93), so `bare/refs/x` travels as `bare%2Frefs%2Fx`. Trust: trusted (built from ids by callers).
- `write_key` (str): sent as `x-sgraph-vault-write-key` (L95). Trust: trusted secret.
- `payload` (bytes): ciphertext.
- Implicit: `base_url`, `access_token`.

**Outputs & Effects:**
- Returns the parsed JSON body (or `{}` for an empty body, `_request` L397-L399). Nothing checks the body: a 2xx is success whatever it says: `nothing found`.
- External: the write key leaves the process on every call; its only protection is the transport (`https://` by default; TM-R10).
- Not retried on a stale keep-alive (`_send` L459: `idempotent` is False for PUT by default, `_request_bytes` L408-L409) but **is** retried on 429/502/503/504 (`_request_bytes` L424-L426): a write that the server applied before answering 502 is resent. Harmless for content-addressed objects; for refs the fallback path compares first (`execute_individually` L330-L332, L349).

**Block-by-Block:** L93 URL; L94-L95 headers via `_auth_headers`; L96 `_request('PUT', ...)`.

**Cross-Function Dependencies:**
- Callee `_request` → `_request_bytes` → `_send` (internal).
- Callers: `Vault__Batch.execute_individually` L352; `Vault__Backend__API.write` L17; `Vault__API__Auto.write` L226-L227 (dispatch).
- Server side: the write-key check is the only write gate (threat model §4; `tests/integration/test_Security__Server_Boundary__Integration.py::test_reader_cannot_move_the_named_ref_by_plain_write`).

**Open Questions:** none.
