## `list_files` in sgit_ai/network/api/Vault__API__Static.py (L202-L216)

**Purpose:** Local: walk the folder. HTTP: enumerate from a host-published `manifest.json` (a static host has no listing endpoint).

**Inputs & Assumptions:** `vault_id` (unused for listing), `prefix`. Local `prefix` is joined onto root (L207) with no containment check (callers pass literals; `nothing found` otherwise). HTTP: the manifest is **host-supplied JSON** (`_read_manifest` L227-L240).

**Outputs & Effects:**
- Local: sorted relative paths (L210-L211), symlinked files included as names.
- HTTP: `[str(entry.get('file_id', ''))` for `manifest['objects']`, filtered by prefix (L215-L216). Any string the manifest names is returned; it then feeds `read`/`batch_read` (`_location` URL-encodes each segment) and, in push, `_is_first_push` (empty → "first push") — but push cannot write to a static host anyway (`batch`/`write` raise).
- Any error reading/parsing the manifest other than a dead host → `[]` (`_read_manifest` L233-L240), i.e. "no files". Combined with `Vault__Sync__Push._is_first_push` L722-L725 this would read as a first push; the subsequent `_upload_bare_to_server` then raises `Vault__Read_Only_Transport_Error` from `batch` — nothing is written anywhere.

**Cross-Function Dependencies:** callee `_read_manifest` → `read_root_file` → `_fetch`. Callers: `Vault__API__Auto.list_files` when static; mirror/publish tooling (outside slice).

**Open Questions:** none.
