## `key_for` in sgit_ai/network/api/Vault__HTTP_Pool.py (L67-L73)

**Purpose:** The identity of a connection bucket: `(scheme, host, port, bool(tls_verify), proxy)`. It is what guarantees a `--no-verify-tls` connection never serves a verifying caller and a presigned S3 host never shares a socket with the API host (docstring L11-L13).

**Inputs & Assumptions:**
- `url` (str): the full request URL from `Vault__API` (`base_url` + path). Trust: `base_url` is operator-configured; the path is built locally.
- Implicit: environment proxies via `proxy_for` (L72).

**Outputs & Effects:** returns the tuple; no state.

**Block-by-Block:**
```python
# L68-L73
parts  = urlsplit(url)
scheme = (parts.scheme or 'http').lower()
host   = parts.hostname or ''
port   = parts.port or (443 if scheme == 'https' else 80)
proxy  = self.proxy_for(scheme, host)
return (scheme, host, port, bool(self.tls_verify), proxy or '')
```
- **Assumes:** a URL with no scheme is http (L69). `Safe_Str__Base_URL` does not require a scheme (Safe_Str__Base_URL.py:L4), and `Vault__API__Auto.setup` routes non-http(s) bases to the static transport before the pool is reached (Vault__API__Auto.py:L162-L166); a bare `Vault__API` with a scheme-less `base_url` would build `http://` connections here. `nothing found` checking the scheme in `Vault__API`.
- **Assumes:** `bool(self.tls_verify)` is the only TLS parameter that matters for sharing; the context itself is built once per pool (`ssl_context` L148-L151), so all buckets of one pool share one verify setting anyway.
- **Establishes:** a connection is reused only for the same scheme/host/port/verify/proxy. Tests: `test_key_has_scheme_host_port_verify_proxy`, `test_verify_flag_is_part_of_the_key`.

**Cross-Function Dependencies:**
- Callee `proxy_for` (internal, L75-L81).
- Callers: `acquire` L87.

**Open Questions:** none.
