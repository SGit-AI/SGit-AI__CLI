## `read` in sgit_ai/network/api/Vault__API__Static.py (L92-L110)

**Purpose:** One object by GET/open(), trying each candidate layout; `None` means absent. The first success pins the layout (`self.layout = layout`, L106).

**Inputs & Assumptions:** `vault_id`, `file_id` (str; may be manifest-supplied).

**Outputs & Effects:**
- Returns bytes, or `None` (absent on every layout), and re-raises the last `Vault__Static_Object_Error` when no layout had it and one gave a non-404 status (L108-L109). `Vault__Static_Transport_Error` from `_fetch` propagates at once (dead host).
- **Contract difference** from `Vault__API.read`: absent is `None` here, an exception there (Vault__API.py:L98-L100 via `_api_error`). Callers in this slice tolerate both (`Vault__Sync__Base._require_readable_server_ref` L85-L90: `if not data: return`).
- State: `layout` becomes sticky across the object's lifetime — a host that serves one object at `api/vault/read/...` and the rest flat would be read at the first layout only afterwards.

**Block-by-Block:** L98-L107 loop; L102-L104 keep the object error and try the next layout (A5); L105-L107 success pins layout and returns.

**Cross-Function Dependencies:** callee `_fetch` (L112-L138), `_location`, `_candidate_layouts`. Callers: `batch_read` L152 (sniff), every `api.read` call site when the transport is static (via `Vault__API__Auto._call`), `read_root_file` does **not** use it (goes to `_fetch` directly).

What the host can return that is accepted: any bytes; verification is the caller's (`Vault__Verified_Write`). Tests: `test_absent_object_is_none`, `test_http_404_is_none`, `Test_Vault__API__Static__SP1_Integrity` (corrupt/swapped objects refused by the download paths, not here).

**Open Questions:** none.
