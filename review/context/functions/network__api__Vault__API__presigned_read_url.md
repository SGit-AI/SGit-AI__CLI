## `presigned_read_url` in sgit_ai/network/api/Vault__API.py (L339-L345)

**Purpose:** `GET /api/vault/presigned/read-url/{vault_id}/{file_id}` → `{url, expires_in}`; the host tells the client where to fetch a large blob from.

**Inputs & Assumptions:** `vault_id`, `file_id` (quoted, L344). Auth headers sent to own server (L345). GET → idempotent resend allowed.

**Outputs & Effects:** returns the host's dict unchecked. Every consumer passes `url_info['url']` (or `.get('url') or .get('presigned_url')`) to `fetch_presigned`, which applies `check_presigned_url`: `_presigned_read_fallback` L250-L255; `Vault__Sync__Pull` L461-L462; `Vault__Sync__Clone` L334-L337, L420-L423; `Vault__Sync__Sparse` L113-L115, L161-L163. `expires_in` is never read.

**Cross-Function Dependencies:** `Vault__API__Static.presigned_read_url` (Vault__API__Static.py:L186-L200) returns the object's own URL or a `file://` path instead; `Vault__API__Auto` dispatches by transport (L220-L221).

**Open Questions:** see `check_presigned_url` (the `file://` case for local static vaults).
