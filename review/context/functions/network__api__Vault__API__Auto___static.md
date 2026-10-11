## `_static` in sgit_ai/network/api/Vault__API__Auto.py (L36-L42)

**Purpose:** Lazily builds the `Vault__API__Static` sibling with the same `base_url`, `tls_verify`, `debug_log` and **no access token** (L39).

**Establishes:** every request routed to the static transport carries no API credential. This is what `test_Vault__API__Static.py::test_requests_never_contain_key_material` checks on the recorded request list (asserting on behaviour, L120-L130).

**Depended on by:** `setup` L32, `_call` L65, L78. No open questions.
