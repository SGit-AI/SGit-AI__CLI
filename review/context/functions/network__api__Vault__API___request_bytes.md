## `_request_bytes` in sgit_ai/network/api/Vault__API.py (L401-L428)

**Purpose:** One API call with the transient-status retry loop: up to 4 attempts (`[0] + RETRY_DELAYS`, delays 2/4/8 s, L16, L412) for HTTP 429/502/503/504 (L15), over the kept-alive pool via `_send`. Decides what is "idempotent" (GET by default, L408-L409), which `_send` uses for the stale-keep-alive resend.

**Inputs & Assumptions:**
- `method`, `url`, `headers`, `data`, `idempotent` (None → `method == 'GET'`).
- Implicit: `self.debug_log` (optional `CLI__Debug_Log`).

**Outputs & Effects:**
- Returns the raw body (bytes) of the first 2xx response.
- Raises `RuntimeError` built by `_api_error` for any HTTP status ≥ 300 (non-transient at once, transient after the last attempt — L427, L428). The message contains the status, method, URL, masked headers and the response body.
- Connection-level failures from `_send` surface as `URLError` (L461), not caught here, so **no retry on connection errors** — only on the listed HTTP statuses.
- Side effect: every attempt, including the ones that will be retried, re-sends `data` — a non-idempotent write (PUT/POST/DELETE) that the server applied before answering 502 is sent again (L424-L426). Harmless for content-addressed objects; for a CAS op the second attempt sees `conflict` (its own bytes are now current). Test: `test_Vault__HTTP_Pool.py::test_transient_502_retries_then_succeeds_on_same_connection` (GET), `test_429_throttled_is_retried_like_a_5xx`, `test_transient_exhausted_raises_last_error`.

**Block-by-Block:**

```python
# L408-L409
if idempotent is None:
    idempotent = method.upper() == 'GET'
```
- **Establishes:** PUT/POST/DELETE are non-idempotent unless the caller says otherwise; only `_batch_read_chunk` passes `idempotent=True` (L193).

```python
# L412-L427
for attempt, delay in enumerate([0] + RETRY_DELAYS):
    if delay: time.sleep(delay)
    ...
    try:
        status, body = self._send(method, url, headers, data, idempotent)
        return body
    except HTTPError as e:
        if e.code in TRANSIENT_STATUS_CODES and attempt < len(RETRY_DELAYS):
            last_error = e; continue
        raise self._api_error(method, url, headers, e, data_size=data_size)
```
- **What:** retry on transient, raise otherwise.
- **Assumes:** `_send` raises `HTTPError` for ≥ 300 (L466-L467) and that a 3xx must not be followed — it is not (it reaches `_api_error`, which adds the redirect hint L496-L504).
- **Depended on by:** `Vault__API__Auto._resolve_from_error` (string-matches `HTTP 404/405/501` and the batch path in this message); `_batch_read_chunk_with_fallback` (`HTTP 502/503`); `Vault__Index_Sync.upload` L189-L191 (`conflict`/`409`/`412` in the text); `_classify_exception` (`HTTP 404/403`).

**Cross-Function Dependencies:**
- Callees `_send` (L430-L468), `_api_error` (L470-L510), `debug_log.log_request/log_response/log_error` (sgit_ai/cli/CLI__Debug_Log.py:L11-L33; logs method, URL, sizes, status — not headers or bodies).
- Callers: `_request` L396, `read` L100.

**Open Questions:** none.
