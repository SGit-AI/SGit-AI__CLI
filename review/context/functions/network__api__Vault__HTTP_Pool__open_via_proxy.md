## `open_via_proxy` in sgit_ai/network/api/Vault__HTTP_Pool.py (L176-L190)

**Purpose:** One connection to the proxy: a CONNECT tunnel for an https origin (auth on the CONNECT), or a plain connection to the proxy for an http origin (the request then carries an absolute URI and the auth header per request).

**Inputs & Assumptions:** `scheme`, `host`, `port` of the origin; `proxy` URL (environment).

**Block-by-Block:**
- L180-L182: proxy host/port, default 443 for an https proxy, else 80.
- L183-L187: `HTTPSConnection` to the proxy when **either** the origin or the proxy is https (with the pool's context); else `HTTPConnection`.
- L188-L189: for an https origin, `set_tunnel(host, port, headers=proxy_auth)` — TLS to the origin is negotiated inside the tunnel by `http.client`, with the same `ssl_context()` (verifying the origin's certificate when `tls_verify`).
- **Assumes:** an http origin through an https proxy is sent as an absolute-URI request over the TLS connection to the proxy (L183-L187 + `request_target` L207-L208). The token headers then reach the proxy inside TLS but the origin in clear — the same as any `http://` base_url (TM-R10).

**Depended on by:** `open` L160. Tests: `test_https_proxy_becomes_a_connect_tunnel_with_basic_auth`, `test_plain_http_via_proxy_uses_absolute_uri`.

**Open Questions:** none.
