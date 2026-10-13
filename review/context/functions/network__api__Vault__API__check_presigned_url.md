## `check_presigned_url` in sgit_ai/network/api/Vault__API.py (L58-L71)

**Purpose:** The one rule for a URL the host hands back (presigned S3 read URL, multipart PUT part URLs): which destinations the client will open. Everything that fetches or PUTs to a host-supplied URL goes through it (`fetch_presigned` L43 and each redirect hop L48; `Vault__Batch._upload_large` L139).

**Inputs & Assumptions:**
- `url` (str | None): host-supplied. Trust: **untrusted** (it is the body of an API response, `presigned_read_url` L339-L345, `presigned_initiate` L301-L313).
- Implicit: `self.base_url` (own server), used to allow plain-http to the same host (L67-L69).

**Outputs & Effects:**
- Returns `url` unchanged when accepted; raises `ValueError` otherwise (L71). No state.

**Block-by-Block:**

```python
# L63-L66
parts = urlsplit(str(url or ''))
host  = (parts.hostname or '').lower()
if parts.scheme == 'https' and host:
    return url
```
- **What:** Any `https://` URL with a non-empty hostname passes.
- **Assumes:** that the destination host being arbitrary is acceptable as long as TLS is used — the client will GET (and in `_upload_large`, PUT its ciphertext to) whatever https host the API names. No allow-list of hosts, no comparison with `base_url`'s host, no port check: `nothing found`. The threat model's TM-F07 row describes the fix as "https, or http to loopback only", which matches.
- **Establishes:** scheme ∈ {https} or the http branch below.
- **Depended on by:** `fetch_presigned`'s redirect handler (every hop is re-checked, L46-L49), `_upload_large` L139.

```python
# L67-L70
own_host = (urlsplit(str(self.base_url or '')).hostname or '').lower()
if parts.scheme == 'http' and host and (host in ('127.0.0.1', 'localhost', '::1') or
                                        (host == own_host and str(self.base_url).startswith('http://'))):
    return url
```
- **What:** `http://` only to loopback, or to the configured server's own host when that server is itself `http://`.
- **Assumes:** hostname equality means the same server; the port is not compared (`http://127.0.0.1:<any>` passes — `tests/security/test_Security__Fixed__Host_Substitution.py::Test_Fixed__Presigned_URLs::test_allowed` uses `127.0.0.1:9000`). `localhost` is compared as a name, not resolved. Only the three literal loopback spellings count; `127.0.0.2` or `[::ffff:127.0.0.1]` are refused (fall through to L71).
- **Establishes:** for `http://`, the destination is loopback or the own server.

```python
# L71
raise ValueError(...)
```
- **What:** everything else (`file:`, `data:`, `ftp:`, scheme-less, empty, non-own http) is refused. Tests: `Test_Fixed__Presigned_URLs::test_refused` (8 cases), `Test_Fixed__Presigned_Redirects` (redirect to 169.254.169.254 refused; own http host allowed, other LAN host refused).

**Cross-Function Dependencies:**
- Callers: `fetch_presigned` L43, L48 (internal); `Vault__Batch._upload_large` L139 (`sgit_ai/core/actions/push/Vault__Batch.py`). `Vault__API__Static.presigned_read_url` (Vault__API__Static.py:L186-L200) returns `file://...` for a local folder; any caller that then uses `Vault__API.fetch_presigned` hits this check and is refused — see Open Questions.
- Shared state: none.
- Invariant coupling: the bytes fetched from an accepted URL are still unverified here; content-address verification is the caller's job (`Vault__Sync__Pull._fetch_missing_objects` L276-L290 `_save`; `Clone__Workspace.save_file` L53-L64; `Vault__Sync__Sparse._save_verified` L224-L231). The check decides *where the client connects*, not *what it accepts*.

**Open Questions:**
- unclear; need to inspect how a large blob (> `LARGE_BLOB_THRESHOLD`) in a **local-folder** static vault is fetched: `Vault__API__Static.presigned_read_url` hands back `file://` (L195), `fetch_presigned` refuses `file://` (L43 → L71), and `Vault__API__Static` does not override `fetch_presigned`. `tests/unit/network/api/test_Vault__API__Static.py::test_large_blob_clone_over_http` covers only the http case.
