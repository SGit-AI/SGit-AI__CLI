## `proxy_auth_header` in sgit_ai/network/api/Vault__HTTP_Pool.py (L168-L174)

**Purpose:** `{'Proxy-Authorization': 'Basic <b64(user:pass)>'}` when the proxy URL carries userinfo, else `{}`.

**Inputs & Assumptions:** `proxy` (str) from the environment. Credentials are URL-decoded (`unquote`, L173). Trust: environment.

**Outputs & Effects:** dict; no state. Where it goes: on the CONNECT for an https origin (`open_via_proxy` L189, `set_tunnel(headers=...)`) or on every request for a plain-http origin (`proxy_headers` L195-L196 → `_send` L448). In the plain-http case the header travels in clear to the proxy along with the API token headers.

**Depended on by:** `open_via_proxy`, `proxy_headers`. Tests: `test_https_proxy_becomes_a_connect_tunnel_with_basic_auth`, `test_plain_http_via_authenticated_proxy_sends_proxy_authorization`.

**Open Questions:** none.
