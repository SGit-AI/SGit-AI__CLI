## `setup` in sgit_ai/network/api/Vault__API__Auto.py (L28-L34)

**Purpose:** Transport resolution at construction: a `base_url` that is not `http://`/`https://` is a folder → `LOCAL`, static transport, no network ever; an http(s) base stays unresolved until the first call (`_call`).

**Inputs & Assumptions:** `self.base_url` (operator-configured via `CLI__Vault.create_api`, sgit_ai/cli/CLI__Vault.py:L40-L60, when `--transport auto`, the default).

**Outputs & Effects:**
- Non-http base: `resolved = LOCAL` (L31), `self._static().setup()` (L32) — the static object is built with `access_token=None` (L39, "I2: no key/token to a static host"). Returns without `Vault__API.setup`, so `base_url` is never defaulted for a folder.
- http(s) or empty base: `super().setup()` (L34) → default base URL when empty.
- **Establishes:** `_is_static()` is True for a folder before any call; a folder path can never receive the access token (the static object has none). Test: `test_Vault__API__Static.py::Test_Vault__API__Auto::test_folder_resolves_local`.

**Cross-Function Dependencies:** callees `_static` (L36-L42), `Vault__API__Static.setup` (L50-L54, raises on empty base), `Vault__API.setup`. Caller: `CLI__Vault.create_sync` L37.

**Open Questions:** none.
