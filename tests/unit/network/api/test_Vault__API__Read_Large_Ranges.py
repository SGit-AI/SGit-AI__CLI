"""read_large over a presigned URL reads the file in parallel byte ranges (loopback
HTTP server with Range support; a server that ignores Range still works)."""
import http.server
import threading

import pytest

from sgit_ai.network.api.Vault__API import Vault__API, PRESIGNED_PART


class _Range_Handler(http.server.BaseHTTPRequestHandler):
    body         = b''
    honour_range = True
    requests     = []

    def log_message(self, *args):
        pass

    def do_GET(self):
        header = self.headers.get('Range')
        type(self).requests.append(header)
        if header and self.honour_range:
            start, end = header.replace('bytes=', '').split('-')
            start, end = int(start), min(int(end), len(self.body) - 1)
            chunk = self.body[start:end + 1]
            self.send_response(206)
            self.send_header('Content-Range', f'bytes {start}-{end}/{len(self.body)}')
        else:
            chunk = self.body
            self.send_response(200)
        self.send_header('Content-Length', str(len(chunk)))
        self.end_headers()
        self.wfile.write(chunk)


class _API(Vault__API):
    url = ''
    def presigned_read_url(self, vault_id, file_id):
        return {'url': self.url}


@pytest.fixture
def server():
    httpd  = http.server.ThreadingHTTPServer(('127.0.0.1', 0), _Range_Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True); thread.start()
    _Range_Handler.requests = []
    _Range_Handler.honour_range = True
    yield httpd
    httpd.shutdown()


def _api(httpd):
    api = _API(base_url='http://127.0.0.1:9'); api.setup()
    api.url = f'http://127.0.0.1:{httpd.server_port}/blob'
    return api


class Test_Read_Large__Ranges:

    def test_a_file_over_one_part_is_read_in_parallel_ranges_and_reassembled(self, server, monkeypatch):
        import sgit_ai.network.api.Vault__API as mod
        monkeypatch.setattr(mod, 'PRESIGNED_PART', 1000)
        _Range_Handler.body = bytes(range(256)) * 20                              # 5120 bytes: 6 parts
        data = _api(server).read_large('v', 'bare/packs/snapshots/x.zip')
        assert data == _Range_Handler.body
        assert len(_Range_Handler.requests) == 6 and _Range_Handler.requests[0] == 'bytes=0-999'

    def test_the_declared_size_is_used_and_a_small_file_is_one_request(self, server, monkeypatch):
        import sgit_ai.network.api.Vault__API as mod
        monkeypatch.setattr(mod, 'PRESIGNED_PART', 1000)
        _Range_Handler.body = b'x' * 500
        assert _api(server).read_large('v', 'f', size=500) == _Range_Handler.body
        assert _Range_Handler.requests == [None]                                   # plain GET, no Range
        _Range_Handler.requests = []
        _Range_Handler.body = b'y' * 2500
        assert _api(server).read_large('v', 'f', size=2500) == _Range_Handler.body
        assert _Range_Handler.requests[0] == 'bytes=0-999' and len(_Range_Handler.requests) == 3

    def test_a_host_that_ignores_range_still_delivers_the_file(self, server, monkeypatch):
        import sgit_ai.network.api.Vault__API as mod
        monkeypatch.setattr(mod, 'PRESIGNED_PART', 1000)
        _Range_Handler.honour_range = False
        _Range_Handler.body = b'z' * 4000
        assert _api(server).read_large('v', 'f') == _Range_Handler.body
        assert len(_Range_Handler.requests) == 1
