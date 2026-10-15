## `_send` in sgit_ai/network/api/Vault__API.py (L430-L468)

**Purpose:** One HTTP exchange on a pooled connection: acquire, send, read the whole body, return the connection or discard it, and raise `HTTPError` for any status ≥ 300 (redirects included — the token headers are never replayed to another host). Decides the one case where a request is resent: a warm connection failed, the request is idempotent, and this is the first retry.

**Inputs & Assumptions:**
- `method`, `url`, `headers` (incl. token/write key), `data`, `idempotent` (bool), `retried` (bool).
- Implicit: `Vault__HTTP_Pool` via `_pool()`; env `SGIT_HTTP_NO_KEEPALIVE` (L462).
- Precondition: `url`'s scheme/host/port map to the pool key (`key_for`, Vault__HTTP_Pool.py:L67-L73); the request target is the path (or absolute URI through a plain-http proxy, `request_target` L199-L209).

**Outputs & Effects:**
- Returns `(status, body)` for status < 300.
- Raises `HTTPError(url, status, reason, headers, BytesIO(body))` for ≥ 300 (L466-L467) **after** the connection has been released/discarded (L462-L465), so an error response does not poison the pool. Test: `test_http_error_shape_and_body_preserved`, `test_redirects_are_not_followed`.
- Raises `URLError` wrapping any `http.client.HTTPException`/`OSError` between request and full body read (L457-L461), after discarding the connection.
- Resend: when `warm and idempotent and not retried`, calls itself with `retried=True`, which makes `acquire(fresh=True)` skip the idle bucket (L445; Vault__HTTP_Pool.py:L84-L98). A write is never resent (`idempotent` False): test `test_stale_keep_alive_never_resends_a_write`; the read resend: `test_stale_keep_alive_is_retried_for_idempotent_reads`, `test_stale_keep_alive_read_is_resent_even_when_liveness_check_misses`; a failure on a fresh connection is not retried: `test_fresh_connection_failure_is_not_retried`.

**Block-by-Block:**

```python
# L444-L449
pool            = self._pool()
key, conn, warm = pool.acquire(url, fresh=retried)
target          = pool.request_target(key, url)
send_headers    = {'User-Agent': 'sgit-ai'}
send_headers.update(pool.proxy_headers(key))
send_headers.update(headers or {})
```
- **What:** connection keyed by (scheme, host, port, verify, proxy); headers = UA + proxy auth (plain-http proxy only) + caller's.
- **Assumes:** the pool never hands out a connection keyed for a different host/verify setting — established by `key_for` (the key is the dict key, `acquire` L91).

```python
# L450-L461
try:
    conn.request(method, target, body=data, headers=send_headers)
    response = conn.getresponse()
    status, reason = response.status, response.reason
    body    = response.read()
    closing = response.will_close or (response.getheader('Connection', '') or '').lower() == 'close'
except (http.client.HTTPException, OSError) as error:
    pool.discard(key, conn)
    if warm and idempotent and not retried:
        return self._send(..., retried=True)
    raise URLError(error) from error
```
- **What:** full-body read before anything else; discard on any failure so a half-read response never serves the next caller (docstring L440).
- **Assumes:** `response.read()` reads to the declared length; a server that declares more than it sends raises `IncompleteRead` (an `HTTPException`) → discard (test `test_fresh_connection_failure_is_not_retried` uses the `short` script). No cap on body size: `nothing found`.
- **Assumes:** the socket timeout set at open (`socket_timeout`, default 120 s, Vault__HTTP_Pool.py:L53, L153-L155) bounds each operation.

```python
# L462-L465
if closing or os.environ.get('SGIT_HTTP_NO_KEEPALIVE'):
    pool.discard(key, conn)
else:
    pool.release(key, conn)
```
- **What:** honour the server's close; env switch for A/B (test `test_env_switch_disables_keep_alive`).

```python
# L466-L468
if status >= 300:
    raise HTTPError(url, status, reason, response.headers, io.BytesIO(body))
return status, body
```
- **Establishes:** no automatic redirect following on the API path (the only redirect-following fetch is `fetch_presigned`, which carries no auth headers).

**Cross-Function Dependencies:**
- Callees (all in Vault__HTTP_Pool.py): `acquire` L84-L98, `request_target` L199-L209, `proxy_headers` L192-L197, `discard` L105-L111, `release` L100-L103.
- Callers: `_request_bytes` L417.
- Shared state: the pool's `idle`/`warm` sets, under the pool lock.

**Open Questions:** none.
