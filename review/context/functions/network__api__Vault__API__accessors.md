# `Vault__API` trivial accessors — sgit_ai/network/api/Vault__API.py

Class fields (L25-L30): `base_url : Safe_Str__Base_URL`, `access_token : Safe_Str__Access_Token`, `tls_verify : bool = True`, `debug_log : object`, `http_pool : object`. `Safe_Str__Base_URL` strips every character outside `[a-zA-Z0-9:/._-]` (sgit_ai/safe_types/Safe_Str__Base_URL.py:L4-L10): no `?`, `#`, `@`, `%` can survive into `base_url`, so no userinfo or query can be smuggled in; nothing restricts the scheme (TM-R10, `tests/security/test_Security__Known_Gaps.py::test_TM_R10__plain_http_base_url_is_accepted`). `Safe_Str__Access_Token` allows `[a-zA-Z0-9-_.]` (Safe_Str__Access_Token.py:L4-L10).

---

## `setup` (L32-L35)

**Purpose:** Fills `base_url` from `default_base_url()` when the caller passed none.
**Inputs & Assumptions:** `self.base_url` (trusted: CLI/remote config). Implicit: `SGIT_DEFAULT_BASE_URL` via `default_base_url`.
**Outputs & Effects:** sets `self.base_url` (L34); returns self.
**Depended on by:** every URL built in this class (`f'{self.base_url}/api/...'`). `CLI__Vault.create_sync` calls `api.setup()` (sgit_ai/cli/CLI__Vault.py:L37); `Vault__API__Auto.setup` calls it only for http(s) bases (Vault__API__Auto.py:L167).
**Open Questions:** none.

---

## `default_base_url` (L73-L76)

**Purpose:** The server when none is configured: env `SGIT_DEFAULT_BASE_URL` else `DEFAULT_BASE_URL = 'https://dev.send.sgraph.ai'` (L18).
**Inputs & Assumptions:** environment variable, trust: environment (A6). The threat model's TM-F15/TM-F22 record that this variable used to redirect existing vaults; the per-command server pin lives in the CLI (`CLI__Main.run`, `tests/security/test_Security__Fixed__Server_Pin.py`), not here. Nothing in this function or class checks the variable's scheme or host: `nothing found`.
**Outputs & Effects:** returns a string; no state.
**Depended on by:** `setup` L34; `CLI__Vault` L89, L378, L633, L646; `CLI__Token_Store` L115.
**Open Questions:** none.

---

## `tombstone_vault` (L367-L368)

**Purpose:** Alias of `delete_vault` for the live API (the in-memory double keeps a separate tombstone set, Vault__API__In_Memory.py:L120-L123).
**Depended on by:** `vault move`/destroy flows (outside this slice). No check beyond `delete_vault`'s.

---

## `close` (L389-L392)

**Purpose:** Drops kept-alive connections via `Vault__HTTP_Pool.close` (Vault__HTTP_Pool.py:L113-L123). Optional; process exit does the same.

---

## `_pool` (L381-L387)

**Purpose:** Lazily builds the one `Vault__HTTP_Pool` for this API object, under a module-level lock (`_POOL_INIT_LOCK`, L22) because a multi-chunk `batch_read` may be the first call from several threads (L383).
**Establishes:** exactly one pool per `Vault__API`, built with `tls_verify=bool(self.tls_verify)` (L386) — the pool's verify flag is fixed at first use; a later change to `self.tls_verify` is not reflected. Test: `tests/unit/network/api/test_Vault__HTTP_Pool.py::test_concurrent_first_call_builds_one_pool`.
**Depended on by:** `_send` L444.
**Open Questions:** none.
