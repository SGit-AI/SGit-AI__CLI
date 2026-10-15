## `list_files` in sgit_ai/network/api/Vault__API.py (L347-L358)

**Purpose:** `GET /api/vault/list/{vault_id}[?prefix=...]` → list of file ids. Push uses it to decide **first push** (`_is_first_push` L722: empty list ⇒ upload all of `bare/` and write the ref without CAS), **resync** (`_server_has_named_ref` L769), and which cache objects the server holds (`_cache_targets` L549).

**Inputs & Assumptions:**
- `prefix` (str): appended unquoted to the query (L353-L354). Callers pass literals `'bare/'`, `'bare/refs/'`, `'bare/cache/'`; nothing escapes it: `nothing found` (no untrusted caller).
- Response: a dict with `files` or a bare list (L356-L358); an empty body gives `{}` → `[]`.

**Outputs & Effects:**
- Returns the host's list verbatim. What the host can return that the code accepts: any list, including `[]` for a populated vault. Consequences: `_is_first_push` → `True` → `_upload_bare_to_server` plain-writes every local `bare/` file (L140, L110) and the ref is written by plain `write` after the bare upload (`push` L349-L350 keeps only the ref op; the CAS `match` is the local ref bytes just uploaded). Nothing cross-checks the listing against a `read` of the named ref before that happens: `nothing found`. (`_server_has_named_ref` L772 does a substring match over the listing.)
- An HTTP error raises `RuntimeError` (via `_api_error`); `_is_first_push` and `_server_has_named_ref` convert that into a push failure, never "empty" (L723-L724, L770-L771; tests `test_Vault__Sync__Push__Coverage.py::test_is_first_push_api_exception_is_an_error`, `test_server_has_named_ref_exception_is_an_error`). `_cache_targets` swallows it (L558-L559, `listing_ok=False`).
- GET → idempotent resend allowed; retried on transient codes.

**Block-by-Block:** L352-L354 URL; L355 request; L356-L358 shape normalisation.

**Cross-Function Dependencies:**
- Callers: `Vault__Sync__Push._is_first_push` L722, `_server_has_named_ref` L769, `_cache_targets` L549; `Vault__Backend__API.list_files` L23 (normalises again, L24-L26); `Vault__API__Auto.list_files` L223-L224. `Vault__API__Static.list_files` (L202-L216) reads `manifest.json` instead for http hosts.
- Difference from the double: `Vault__API__In_Memory.list_files` (L107-L111) returns ids with the `vault_id/` prefix stripped, i.e. `bare/...` paths; `test_Security__Server_Boundary__Integration.py` L82-L84 shows the live server may return ids with or without the `bare/` prefix (`blob if blob.startswith('bare/') else f'bare/data/{blob}'`). `_server_has_named_ref`'s substring test (L772) and `_cache_targets`'s split-on-`/` parse (L551-L556, requires `parts[0] == 'bare'`) react differently to that: with bare names, `_cache_targets` would find no server ids.

**Open Questions:**
- unclear; need the live server's `list` response shape (with or without `bare/` prefix, with or without the `files` wrapper). The integration test tolerates both; `_cache_targets` only parses the prefixed form.
