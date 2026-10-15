## `proxy_for` in sgit_ai/network/api/Vault__HTTP_Pool.py (L75-L81)

**Purpose:** The proxy URL urllib would use for `scheme`+`host`, or `''`: `getproxies()` (environment / registry) filtered by `proxy_bypass(host)` (NO_PROXY).

**Inputs & Assumptions:** `scheme`, `host` (str). Implicit: process environment (`HTTP_PROXY`, `HTTPS_PROXY`, `NO_PROXY`, lower-case variants). Trust: environment (A6). The proxy URL may embed credentials (`user:pass@`), consumed by `proxy_auth_header`.

**Outputs & Effects:** string; no state. Called on every `acquire` (via `key_for`), so an environment change mid-process takes effect on the next request.

**Cross-Function Dependencies:** callers `key_for` L72. Tests: `test_https_proxy_becomes_a_connect_tunnel_with_basic_auth`, `test_no_proxy_bypass`, `test_plain_http_via_proxy_uses_absolute_uri`. The hermetic test guard clears these variables (`tests/_helpers/hermetic_network.py` L73-L74).

**Open Questions:** none.
