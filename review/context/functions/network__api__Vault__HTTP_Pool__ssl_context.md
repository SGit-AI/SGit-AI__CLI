## `ssl_context` in sgit_ai/network/api/Vault__HTTP_Pool.py (L148-L151)

**Purpose:** The one TLS context for this pool: `ssl.create_default_context()` (verifies CA chain and hostname) when `tls_verify`, else `ssl._create_unverified_context()`.

**Inputs & Assumptions:** `self.tls_verify`, fixed at pool construction (`Vault__API._pool` L386). Built once (L149) and cached in `ctx`.

**Outputs & Effects:** the context used for every `HTTPSConnection` the pool opens (L162, L184-L185), including the connection to an https **proxy** (L183-L185): with `tls_verify=False` the proxy connection is unverified as well.

**Depended on by:** `open`, `open_via_proxy`. Tests: `test_verify_flag_is_part_of_the_key` (key), no unit test exercises the unverified branch against a TLS server.

**Open Questions:** none.
