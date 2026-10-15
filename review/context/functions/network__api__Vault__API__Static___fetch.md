## `_fetch` in sgit_ai/network/api/Vault__API__Static.py (L112-L138)

**Purpose:** The byte source: `open()` for a local path, `urlopen` for http(s). Classifies failure: `None` for absent (404 / missing file / refused traversal), `Vault__Static_Object_Error` for any other HTTP status, `Vault__Static_Transport_Error` for a dead host.

**Inputs & Assumptions:**
- `location` (str | None): from `_location`/`read_root_file`.
- Implicit: `HTTP_TIMEOUT = 30` (L37), `self._ssl_context(location)` (Vault__API.py:L370-L379 — unverified context when `tls_verify` is False and the URL is https).

**Outputs & Effects:**
- Records the location (L119) before fetching.
- Local: `None` unless `os.path.isfile` (L121-L122); reads the file (follows symlinks — `open` on a link path; `isfile` follows too).
- HTTP: `urlopen(location, timeout=30, context=...)` (L126-L128). **urllib follows redirects by default** here (unlike the API path `_send`, which raises on 3xx, and `fetch_presigned`, which re-checks each hop). No auth headers are involved, so a redirect leaks nothing of ours; the destination of a redirect is unconstrained: `nothing found`. Body read in full, no cap: `nothing found`.
- 404 → `None` (L130-L131, "the ONLY 'absent' answer"); other `HTTPError` → `Vault__Static_Object_Error` (L132-L133); `URLError`/`socket.timeout`/`ConnectionError`/`OSError` → `Vault__Static_Transport_Error` naming the root (L134-L138).

**Block-by-Block:** as above; L117-L118 `None` location (traversal refused) → absent.

**Cross-Function Dependencies:**
- Callers: `read` L101, `batch_read.fetch_one` L163, `read_root_file` L224-L225.
- Tests: `test_dead_host_raises_naming_host_not_empty_vault`, `test_resetting_host_raises_transport_error`, `test_non_404_status_is_typed_and_fails_soft_in_batch`, `test_http_404_is_none`.

**Open Questions:** none.
