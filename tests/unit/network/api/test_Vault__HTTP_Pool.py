"""Vault__HTTP_Pool + the Vault__API request layer on top of it — against a real
local HTTP/1.1 keep-alive server (no mocks of the transport)."""
import threading
import pytest
from   http.server                              import BaseHTTPRequestHandler, ThreadingHTTPServer
from   urllib.error                             import URLError
from   sgit_ai.network.api.Vault__HTTP_Pool     import Vault__HTTP_Pool
from   sgit_ai.network.api.Vault__API           import Vault__API
import sgit_ai.network.api.Vault__API           as api_module


class _Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'                 # keep-alive by default

    def log_message(self, *args):                 # quiet
        pass

    def handle(self):
        self.server.connections += 1
        super().handle()

    def _serve(self):
        length = int(self.headers.get('Content-Length') or 0)
        body   = self.rfile.read(length) if length else b''
        self.server.requests.append((self.command, self.path, dict(self.headers), body))
        step   = self.server.script.pop(0) if self.server.script else ('ok', 200, b'{"status":"ok"}')
        kind   = step[0]
        status = step[1] if len(step) > 1 else 200
        data   = step[2] if len(step) > 2 else b'{"status":"ok"}'
        extra  = step[3] if len(step) > 3 else {}
        if kind == 'short':                       # claims 50 bytes, sends 10, hangs up
            self.send_response(200)
            self.send_header('Content-Length', '50')
            self.end_headers()
            self.wfile.write(b'x' * 10)
            self.wfile.flush()
            self.close_connection = True
            return
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(data)))
        for k, v in extra.items():
            self.send_header(k, v)
        if kind == 'close':
            self.send_header('Connection', 'close')
        self.end_headers()
        self.wfile.write(data)
        if kind in ('close', 'ok_then_drop'):     # drop: server hangs up WITHOUT saying so
            self.close_connection = True

    do_GET = do_POST = do_PUT = do_DELETE = _serve


class _Server:
    def __init__(self):
        self.httpd             = ThreadingHTTPServer(('127.0.0.1', 0), _Handler)
        self.httpd.connections = 0
        self.httpd.requests    = []
        self.httpd.script      = []
        self.thread            = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        self.url = f'http://127.0.0.1:{self.httpd.server_address[1]}'

    def stop(self):
        self.httpd.shutdown()
        self.httpd.server_close()

    @property
    def connections(self): return self.httpd.connections
    @property
    def requests(self):    return self.httpd.requests
    def script(self, *steps): self.httpd.script.extend(steps)


PROXY_VARS = ('HTTP_PROXY', 'http_proxy', 'HTTPS_PROXY', 'https_proxy', 'NO_PROXY', 'no_proxy')


def _clear_proxy_env(monkeypatch):
    for var in PROXY_VARS:                        # getproxies() reads both cases
        monkeypatch.delenv(var, raising=False)


@pytest.fixture
def server(monkeypatch):
    _clear_proxy_env(monkeypatch)
    monkeypatch.setenv('NO_PROXY', '127.0.0.1,localhost')
    monkeypatch.setattr(api_module, 'RETRY_DELAYS', [0, 0, 0])      # same attempts, no sleeping
    s = _Server()
    yield s
    s.stop()


@pytest.fixture
def api():
    a = Vault__API(access_token='tok-123').setup()
    yield a
    a.close()


# ---------------------------------------------------------------- the pool itself

