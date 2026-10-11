# `Vault__HTTP_Pool` trivial methods — sgit_ai/network/api/Vault__HTTP_Pool.py

Fields (L52-L58): `tls_verify : bool = True`, `timeout_seconds : Safe_UInt = 120`, `max_idle_seconds : Safe_UInt = 30`, `idle` ({key: [(conn, released_at)]}), `warm` (set of `id(conn)`), `lock`, `ctx`. Built only by `Vault__API._pool` (Vault__API.py:L386) with `tls_verify=bool(api.tls_verify)`.

---

## `setup` (L60-L64)
Initialises `idle = {}`, `warm = set()`, `lock = threading.Lock()`. Precondition for every other method; `_pool` calls it (L386).

## `release` (L100-L103)
Under the lock: marks `id(conn)` warm and appends `(conn, monotonic())` to the key's idle bucket. **Establishes** `warm` = "has served at least one request", which `acquire` returns and `_send` uses to decide a resend (Vault__API.py:L459). Called by `_send` L465 after a fully read response.

## `discard` (L105-L111)
Removes the warm mark and closes the connection (errors swallowed). Called by `_send` on any transport failure (L458) and on `Connection: close`/env switch (L463); by `acquire` for a non-reusable idle connection (L97).

## `close` (L113-L123)
Swaps the buckets out under the lock, then closes every idle connection. Connections currently checked out are not touched (they are not in `idle`). Caller: `Vault__API.close` L392. Test: `test_close_drops_pooled_connections`.

## `socket_timeout` (L153-L155)
`float(timeout_seconds)` or `None` when 0. Default 120 s per socket operation (docstring L36-L37: urlopen had none). Used by `open` L162-L163, `open_via_proxy` L184-L187. Test: `test_sockets_have_a_timeout`.

## `proxy_parts` (L165-L166)
`urlsplit(proxy)` with `http://` prepended when the proxy string has no scheme. Input: the proxy URL from the environment (`getproxies()`, via `proxy_for`). Used by `proxy_auth_header` L170, `open_via_proxy` L180.
