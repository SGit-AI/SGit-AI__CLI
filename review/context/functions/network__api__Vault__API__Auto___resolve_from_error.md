## `_resolve_from_error` in sgit_ai/network/api/Vault__API__Auto.py (L47-L61)

**Purpose:** Decides whether an API `RuntimeError` means "this host has no live API" — the one signal that flips an http(s) base to the read-only static transport. Only the **batch endpoint** answering 404/405/501 counts (docstring L51-L55: a 404 from `/api/vault/read/...` is a missing object, which is what every fresh vault looks like on its first push).

**Inputs & Assumptions:**
- `error` (Exception): the `RuntimeError` from `Vault__API._api_error`, whose text is `API Error: HTTP <code> <reason>\n  Request: <METHOD> <url>\n ... Response: <body>` (Vault__API.py:L484-L490). Trust: the status line is ours; the **response body is host text embedded in the same string**.
- Implicit: `self.resolved`.

**Outputs & Effects:** bool; no state (the caller sets `resolved`).

**Block-by-Block:**
```python
# L56-L61
if self.resolved is not None: return False
message = str(error)
if BATCH_PATH not in message: return False          # '/api/vault/batch/'
return any(marker in message for marker in FALLBACK_MARKERS)   # 'HTTP 404', 'HTTP 405', 'HTTP 501'
```
- **What:** once resolved (either way) never re-resolve (L56-L57; test `test_once_resolved_it_stays_resolved`). Then two substring tests over the whole message.
- **Assumes:** `BATCH_PATH` appears in the message only when the request URL was the batch endpoint, and `HTTP 404` only when the status was 404. Both can also appear inside the host's `Response:` body, which `_api_error` appends verbatim (L489-L490). A 500 from the batch endpoint whose body says `HTTP 404` would resolve to static; a 404 from `/read/` whose body mentions `/api/vault/batch/` would too. `nothing found` separating status line from body. Tests cover the clean cases: `test_Vault__API__Auto.py` (object 404 → False; batch 404/405/501 → True; batch 500 → False; connection error → False).
- **Depended on by:** `_call` L72-L79: a True here makes the current call (whatever it was — including `write`/`batch`) re-run on the static transport, where writes raise `Vault__Read_Only_Transport_Error`.

**Cross-Function Dependencies:**
- Callers: `_call` L72.
- Note the batch endpoint is reached on the very first push through `Vault__Batch.execute_batch` or by `batch_read` (`_batch_read_chunk` L190 uses the same `/api/vault/batch/{vault_id}` URL for reads). A live server that answers 404 on `POST /api/vault/batch/<unknown vault>` for a vault that does not exist yet would flip a writable session to read-only on its first call; the comment at L51-L55 says the *read* 404 case was fixed, not the batch one. Observation; whether the live server 404s an unknown vault on the batch route is an open question.

**Open Questions:**
- unclear; need the live server's status for `POST /api/vault/batch/{vault_id}` when the vault has no files yet (first push). If 404, the auto transport would resolve to static before the first write.
