## `_call` in sgit_ai/network/api/Vault__API__Auto.py (L63-L79)

**Purpose:** The dispatcher: static when resolved static/local; otherwise the live `Vault__API` method, remembering `API` on the first success and flipping to `STATIC` (with a stderr note) when `_resolve_from_error` says the host has no live API.

**Inputs & Assumptions:** `method_name` (one of the seven wrappers below), args. Implicit: `resolved`.

**Outputs & Effects:**
- Returns the target method's result.
- State: `resolved = API` on first success of **any** routed method (L68-L69); `resolved = STATIC` on the fallback signal (L74), printed once to stderr (L75-L77; the note is also what `describe()` reports and `CLI__Vault.describe_transport` prints — "visible, never silent", module docstring L10-L14).
- On the flip, the **same call is re-issued to the static transport** (L78): for `read`/`batch_read`/`list_files`/`presigned_read_url` that yields static semantics (404 → `None`, manifest listing); for `write`/`delete`/`batch` it raises `Vault__Read_Only_Transport_Error` (Vault__API__Static.py:L244-L250). So a push whose first batch POST gets a 404/405/501 ends with the read-only-transport message, not the API error.
- Any other `RuntimeError` re-raises (L79); non-`RuntimeError` exceptions (`URLError` for a dead host) bypass the handler entirely — "a dead host raises either way (F5)", test `test_connection_failure_never_resolves`.

**Block-by-Block:**
```python
# L64-L65
if self._is_static():
    return getattr(self._static(), method_name)(*args, **kwargs)
```
```python
# L66-L79
try:
    result = getattr(super(), method_name)(*args, **kwargs)
    if self.resolved is None: self.resolved = Enum__Transport.API
    return result
except RuntimeError as error:
    if self._resolve_from_error(error):
        self.resolved = Enum__Transport.STATIC
        print(f'note: {self.base_url} has no live API ...', file=sys.stderr)
        return getattr(self._static(), method_name)(*args, **kwargs)
    raise
```
- **Assumes:** `super()` inside a method of a Type_Safe subclass binds to `Vault__API`'s method — it does (`getattr(super(), name)`).
- **Assumes:** methods not listed in the wrappers (`delete_vault`, `tombstone_vault`, `presigned_initiate/complete/cancel`, `fetch_presigned`, `check_presigned_url`) are inherited from `Vault__API` unchanged and never consult `resolved`: a `delete_vault` on a resolved-static `Vault__API__Auto` still issues the live DELETE. `nothing found` routing those.

**Cross-Function Dependencies:**
- Callers: the wrappers `read` L81, `batch_read` L84, `presigned_read_url` L87, `list_files` L90, `write` L93, `delete` L96, `batch` L99.
- Callee `_resolve_from_error` L47-L61; `Vault__API__Static.*`.
- Tests: `test_Vault__API__Static.py::Test_Vault__API__Auto::test_http_static_host_flips_to_static` (stderr note + describe).

**Open Questions:**
- see `_resolve_from_error` (first-push 404 on the batch route).
