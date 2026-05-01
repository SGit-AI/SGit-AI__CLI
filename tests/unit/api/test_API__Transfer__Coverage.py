# Additional coverage tests for API__Transfer.
import json
from io import BytesIO
from urllib.error import HTTPError

import pytest

from sgit_ai.api.API__Transfer import (
    API__Transfer,
    DEFAULT_BASE_URL,
    LAMBDA_RESPONSE_LIMIT,
    TRANSIENT_STATUS_CODES,
    RETRY_DELAYS,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_api(base_url: str = 'https://send.sgraph.ai',
              access_token: str = 'test-token') -> API__Transfer:
    api = API__Transfer(base_url=base_url, access_token=access_token)
    api.setup()
    return api


def _http_error(code: int, reason: str = 'Error',
                body: bytes = b'',
                headers: dict = None) -> HTTPError:
    from http.client import HTTPMessage
    msg = HTTPMessage()
    if headers:
        for k, v in headers.items():
            msg[k] = v
    return HTTPError('http://test', code, reason, msg, BytesIO(body))


# ---------------------------------------------------------------------------
# setup()
# ---------------------------------------------------------------------------

class Test_API__Transfer__Setup:

    def test_setup_sets_default_url(self):
        api = API__Transfer()
        api.setup()
        assert str(api.base_url) == DEFAULT_BASE_URL

    def test_setup_returns_self(self):
        api = API__Transfer()
        assert api.setup() is api

    def test_setup_does_not_override_custom_url(self):
        api = API__Transfer(base_url='https://custom.example.com')
        api.setup()
        assert str(api.base_url) == 'https://custom.example.com'

    def test_default_access_token_is_none(self):
        api = API__Transfer()
        assert api.access_token is None


# ---------------------------------------------------------------------------
# _auth_headers()
# ---------------------------------------------------------------------------

class Test_API__Transfer__Auth_Headers:

    def setup_method(self):
        self.api = _make_api(access_token='my-secret-token')

    def test_auth_headers_contains_token(self):
        h = self.api._auth_headers()
        assert h['x-sgraph-access-token'] == 'my-secret-token'

    def test_auth_headers_merges_extra(self):
        h = self.api._auth_headers({'Content-Type': 'application/json'})
        assert h['x-sgraph-access-token'] == 'my-secret-token'
        assert h['Content-Type'] == 'application/json'

    def test_auth_headers_no_token_returns_empty(self):
        api = API__Transfer()
        api.setup()
        assert api._auth_headers() == {}

    def test_auth_headers_no_token_with_extra(self):
        api = API__Transfer()
        api.setup()
        h   = api._auth_headers({'X-Custom': 'value'})
        assert h == {'X-Custom': 'value'}

    def test_auth_headers_does_not_mutate_extra(self):
        extra    = {'Content-Type': 'application/octet-stream'}
        original = dict(extra)
        self.api._auth_headers(extra)
        assert extra == original


# ---------------------------------------------------------------------------
# _api_error() formatting
# ---------------------------------------------------------------------------

class Test_API__Transfer__Api_Error:

    def setup_method(self):
        self.api = _make_api()

    def test_returns_runtime_error(self):
        err = _http_error(500, 'Internal Server Error')
        exc = self.api._api_error('GET', 'http://test', {}, err)
        assert isinstance(exc, RuntimeError)

    def test_contains_http_status(self):
        err = _http_error(404, 'Not Found')
        exc = self.api._api_error('GET', 'http://test', {}, err)
        assert 'HTTP 404' in str(exc)

    def test_contains_method_and_url(self):
        err = _http_error(400, 'Bad Request')
        exc = self.api._api_error('DELETE', 'http://example.com/path', {}, err)
        assert 'DELETE' in str(exc)
        assert 'http://example.com/path' in str(exc)

    def test_masks_access_token_header(self):
        err     = _http_error(401, 'Unauthorized')
        headers = {'x-sgraph-access-token': 'supersecret12345678'}
        exc     = self.api._api_error('GET', 'http://test', headers, err)
        msg = str(exc)
        assert 'supersecret12345678' not in msg
        # masked format is first 8 chars + '...(N chars)'
        assert 'supersec...(19 chars)' in msg

    def test_masks_write_key_header(self):
        err     = _http_error(403, 'Forbidden')
        headers = {'x-sgraph-vault-write-key': 'deadbeef' * 8}
        exc     = self.api._api_error('PUT', 'http://test', headers, err)
        assert 'deadbeef' * 8 not in str(exc)

    def test_non_sensitive_header_not_masked(self):
        err     = _http_error(400, 'Bad Request')
        headers = {'Content-Type': 'application/json'}
        exc     = self.api._api_error('POST', 'http://test', headers, err)
        assert 'application/json' in str(exc)

    def test_includes_response_body(self):
        err = _http_error(422, 'Unprocessable', b'{"error": "invalid field"}')
        exc = self.api._api_error('POST', 'http://test', {}, err)
        assert 'invalid field' in str(exc)

    def test_includes_payload_size_when_nonzero(self):
        err = _http_error(413, 'Payload Too Large')
        exc = self.api._api_error('POST', 'http://test', {}, err, data_size=4096)
        assert '4096' in str(exc)

    def test_payload_size_zero_omits_field(self):
        err = _http_error(400, 'Bad Request')
        exc = self.api._api_error('GET', 'http://test', {}, err, data_size=0)
        assert 'Payload' not in str(exc)

    def test_none_headers_handled(self):
        err = _http_error(500, 'Server Error')
        exc = self.api._api_error('GET', 'http://test', None, err)
        assert isinstance(exc, RuntimeError)


# ---------------------------------------------------------------------------
# _upload_large() — cancels on various failure points
# ---------------------------------------------------------------------------

class Test_API__Transfer__Upload_Large__Extended:

    PART_SIZE = 5 * 1024 * 1024
    PAYLOAD   = b'Y' * (6 * 1024 * 1024)   # 6 MB

    def setup_method(self):
        self.api = _make_api()
        self._caps_calls     = 0
        self._initiate_calls = []
        self._upload_calls   = []
        self._complete_calls = []
        self._cancel_calls   = []

        self.api.presigned_capabilities = self._stub_caps
        self.api.presigned_initiate     = self._stub_initiate
        self.api.upload_part            = self._stub_upload_part
        self.api.presigned_complete     = self._stub_complete
        self.api.presigned_cancel       = self._stub_cancel

    def _stub_caps(self):
        self._caps_calls += 1
        return {
            'presigned_upload' : True,
            'max_part_size'    : 10 * 1024 * 1024,
            'min_part_size'    : self.PART_SIZE,
            'max_parts'        : 10000,
        }

    def _stub_initiate(self, transfer_id, file_size_bytes, num_parts):
        self._initiate_calls.append(dict(transfer_id=transfer_id))
        part_urls = [
            dict(part_number=i + 1, upload_url=f'https://s3.test/part{i+1}')
            for i in range(num_parts)
        ]
        return dict(upload_id='uid-test', part_urls=part_urls)

    def _stub_upload_part(self, url, data):
        self._upload_calls.append(len(data))
        return f'etag-{len(self._upload_calls)}'

    def _stub_complete(self, transfer_id, upload_id, parts):
        self._complete_calls.append(dict(tid=transfer_id, uid=upload_id))
        return {}

    def _stub_cancel(self, transfer_id, upload_id):
        self._cancel_calls.append(dict(tid=transfer_id, uid=upload_id))
        return {}

    def test_caps_checked_first(self):
        self.api._upload_large('t1', self.PAYLOAD)
        assert self._caps_calls == 1

    def test_complete_called_after_all_parts(self):
        self.api._upload_large('t1', self.PAYLOAD)
        assert len(self._complete_calls) == 1

    def test_cancel_on_complete_failure(self):
        def _fail_complete(*args, **kwargs):
            raise RuntimeError('complete failed')
        self.api.presigned_complete = _fail_complete

        with pytest.raises(RuntimeError, match='complete failed'):
            self.api._upload_large('t1', self.PAYLOAD)

        assert len(self._cancel_calls) == 1

    def test_transfer_id_passed_to_initiate(self):
        self.api._upload_large('xfer-abc', self.PAYLOAD)
        assert self._initiate_calls[0]['transfer_id'] == 'xfer-abc'

    def test_no_presigned_upload_error_message_includes_size(self):
        self.api.presigned_capabilities = lambda: {'presigned_upload': False}
        with pytest.raises(RuntimeError) as exc_info:
            self.api._upload_large('t1', self.PAYLOAD)
        assert '6.0 MB' in str(exc_info.value)


# ---------------------------------------------------------------------------
# Constants sanity
# ---------------------------------------------------------------------------

class Test_API__Transfer__Constants:

    def test_lambda_response_limit_is_5mb(self):
        assert LAMBDA_RESPONSE_LIMIT == 5 * 1024 * 1024

    def test_transient_codes(self):
        assert 502 in TRANSIENT_STATUS_CODES
        assert 503 in TRANSIENT_STATUS_CODES
        assert 504 in TRANSIENT_STATUS_CODES

    def test_retry_delays_are_increasing(self):
        assert RETRY_DELAYS == sorted(RETRY_DELAYS)
        assert len(RETRY_DELAYS) >= 2
