"""Vault__HTTP_Pool — keep-alive connections for Vault__API, stdlib only.

Why: every API call used urllib's urlopen, which sends `Connection: close` and
tears the TLS session down after each response. A clone is hundreds of small
requests (one per commit on a linear chain, one per 50 trees or blobs), and
~0.11 s of every ~0.43 s request was the TLS handshake. Reusing the connection
answers a warm request in ~0.16 s.

Rules (these are the whole point — see the session note of 2026-10-02):

  * Keyed by (scheme, host, port, verify, proxy). A `--no-verify-tls`
    connection can never serve a verifying caller; a presigned S3 host never
    shares a socket with the API host.
  * Shared across threads with a lock (checkout / checkin), not thread-local:
    `batch_read` and the blob download each spin up a fresh ThreadPoolExecutor
    per call, so thread-local connections would be thrown away after one level.
  * An idle connection is checked before it is handed out: one the peer has
    closed (readable == FIN, or TLS bytes pending) is dropped, and one idle for
    longer than `max_idle_seconds` is dropped unconditionally — a NAT that
    silently forgot the mapping sends no FIN, and with no FIN the first write
    would block. So a `push` that encrypts for a minute between its ref read
    and its batch write gets a fresh socket, exactly as urlopen gave it.
  * Any exception between request and the fully-read body discards the
    connection — a half-read response must never serve the next caller.
  * The server closing its side (`Connection: close`, or `will_close`) also
    discards it.
  * Reconnect-and-resend is the CALLER's decision (Vault__API knows which
    requests are idempotent); this class only reports whether the connection
    it handed out had already served a request (`warm`), which is the only
    case where "remote end closed without response" is a stale keep-alive
    rather than a real failure. `acquire(fresh=True)` bypasses the idle
    bucket for that resend, so a second stale socket cannot fail it again.
  * Proxies: honours HTTP(S)_PROXY / NO_PROXY exactly as urllib does, via a
    CONNECT tunnel for https and an absolute-URI request (plus
    Proxy-Authorization per request) for http.
  * Every socket operation has a timeout (`timeout_seconds`): urlopen had
    none, and a kept-alive socket is the one place a silent peer can hang.
"""
import base64
import http.client
import select
import ssl
import threading
import time
from   urllib.parse                                      import urlsplit, unquote
from   urllib.request                                    import getproxies, proxy_bypass
from   osbot_utils.type_safe.Type_Safe                   import Type_Safe
from   osbot_utils.type_safe.primitives.core.Safe_UInt   import Safe_UInt


