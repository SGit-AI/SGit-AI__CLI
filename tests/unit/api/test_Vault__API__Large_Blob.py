import io
import zipfile

from sgit_ai.api.Vault__API import Vault__API, LARGE_BLOB_THRESHOLD


class Test_Vault__API__Large_Blob:
    """Unit tests for the write_large() zip packaging in Vault__API."""

    def setup_method(self):
        self.api = Vault__API(base_url='https://example.com', access_token='test-token')

    def test_large_blob_threshold_is_4mb(self):
        assert LARGE_BLOB_THRESHOLD == 4 * 1024 * 1024

    def test_write_large_packages_as_zip(self):
        """write_large() wraps the payload in a ZIP before POSTing."""
        captured = {}

        def fake_request(method, url, headers, data):
            captured['method']  = method
            captured['url']     = url
            captured['headers'] = headers
            captured['data']    = data
            return {'status': 'ok'}

        self.api._request = fake_request
        payload = b'X' * 100
        self.api.write_large('vault1', 'bare/data/obj-abc', 'wk', payload)

        assert captured['method'] == 'POST'
        assert 'vault/zip/vault1' in captured['url']
        assert captured['headers']['Content-Type'] == 'application/zip'

        # The body must be a valid ZIP containing the file at the correct path
        buf = io.BytesIO(captured['data'])
        with zipfile.ZipFile(buf, 'r') as zf:
            assert 'bare/data/obj-abc' in zf.namelist()
            assert zf.read('bare/data/obj-abc') == payload

    def test_write_large_uses_no_compression(self):
        """Encrypted blobs are random — ZIP_STORED avoids wasted CPU."""
        captured = {}
        self.api._request = lambda m, u, h, d: captured.update({'data': d}) or {}
        self.api.write_large('v1', 'bare/data/blob', 'wk', b'content')

        buf = io.BytesIO(captured['data'])
        with zipfile.ZipFile(buf, 'r') as zf:
            info = zf.getinfo('bare/data/blob')
            assert info.compress_type == zipfile.ZIP_STORED

    def test_write_large_sends_auth_headers(self):
        captured = {}
        self.api._request = lambda m, u, h, d: captured.update({'headers': h}) or {}
        self.api.write_large('v1', 'bare/data/x', 'my-write-key', b'data')

        assert captured['headers']['x-sgraph-access-token'] == 'test-token'
        assert captured['headers']['x-sgraph-vault-write-key'] == 'my-write-key'
