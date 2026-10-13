## `proxy_headers` in sgit_ai/network/api/Vault__HTTP_Pool.py (L192-L197)

**Purpose:** Per-request headers needed only for plain http through a proxy: the `Proxy-Authorization` header. Empty otherwise (for https the auth went on the CONNECT).

**Inputs & Assumptions:** `key` tuple.
**Outputs & Effects:** dict merged into `send_headers` before the caller's headers (`_send` L448-L449), so a caller header of the same name would override it.

**Depended on by:** `_send` L448. Test: `test_plain_http_via_authenticated_proxy_sends_proxy_authorization`.

**Open Questions:** none.