class Test_Vault__HTTP_Pool__Keys:

    def test_key_has_scheme_host_port_verify_proxy(self, monkeypatch):
        _clear_proxy_env(monkeypatch)
        pool = Vault__HTTP_Pool().setup()
        assert pool.key_for('https://dev.send.sgraph.ai/api/x')     == ('https', 'dev.send.sgraph.ai', 443, True, '')
        assert pool.key_for('http://host:8080/p?q=1')               == ('http',  'host', 8080, True, '')

    def test_verify_flag_is_part_of_the_key(self):
        url = 'https://h/x'
        assert Vault__HTTP_Pool(tls_verify=False).setup().key_for(url) != Vault__HTTP_Pool().setup().key_for(url)

    def test_https_proxy_becomes_a_connect_tunnel_with_basic_auth(self, monkeypatch):
        _clear_proxy_env(monkeypatch)
        monkeypatch.setenv('HTTPS_PROXY', 'http://user:p%40ss@proxy.local:3128')
        monkeypatch.setenv('NO_PROXY', '')
        pool = Vault__HTTP_Pool().setup()
        key  = pool.key_for('https://api.example/api/v')
        assert key[4] == 'http://user:p%40ss@proxy.local:3128'
        conn = pool.open(key)                                  # no I/O until a request is sent
        assert (conn.host, conn.port)       == ('proxy.local', 3128)
        assert conn._tunnel_host            == 'api.example'
        assert conn._tunnel_port            == 443
        assert conn._tunnel_headers['Proxy-Authorization'] == 'Basic dXNlcjpwQHNz'   # user:p@ss
        assert pool.request_target(key, 'https://api.example/api/v?x=1') == '/api/v?x=1'

    def test_no_proxy_bypass(self, monkeypatch):
        _clear_proxy_env(monkeypatch)
        monkeypatch.setenv('HTTPS_PROXY', 'http://proxy.local:3128')
        monkeypatch.setenv('NO_PROXY', 'api.example')
        pool = Vault__HTTP_Pool().setup()
        assert pool.key_for('https://api.example/x')[4] == ''

    def test_plain_http_via_proxy_uses_absolute_uri(self, monkeypatch):
        _clear_proxy_env(monkeypatch)
        monkeypatch.setenv('HTTP_PROXY', 'http://proxy.local:3128')
        monkeypatch.setenv('NO_PROXY', '')
        pool = Vault__HTTP_Pool().setup()
        key  = pool.key_for('http://api.example/x')
        conn = pool.open(key)
        assert (conn.host, conn.port) == ('proxy.local', 3128)
        assert conn._tunnel_host is None
        assert pool.request_target(key, 'http://api.example/x?y') == 'http://api.example/x?y'

    def test_acquire_release_reuses_and_marks_warm(self, monkeypatch):
        _clear_proxy_env(monkeypatch)
        pool = Vault__HTTP_Pool().setup()
        key, c1, warm1 = pool.acquire('http://h/a')
        assert warm1 is False
        pool.release(key, c1)
        key2, c2, warm2 = pool.acquire('http://h/b')
        assert c2 is c1 and warm2 is True and key2 == key
        pool.discard(key, c2)
        _, c3, warm3 = pool.acquire('http://h/c')
        assert c3 is not c1 and warm3 is False
        pool.close()
        assert pool.idle == {}


# -------------------------------------------------- Vault__API on the pool, real sockets

