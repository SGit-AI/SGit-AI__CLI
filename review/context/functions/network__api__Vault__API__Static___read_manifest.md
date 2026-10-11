## `_read_manifest` in sgit_ai/network/api/Vault__API__Static.py (L227-L240)

**Purpose:** `manifest.json` from the site root as a dict; `{}` on anything but a dead host.

**Inputs & Assumptions:** host-published JSON. Trust: **untrusted**; no schema check beyond `json.loads` (L238). Consumers index `manifest.get('objects', [])` and `entry.get('file_id')` (`list_files` L215) — a non-dict `objects` element raises `AttributeError` there (not caught).

**Outputs & Effects:** dict or `{}`. `Vault__Static_Transport_Error` re-raised (L231-L232); every other exception → `{}` (L233-L234, L239-L240), so a 403 on the manifest (an `Object_Error`) reads as "no manifest".

**Cross-Function Dependencies:** callee `read_root_file`; caller `list_files` L212.

**Open Questions:** none.
