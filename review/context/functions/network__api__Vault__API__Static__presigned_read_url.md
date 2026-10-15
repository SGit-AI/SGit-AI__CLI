## `presigned_read_url` in sgit_ai/network/api/Vault__API__Static.py (L186-L200)

**Purpose:** "Presigned" URL for a large blob on a static host is just the object's own URL (http) or `file://<path>` (local), so the existing large-blob paths work unmodified (docstring L187-L189).

**Inputs & Assumptions:** `vault_id`, `file_id`.

**Outputs & Effects:**
- Local: `{'url': 'file://' + path, 'expires_in': 0}` for the first layout whose file exists (L192-L195); raises `Vault__Static_Transport_Error('not found in folder: ...')` when none does (L199-L200).
- HTTP: `{'url': <first candidate layout's URL>}` **without checking it exists** (L196-L198) — the first candidate is `API_PATH` unless `layout` is already pinned, so on an unpinned object the returned URL may be the wrong layout; the subsequent `fetch_presigned` would then 404 (urllib `HTTPError`).
- The consumer is `Vault__API.fetch_presigned` (clone L337/L423, pull L462, sparse L115/L163, `_presigned_read_fallback` L255), which applies `check_presigned_url`: `https://` passes; `http://` passes only for loopback or the own `http://` base host (so a plain-http static host serving its own blobs passes); **`file://` is refused** (Vault__API.py:L71).

**Cross-Function Dependencies:** `_location`, `_record`, `_candidate_layouts`. Tests: `test_large_blob_clone_over_http` (http, flat layout, 5 MB).

**Open Questions:**
- unclear; need to inspect whether a > 4 MB blob can be cloned from a **local folder** static vault at all: this returns `file://`, `fetch_presigned` refuses it, and no local-folder large-blob test exists.
- unclear; whether returning the unverified `API_PATH` URL for an unpinned http object is reachable (large blobs are fetched after small ones in clone, by which time `layout` is pinned by `batch_read`).
