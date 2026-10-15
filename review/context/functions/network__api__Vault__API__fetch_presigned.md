## `fetch_presigned` in sgit_ai/network/api/Vault__API.py (L37-L56)

**Purpose:** GET a host-supplied presigned URL (large blobs, and the per-file 502 fallback in `batch_read`). Separate from the pooled `_send` path: it uses `urllib` with a redirect handler that re-applies `check_presigned_url` on every hop, and it sends none of the API auth headers.

**Inputs & Assumptions:**
- `url` (str): from the server's `presigned_read_url` response. Trust: **untrusted**.
- `timeout` (int, default 300 s): per-socket timeout passed to `opener.open` (L55).
- Implicit: `self.tls_verify` via `_ssl_context` (L52).
- Precondition: the URL passes `check_presigned_url` — established at L43 before any network activity (test: `tests/security/test_Security__Fixed__Host_Substitution.py::test_fetch_presigned_checks_before_any_request`).

**Outputs & Effects:**
- Returns the full response body as bytes (L56). No cap on size: the client reads whatever the destination sends: `nothing found`.
- External interaction: one or more GETs (redirect chain) to host-chosen destinations within the `check_presigned_url` rule.
- No API headers are attached (`_auth_headers` is not called): the access token is not sent to the presigned host. urllib adds its default `User-Agent`.

**Block-by-Block:**

```python
# L43
self.check_presigned_url(url)
```
- **What:** scheme/host rule on the first URL.
- **Why here:** before `build_opener(...).open`, so a refused URL never connects.

```python
# L46-L51
class Checked_Redirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        api.check_presigned_url(newurl)
        return super().redirect_request(...)
handlers = [Checked_Redirects()]
```
- **What:** every redirect target is held to the same rule (comment L46-L48: an https URL may not bounce to an internal http address).
- **Assumes:** urllib routes every 3xx through `redirect_request`; the default handler also caps redirects at `max_redirections` (stdlib). Test: `Test_Fixed__Presigned_Redirects::test_a_redirect_to_an_internal_address_is_refused`.
- **Establishes:** each hop's destination satisfies `check_presigned_url`.

```python
# L52-L54
context = self._ssl_context(url)
if context is not None:
    handlers.append(urllib.request.HTTPSHandler(context=context))
```
- **What:** when `tls_verify` is False and the URL is https, install an unverified context (`_ssl_context` L370-L379).
- **Assumes:** the context chosen for the *first* URL applies to the whole redirect chain (the handler is installed once); `_ssl_context` returns None when the first URL is http, so an http→https redirect under `tls_verify=False` would verify. Observation only.

```python
# L55-L56
with urllib.request.build_opener(*handlers).open(url, timeout=timeout) as resp:
    return resp.read()
```
- **What:** fetch and return the body. HTTP errors raise `HTTPError` (urllib default), network errors `URLError`.
- **Assumes:** the caller verifies the bytes (docstring L41: "Callers still verify the bytes against their id"). Established by callers: `Vault__Sync__Pull` L462 + `_save` L276-L290 (Verified_Write), `Vault__Sync__Clone` L337/L423 → `Clone__Workspace.save_file` L53-L64, `Vault__Sync__Sparse` L115-L116 → `_save_verified` L224-L231, and `_presigned_read_fallback` L255 whose result flows into `batch_read`'s `payloads` for the caller to verify (see that record).

**Cross-Function Dependencies:**
- Callee `check_presigned_url` (internal, L58-L71): the whole destination rule.
- Callee `_ssl_context` (internal, L370-L379).
- Callers: `_presigned_read_fallback` L255; `Vault__Sync__Pull` L462; `Vault__Sync__Clone` L337, L423; `Vault__Sync__Sparse` L115, L163.
- Shared state: none (does not use the connection pool).

**Open Questions:**
- unclear; need to inspect whether any caller uses the returned bytes without a content-address check. Within this slice none does; `Vault__Sync__Base.fetch_tree_lazy` (sgit_ai/core/Vault__Sync__Base.py:L598-L665) writes `api.read`/`batch_read` bytes unverified but has no callers (`grep fetch_tree_lazy` finds only its definition).
