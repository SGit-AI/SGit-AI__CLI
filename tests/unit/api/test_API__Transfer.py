from sg_send_cli.api.API__Transfer import API__Transfer


class Test_API__Transfer:

    def setup_method(self):
        self.api = API__Transfer(base_url='https://send.sgraph.ai', access_token='test-token-123')
        self.api.setup()

    def test_setup_default_base_url(self):
        api = API__Transfer()
        api.setup()
        assert str(api.base_url) == 'https://send.sgraph.ai'

    def test_setup_custom_base_url(self):
        api = API__Transfer(base_url='https://custom.example.com')
        api.setup()
        assert str(api.base_url) == 'https://custom.example.com'

    def test_auth_headers_with_token(self):
        headers = self.api._auth_headers()
        assert headers['x-sgraph-access-token'] == 'test-token-123'

    def test_auth_headers_with_extra(self):
        headers = self.api._auth_headers({'Content-Type': 'application/json'})
        assert headers['x-sgraph-access-token'] == 'test-token-123'
        assert headers['Content-Type'] == 'application/json'

    def test_auth_headers_no_token(self):
        api = API__Transfer()
        api.setup()
        headers = api._auth_headers()
        assert headers == {}

    def test_api_error_masks_sensitive_headers(self):
        from urllib.error import HTTPError
        from io import BytesIO
        error = HTTPError('http://test', 400, 'Bad Request', {}, BytesIO(b'error body'))
        headers = {'x-sgraph-access-token': 'secret-token-value-12345'}
        exc = self.api._api_error('POST', 'http://test', headers, error)
        assert 'secret-token-value-12345' not in str(exc)
        assert 'secret-t...' in str(exc)
