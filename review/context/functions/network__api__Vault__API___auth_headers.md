## `_auth_headers` in sgit_ai/network/api/Vault__API.py (L78-L90)

**Purpose:** Builds the header set every API request carries: the access token under two names (`x-sgraph-access-token`, `X-API-Key`) plus whatever the caller adds (content type, `x-sgraph-vault-write-key`). It is the only place the access token leaves the process, so where these headers go decides who can learn the token.

**Inputs & Assumptions:**
- `extra` (dict | None): caller-supplied headers. Trust: trusted (internal callers only; the write key arrives through `extra`, L94-L95, L104, L120-L121).
- Implicit: `self.access_token` (Safe_Str__Access_Token), set by the CLI from the token store.
- Precondition: the headers are sent only to `self.base_url`'s host. Established by `_send` (L434-L436, L466-L467: redirects raise instead of being followed) and by `fetch_presigned`, which never calls this function (L37-L56). Test: `tests/unit/network/api/test_Vault__HTTP_Pool.py::test_redirects_are_not_followed`.

**Outputs & Effects:**
- Returns a new dict. No state writes.
- Postcondition: when `access_token` is falsy the dict has no auth header at all (L84); the request still goes out.

**Block-by-Block:**

```python
# L84-L87
if self.access_token:
    token = str(self.access_token)
    headers['x-sgraph-access-token'] = token
    headers['X-API-Key']             = token
```
- **What:** Same token on two header names (comment L79-L82: a FastAPI gate checks `X-API-Key`, the vault app checks `x-sgraph-access-token`).
- **Assumes:** both gates expect the same value (comment L81-L82). Nothing here checks the scheme the token will travel over: an `http://` base_url sends it in clear (TM-R10).
- **Depended on by:** every `_request` call in this class; `_api_error` masks any header whose name contains `token` or `key` (L478-L482), which covers both names and the write-key header.

```python
# L88-L89
if extra:
    headers.update(extra)
```
- **What:** caller headers override.
- **Assumes:** `extra` never carries a key that should not be sent; all callers are in this file.

**Cross-Function Dependencies:**
- Callers: `write` L94, `read` L100, `delete` L104, `batch` L120, `_batch_read_chunk` L191, `presigned_*` L309, L322, L334, L345, `list_files` L355, `delete_vault` L363.
- Shared state: `self.access_token` is read-only here.

**Open Questions:**
- none.
