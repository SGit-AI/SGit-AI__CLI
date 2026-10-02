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
  * Any exception between request and the fully-read body discards the
    connection — a half-read response must never serve the next caller.
  * The server closing its side (`Connection: close`, or `will_close`) also
    discards it.
  * Reconnect-and-resend is the CALLER's decision (Vault__API knows which
    requests are idempotent); this class only reports whether the connection
    it handed out had already served a request (`warm`), which is the only
    case where "remote end closed without response" is a stale keep-alive
    rather than a real failure.
  * Proxies: honours HTTP(S)_PROXY / NO_PROXY exactly as urllib does, via a
    CONNECT tunnel for https and an absolute-URI request for http.
"""
import base64
import http.client
import ssl
import threading
from   urllib.parse                      import urlsplit, unquote
from   urllib.request                    import getproxies, proxy_bypass
from   osbot_utils.type_safe.Type_Safe   import Type_Safe


class Vault__HTTP_Pool(Type_Safe):
    tls_verify : bool   = True
    timeout    : object = None      # seconds, or None for no timeout (urlopen's default)
    idle       : object = None      # {key: [conn, ...]} — connections not currently checked out
    warm       : object = None      # set of id(conn) that have served at least one request
    lock       : object = None
    ctx        : object = None      # the ssl context, built once

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
    def acquire(self, url: str):
        """(key, conn, warm). `warm` is True when conn has served a request before."""
        key = self.key_for(url)
        with self.lock:
            bucket = self.idle.get(key) or []
            if bucket:
                conn = bucket.pop()
                return key, conn, id(conn) in self.warm
        return key, self.open(key), False

    def release(self, key: tuple, conn) -> None:
        with self.lock:
            self.warm.add(id(conn))
            self.idle.setdefault(key, []).append(conn)

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
            for conn in bucket:
                try:
                    conn.close()
                except Exception:
                    pass

    # ----------------------------------------------------------------- open
    def ssl_context(self):
        if self.ctx is None:
            self.ctx = ssl.create_default_context() if self.tls_verify else ssl._create_unverified_context()
        return self.ctx

    def open(self, key: tuple):
        scheme, host, port, _verify, proxy = key
        if proxy:
            return self.open_via_proxy(scheme, host, port, proxy)
        if scheme == 'https':
            return http.client.HTTPSConnection(host, port, timeout=self.timeout, context=self.ssl_context())
        return http.client.HTTPConnection(host, port, timeout=self.timeout)

    def open_via_proxy(self, scheme: str, host: str, port: int, proxy: str):
        p          = urlsplit(proxy if '://' in proxy else f'http://{proxy}')
        proxy_host = p.hostname or ''
        proxy_port = p.port or (443 if p.scheme == 'https' else 80)
        headers    = {}
        if p.username:
            cred = f'{unquote(p.username)}:{unquote(p.password or "")}'.encode()
            headers['Proxy-Authorization'] = 'Basic ' + base64.b64encode(cred).decode()
        if p.scheme == 'https':
            conn = http.client.HTTPSConnection(proxy_host, proxy_port, timeout=self.timeout,
                                               context=self.ssl_context())
        else:
            conn = http.client.HTTPConnection(proxy_host, proxy_port, timeout=self.timeout)
        if scheme == 'https':                      # CONNECT tunnel; TLS to the origin runs inside it
            conn = http.client.HTTPSConnection(proxy_host, proxy_port, timeout=self.timeout,
                                               context=self.ssl_context())
            conn.set_tunnel(host, port, headers=headers or None)
        return conn

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
