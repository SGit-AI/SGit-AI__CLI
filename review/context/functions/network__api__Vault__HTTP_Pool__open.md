## `open` in sgit_ai/network/api/Vault__HTTP_Pool.py (L157-L163)

**Purpose:** Create an unconnected `HTTPSConnection`/`HTTPConnection` for a key (the connect happens on first `request`). With a proxy in the key, delegate to `open_via_proxy`.

**Inputs & Assumptions:** `key = (scheme, host, port, verify, proxy)` from `key_for`.

**Block-by-Block:**
- L159-L160: proxy → `open_via_proxy`.
- L161-L162: https → `HTTPSConnection(host, port, timeout, context=self.ssl_context())`.
- L163: anything else (including an unknown scheme normalised to `'http'` by `key_for` L69) → plain `HTTPConnection`.
- **Establishes:** every socket has the pool's timeout; TLS verification follows `tls_verify`.

**Depended on by:** `acquire` L98. The hermetic test guard patches `HTTPConnection.connect` (tests/_helpers/hermetic_network.py L26-L31, L75), so these objects are what the guard sees.

**Open Questions:** none.
