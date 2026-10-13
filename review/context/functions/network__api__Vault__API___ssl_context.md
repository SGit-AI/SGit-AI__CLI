## `_ssl_context` in sgit_ai/network/api/Vault__API.py (L370-L379)

**Purpose:** TLS context for the one-off `urlopen` paths (`fetch_presigned`, `Vault__API__Static._fetch`): `None` (default verifier) unless `tls_verify` is False **and** the URL is https, then `ssl._create_unverified_context()`.

**Inputs & Assumptions:** `url` (str), `self.tls_verify`. The flag comes from `--verify-tls` / the remote config (`CLI__Token_Store.resolve_tls_verify` L32-L48, default True).

**Outputs & Effects:** returns a context or None; no state. With `tls_verify=False` certificate and hostname checks are both off for that connection.

**Cross-Function Dependencies:** callers `fetch_presigned` L52; `Vault__API__Static._fetch` L127 (inherits). The pooled path builds its own in `Vault__HTTP_Pool.ssl_context` (Vault__HTTP_Pool.py:L148-L151) from the pool's copy of the flag (`_pool` L386).

**Open Questions:** none.
