"""P3 — sgit vault serve: read-only, path-guarded, loopback-locked."""
import http.client
import os
import shutil
import tempfile
import urllib.request

import pytest

from sgit_ai.core.serve.Vault__Static_Server import Vault__Static_Server
from sgit_ai.safe_types.Safe_UInt__Port      import Safe_UInt__Port


@pytest.fixture(scope='module')
def served():
    tmp     = tempfile.mkdtemp(prefix='vault_serve_')
    publish = os.path.join(tmp, 'publish')
    bare    = os.path.join(tmp, 'bare')
    os.makedirs(os.path.join(publish, 'api', 'docs'))
    os.makedirs(os.path.join(publish, 'nodocs'))
    os.makedirs(os.path.join(bare, 'refs'))
    with open(os.path.join(publish, 'index.html'), 'w') as f:
        f.write('<html>loader</html>')
    with open(os.path.join(publish, 'cover.json'), 'w') as f:
        f.write('{"title": "t"}')
    with open(os.path.join(publish, 'api', 'docs', 'index.html'), 'w') as f:
        f.write('<html>docs</html>')
    with open(os.path.join(bare, 'refs', 'ref-pid-muw-aabbccddeeff'), 'wb') as f:
        f.write(b'\x00\x01ciphertext-ref-bytes')
    with open(os.path.join(tmp, 'secret-outside.txt'), 'w') as f:
        f.write('must never be served')

    server = Vault__Static_Server(root_dir=publish, bare_dir=bare,
                                  vault_id='q7r6d5zd', port=Safe_UInt__Port(0), quiet=True)
    port = server.start()
    yield dict(tmp=tmp, publish=publish, bare=bare, port=port, url=server.url())
    server.stop()
    shutil.rmtree(tmp, ignore_errors=True)


def _get(served_ctx, path, method='GET', host_header=None):
    conn = http.client.HTTPConnection('127.0.0.1', served_ctx['port'], timeout=10)
    if host_header is None:
        conn.request(method, path)
    else:
        conn.putrequest(method, path, skip_host=True)
        conn.putheader('Host', host_header)
        conn.endheaders()
    response = conn.getresponse()
    body     = response.read()
    conn.close()
    return response.status, body


class Test_Vault__Static_Server:

    def test_root_serves_the_loader(self, served):
        status, body = _get(served, '/')
        assert status == 200
        assert body   == b'<html>loader</html>'

    def test_surface_files_served(self, served):
        status, body = _get(served, '/cover.json')
        assert status == 200
        assert body   == b'{"title": "t"}'

    def test_virtual_bare_route_is_byte_identical(self, served):
        """I1: the ciphertext a reader receives IS the store — routed, not copied."""
        status, body = _get(served, '/api/vault/read/q7r6d5zd/bare/refs/ref-pid-muw-aabbccddeeff')
        assert status == 200
        with open(os.path.join(served['bare'], 'refs', 'ref-pid-muw-aabbccddeeff'), 'rb') as f:
            assert body == f.read()

    def test_absent_object_is_404(self, served):
        status, _body = _get(served, '/api/vault/read/q7r6d5zd/bare/refs/ref-pid-muw-000000000000')
        assert status == 404

    def test_directory_request_serves_index_only(self, served):
        status, body = _get(served, '/api/docs/')
        assert status == 200
        assert body   == b'<html>docs</html>'

    def test_no_directory_listing(self, served):
        status, body = _get(served, '/nodocs/')
        assert status == 404
        assert b'secret' not in body and b'index' not in body

    def test_path_traversal_refused(self, served):
        for path in ['/../secret-outside.txt',
                     '/../../etc/passwd',
                     '/%2e%2e/secret-outside.txt',
                     '/%2e%2e/%2e%2e/etc/passwd',
                     '/..%2fsecret-outside.txt']:
            status, body = _get(served, path)
            assert status in (403, 404), path
            assert b'must never be served' not in body, path
            assert b'root:' not in body, path

    def test_bare_route_traversal_refused(self, served):
        """SP-8: the manifest/virtual-route file ids are attacker-influenced."""
        for path in ['/api/vault/read/q7r6d5zd/bare/../../secret-outside.txt',
                     '/api/vault/read/q7r6d5zd/bare/%2e%2e/%2e%2e/secret-outside.txt']:
            status, body = _get(served, path)
            assert status in (403, 404), path
            assert b'must never be served' not in body, path

    def test_writes_are_405(self, served):
        for method in ('POST', 'PUT', 'DELETE', 'PATCH'):
            status, _body = _get(served, '/cover.json', method=method)
            assert status == 405, method

    def test_host_header_check_refuses_dns_rebinding(self, served):
        """SP-9: a request whose Host is not loopback is refused."""
        status, body = _get(served, '/', host_header='evil.example.com')
        assert status == 403
        assert b'Host' in body

    def test_host_header_localhost_allowed(self, served):
        status, _body = _get(served, '/', host_header='localhost:1234')
        assert status == 200

    def test_port_zero_picked_a_free_port(self, served):
        assert served['port'] > 0

    def test_head_supported(self, served):
        status, body = _get(served, '/', method='HEAD')
        assert status == 200
        assert body   == b''

    def test_urllib_round_trip(self, served):
        with urllib.request.urlopen(served['url'] + 'index.html', timeout=10) as response:
            assert response.read() == b'<html>loader</html>'

    def test_start_requires_existing_root(self):
        server = Vault__Static_Server(root_dir='/nonexistent/dir', port=Safe_UInt__Port(0))
        with pytest.raises(ValueError):
            server.start()
