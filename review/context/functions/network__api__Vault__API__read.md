## `read` in sgit_ai/network/api/Vault__API.py (L98-L100)

**Purpose:** `GET /api/vault/read/{vault_id}/{file_id}`, returning the raw body bytes. This is how push reads the server's refs and index (`Vault__Sync__Base._require_readable_server_ref` L86, `_server_named_commit_id` L123; `Vault__Sync__Push._remote_clone_ref` L586, `_check_lease` L949; `Vault__Index_Sync.read_remote` L45) and how pull fetches small blobs (`Vault__Sync__Pull` L464).

**Inputs & Assumptions:**
- `vault_id`, `file_id` (str): as in `write`. Trust: trusted.
- Implicit: `base_url`, `access_token`.

**Outputs & Effects:**
- Returns bytes (`_request_bytes`, L100), possibly `b''` on an empty 2xx body.
- Raises `RuntimeError('API Error: HTTP 404 ...')` when absent (`_send` L466-L467 → `_request_bytes` L427 → `_api_error`): **absence is an exception here**, whereas `Vault__API__Static.read` returns `None` for 404 (Vault__API__Static.py:L130-L131) and `Vault__API__In_Memory.read` raises `RuntimeError('Not found: ...')` (Vault__API__In_Memory.py:L32-L33). Callers that must work on all three wrap in `try/except Exception` and treat a raise and an empty result alike (`_require_readable_server_ref` L85-L90; `_server_named_commit_id` L122-L128; `_remote_clone_ref` L585-L592). `_check_lease` does not catch (Vault__Sync__Push.py:L949): a 404 there surfaces as the API error.
- GET is idempotent → resent once on a stale keep-alive (`_send` L459-L460) and retried on transient codes (`_request_bytes` L424-L426).
- What the host can return that the code accepts: any bytes. This function performs no content check. For `bare/data/*` objects the callers verify the content address before writing (Pull `_save` L276-L290). For `bare/refs/*` and `bare/indexes/*` the only check is AES-GCM decryption under the read key by the caller — the ciphertext is not bound to the ref id (TM-R03, `tests/security/test_Security__Known_Gaps.py::test_TM_R03__ref_ciphertext_is_not_bound_to_its_ref_id`) and carries no freshness (SP-2).

**Block-by-Block:** L99 URL; L100 `_request_bytes('GET', url, self._auth_headers())`.

**Cross-Function Dependencies:**
- Callee `_request_bytes` (internal, L401-L428).
- Callers (host-boundary readers in this slice): `Vault__Sync__Base._require_readable_server_ref` L86, `_server_named_commit_id` L123, `_make_blob_fetcher` L75; `Vault__Sync__Push._remote_clone_ref` L586, `_check_lease` L949; `Vault__Index_Sync.read_remote` L45; `Vault__Backend__API.read` L14; `Vault__Backend.exists` L47 (via subclass).

**Open Questions:** none.