class Test_Vault__API__Keep_Alive:

    def test_sequential_requests_share_one_connection(self, server, api):
        for _ in range(5):
            assert api._request('GET', f'{server.url}/api/x') == {'status': 'ok'}
        assert server.connections == 1
        assert len(server.requests) == 5

    def test_headers_still_sent_per_request(self, server, api):
        api._request('GET', f'{server.url}/api/x', api._auth_headers())
        api._request('POST', f'{server.url}/api/y', api._auth_headers({'Content-Type': 'application/json'}), b'{}')
        _, _, h1, _    = server.requests[0]
        _, _, h2, body = server.requests[1]
        assert h1['x-sgraph-access-token'] == 'tok-123' and h1['X-API-Key'] == 'tok-123'
        assert h2['Content-Type'] == 'application/json' and body == b'{}'
        assert 'Connection' not in h1                     # urlopen used to force Connection: close
        assert h1['User-Agent'] == 'sgit-ai'

    def test_server_connection_close_is_honoured(self, server, api):
        server.script(('close', 200))
        api._request('GET', f'{server.url}/a')
        api._request('GET', f'{server.url}/b')
        assert server.connections == 2
        assert sum(len(b) for b in api.http_pool.idle.values()) == 1

    def test_stale_keep_alive_is_retried_for_idempotent_reads(self, server, api):
        server.script(('ok_then_drop', 200))
        api._request('GET', f'{server.url}/a')
        assert api._request('GET', f'{server.url}/b') == {'status': 'ok'}      # transparent reconnect
        assert server.connections == 2
        assert [r[1] for r in server.requests] == ['/a', '/b']

    def test_batch_read_is_treated_as_idempotent(self, server, api):
        server.script(('ok_then_drop', 200), ('ok', 200, b'{"results":[{"file_id":"f","status":"ok","data":"aGk="}]}'))
        api._request('GET', f'{server.url}/warm')
        api.base_url = server.url
        assert api.batch_read('v1', ['f']) == {'f': b'hi'}
        assert server.connections == 2

    def test_stale_keep_alive_never_resends_a_write(self, server, api):
        server.script(('ok_then_drop', 200))
        api._request('PUT', f'{server.url}/w1', None, b'one')
        with pytest.raises(URLError):
            api._request('PUT', f'{server.url}/w2', None, b'two')
        assert [r[1] for r in server.requests] == ['/w1']                       # /w2 never applied twice
        api._request('PUT', f'{server.url}/w3', None, b'three')                 # pool recovered
        assert server.connections == 2

    def test_fresh_connection_failure_is_not_retried(self, server, api):
        server.script(('short', 200))
        with pytest.raises(URLError):
            api._request('GET', f'{server.url}/a')
        assert len(server.requests) == 1
        assert api._request('GET', f'{server.url}/b') == {'status': 'ok'}      # poisoned conn discarded
        assert server.connections == 2

    def test_http_error_shape_and_body_preserved(self, server, api):
        server.script(('ok', 404, b'{"error":"vault not found"}'))
        with pytest.raises(RuntimeError) as exc:
            api._request('GET', f'{server.url}/missing', api._auth_headers())
        msg = str(exc.value)
        assert 'API Error: HTTP 404' in msg and 'vault not found' in msg
        assert 'tok-123' not in msg                                             # token masked
        assert server.connections == 1
        assert api._request('GET', f'{server.url}/ok') == {'status': 'ok'}      # conn still usable after a 4xx

    def test_transient_502_retries_then_succeeds_on_same_connection(self, server, api):
        server.script(('ok', 502, b'bad gateway'), ('ok', 503, b''), ('ok', 200))
        assert api._request('GET', f'{server.url}/x') == {'status': 'ok'}
        assert len(server.requests) == 3
        assert server.connections == 1

    def test_transient_exhausted_raises_last_error(self, server, api):
        server.script(*[('ok', 502, b'down')] * 4)
        with pytest.raises(RuntimeError, match='HTTP 502'):
            api._request('GET', f'{server.url}/x')
        assert len(server.requests) == 4

    def test_redirects_are_not_followed(self, server, api):
        server.script(('ok', 302, b'', {'Location': 'http://attacker.example/steal'}))
        with pytest.raises(RuntimeError, match='HTTP 302'):
            api._request('GET', f'{server.url}/r', api._auth_headers())
        assert len(server.requests) == 1

    def test_request_bytes_returns_raw_body(self, server, api):
        server.script(('ok', 200, b'\x00\x01raw'))
        assert api._request_bytes('GET', f'{server.url}/raw') == b'\x00\x01raw'

    def test_parallel_callers_share_a_bounded_pool(self, server, api):
        errors = []
        def worker():
            try:
                for _ in range(5):
                    api._request('GET', f'{server.url}/p')
            except Exception as e:
                errors.append(e)
        threads = [threading.Thread(target=worker) for _ in range(8)]
        for t in threads: t.start()
        for t in threads: t.join()
        assert errors == []
        assert len(server.requests) == 40
        assert server.connections <= 8
        assert sum(len(b) for b in api.http_pool.idle.values()) <= 8

    def test_close_drops_pooled_connections(self, server, api):
        api._request('GET', f'{server.url}/a')
        api.close()
        assert api.http_pool.idle == {}
        api._request('GET', f'{server.url}/b')
        assert server.connections == 2

    def test_env_switch_disables_keep_alive(self, server, api, monkeypatch):
        monkeypatch.setenv('SGIT_HTTP_NO_KEEPALIVE', '1')
        for _ in range(3):
            api._request('GET', f'{server.url}/x')
        assert server.connections == 3
        assert api.http_pool.idle == {}
