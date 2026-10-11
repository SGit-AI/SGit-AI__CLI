## `request_target` in sgit_ai/network/api/Vault__HTTP_Pool.py (L199-L209)

**Purpose:** What goes on the request line: `path[?query]` for direct or tunnelled connections, the absolute URL for plain-http-through-proxy.

**Inputs & Assumptions:** `key`, `url` (full URL built by `Vault__API`). Fragment is dropped (`urlsplit` separates it; L204-L206 use path and query only). The path keeps `Vault__API`'s `quote(file_id, safe="")` encoding (Vault__API.py:L93, L99, L103, L344) — `/` inside a file id is `%2F`.

**Outputs & Effects:** string; no state.

**Depended on by:** `_send` L446. Tests: `test_plain_http_via_proxy_uses_absolute_uri`; the local-server tests assert on `r[1]` paths (`test_stale_keep_alive_is_retried_for_idempotent_reads` L219).

**Open Questions:** none.