class Vault__HTTP_Pool(Type_Safe):
    tls_verify       : bool      = True
    timeout_seconds  : Safe_UInt = 120     # per socket operation; 0 = no timeout
    max_idle_seconds : Safe_UInt = 30      # an idle connection older than this is not reused
    idle             : object    = None    # {key: [(conn, released_at), ...]} — not checked out
    warm             : object    = None    # set of id(conn) that have served at least one request
    lock             : object    = None
    ctx              : object    = None    # the ssl context, built once

    def setup(self):
        self.idle = {}
        self.warm = set()
        self.lock = threading.Lock()
        return self

    # ------------------------------------------------------------------ keys
    def key_for(self, url: str) -> tuple:
        parts  = urlsplit(url)
        scheme = (parts.scheme or 'http').lower()
        host   = parts.hostname or ''
        port   = parts.port or (443 if scheme == 'https' else 80)
        proxy  = self.proxy_for(scheme, host)
        return (scheme, host, port, bool(self.tls_verify), proxy or '')

    def proxy_for(self, scheme: str, host: str) -> str:
        """The proxy URL urllib would use for this scheme+host, or ''."""
        proxies = getproxies()
        proxy   = proxies.get(scheme) or ''
        if not proxy or proxy_bypass(host):
            return ''
        return proxy

    # ------------------------------------------------------------- checkout
    def acquire(self, url: str, fresh: bool = False):
        """(key, conn, warm). `warm` is True when conn has served a request before.
        fresh=True never reuses an idle connection (the stale-keep-alive resend)."""
        key = self.key_for(url)
        if not fresh:
            while True:
                with self.lock:
                    bucket = self.idle.get(key) or []
                    if not bucket:
                        break
                    conn, released_at = bucket.pop()
                if self.is_reusable(conn, released_at):
                    return key, conn, id(conn) in self.warm
                self.discard(key, conn)
        return key, self.open(key), False

    def release(self, key: tuple, conn) -> None:
        with self.lock:
            self.warm.add(id(conn))
            self.idle.setdefault(key, []).append((conn, time.monotonic()))

    def discard(self, key: tuple, conn) -> None:
        with self.lock:
            self.warm.discard(id(conn))
        try:
            conn.close()
        except Exception:
            pass

    def close(self) -> None:
        with self.lock:
            buckets   = list(self.idle.values())
            self.idle = {}
            self.warm = set()
        for bucket in buckets:
            for conn, _released_at in bucket:
                try:
                    conn.close()
                except Exception:
                    pass

    # ------------------------------------------------------------- liveness
    def is_reusable(self, conn, released_at: float) -> bool:
        if int(self.max_idle_seconds) and time.monotonic() - released_at > int(self.max_idle_seconds):
            return False
        return not self.is_dropped(conn)

    def is_dropped(self, conn) -> bool:
        """True when the peer has closed (or something arrived we did not ask
        for): a readable idle socket is a FIN or stray bytes, either way not a
        connection to send a request on. Same test urllib3 uses."""
        sock = getattr(conn, 'sock', None)
        if sock is None:
            return False                               # never connected yet — fine to use
        try:
            pending = getattr(sock, 'pending', None)   # TLS: bytes already decrypted and waiting
            if pending is not None and pending() > 0:
                return True
            readable, _w, _x = select.select([sock], [], [], 0)
            return bool(readable)
        except (OSError, ValueError):
            return True

    # ----------------------------------------------------------------- open
    def ssl_context(self):
        if self.ctx is None:
            self.ctx = ssl.create_default_context() if self.tls_verify else ssl._create_unverified_context()
        return self.ctx

    def socket_timeout(self):
        seconds = int(self.timeout_seconds)
        return float(seconds) if seconds else None

    def open(self, key: tuple):
        scheme, host, port, _verify, proxy = key
        if proxy:
            return self.open_via_proxy(scheme, host, port, proxy)
        if scheme == 'https':
            return http.client.HTTPSConnection(host, port, timeout=self.socket_timeout(), context=self.ssl_context())
        return http.client.HTTPConnection(host, port, timeout=self.socket_timeout())

    def proxy_parts(self, proxy: str):
        return urlsplit(proxy if '://' in proxy else f'http://{proxy}')

    def proxy_auth_header(self, proxy: str) -> dict:
        """{'Proxy-Authorization': ...} when the proxy URL carries user:pass, else {}."""
        p = self.proxy_parts(proxy)
        if not p.username:
            return {}
        cred = f'{unquote(p.username)}:{unquote(p.password or "")}'.encode()
        return {'Proxy-Authorization': 'Basic ' + base64.b64encode(cred).decode()}

    def open_via_proxy(self, scheme: str, host: str, port: int, proxy: str):
        """One connection to the proxy; for an https origin it carries a CONNECT
        tunnel (auth header on the CONNECT), for http the request itself goes to
        the proxy with an absolute URI and `proxy_headers()` adds the auth."""
        p          = self.proxy_parts(proxy)
        proxy_host = p.hostname or ''
        proxy_port = p.port or (443 if p.scheme == 'https' else 80)
        if scheme == 'https' or p.scheme == 'https':
            conn = http.client.HTTPSConnection(proxy_host, proxy_port, timeout=self.socket_timeout(),
                                               context=self.ssl_context())
        else:
            conn = http.client.HTTPConnection(proxy_host, proxy_port, timeout=self.socket_timeout())
        if scheme == 'https':
            conn.set_tunnel(host, port, headers=self.proxy_auth_header(proxy) or None)
        return conn

    def proxy_headers(self, key: tuple) -> dict:
        """Headers each request needs for plain http through a proxy (none otherwise)."""
        scheme, _host, _port, _verify, proxy = key
        if proxy and scheme == 'http':
            return self.proxy_auth_header(proxy)
        return {}

    def request_target(self, key: tuple, url: str) -> str:
        """What goes on the request line: the path for direct/tunnelled, the
        absolute URI for plain-http-through-proxy."""
        scheme, _host, _port, _verify, proxy = key
        parts = urlsplit(url)
        path  = parts.path or '/'
        if parts.query:
            path = f'{path}?{parts.query}'
        if proxy and scheme == 'http':
            return url
        return path
