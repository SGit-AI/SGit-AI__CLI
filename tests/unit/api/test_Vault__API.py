"""Tests for Vault__API.

Focuses on:
  - setup() and default values
  - URL construction helpers (no real HTTP is sent)
  - _api_error() error formatting
  - list_files() response normalisation
  - batch_read() chunk splitting and fallback logic (exercised via In_Memory)
"""
import base64
import json
from io import BytesIO
from urllib.error import HTTPError

import pytest

from sgit_ai.api.Vault__API             import Vault__API, DEFAULT_BASE_URL, MAX_BATCH_OPS, TRANSIENT_STATUS_CODES, RETRY_DELAYS
from sgit_ai.api.Vault__API__In_Memory  import Vault__API__In_Memory


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_api(base_url: str = 'https://example.com',
              access_token: str = 'tok-test') -> Vault__API:
    api = Vault__API(base_url=base_url, access_token=access_token)
    api.setup()
    return api


def _http_error(code: int, reason: str = 'Error',
                body: bytes = b'') -> HTTPError:
    return HTTPError('http://test', code, reason, {}, BytesIO(body))


class _UnreadableError(HTTPError):
    """HTTPError whose .read() always raises IOError."""
    def __init__(self):
        super().__init__('http://test', 500, 'Server Error', {}, None)

    def read(self):
        raise IOError('stream closed')


# ---------------------------------------------------------------------------
# setup()
# ---------------------------------------------------------------------------

class Test_Vault__API__Setup:

    def test_setup_returns_self(self):
        api = Vault__API()
        assert api.setup() is api

    def test_setup_sets_default_base_url(self):
        api = Vault__API()
        api.setup()
        assert str(api.base_url) == DEFAULT_BASE_URL

    def test_setup_does_not_override_existing_base_url(self):
        api = Vault__API(base_url='https://custom.example.com')
        api.setup()
        assert str(api.base_url) == 'https://custom.example.com'

    def test_default_access_token_is_none(self):
        api = Vault__API()
        assert api.access_token is None

    def test_custom_access_token_preserved(self):
        api = Vault__API(access_token='my-token')
        api.setup()
        assert str(api.access_token) == 'my-token'


# ---------------------------------------------------------------------------
# _api_error() — error message formatting
# ---------------------------------------------------------------------------

class Test_Vault__API__Error_Formatting:

    def setup_method(self):
        self.api = _make_api()

    def test_api_error_includes_status_code(self):
        err = _http_error(404, 'Not Found')
        exc = self.api._api_error('GET', 'http://test/foo', {}, err)
        assert 'HTTP 404' in str(exc)

    def test_api_error_includes_method_and_url(self):
        err = _http_error(500, 'Server Error')
        exc = self.api._api_error('POST', 'http://test/bar', {}, err)
        assert 'POST' in str(exc)
        assert 'http://test/bar' in str(exc)

    def test_api_error_masks_access_token(self):
        err     = _http_error(403, 'Forbidden')
        headers = {'x-sgraph-access-token': 'secret-token-xyz-12345'}
        exc     = self.api._api_error('GET', 'http://test', headers, err)
        msg     = str(exc)
        assert 'secret-token-xyz-12345' not in msg
        assert '***...' in msg

    def test_api_error_masks_write_key(self):
        err     = _http_error(403, 'Forbidden')
        headers = {'x-sgraph-vault-write-key': 'abcdef1234567890' * 4}
        exc     = self.api._api_error('PUT', 'http://test', headers, err)
        assert 'abcdef1234567890' * 4 not in str(exc)
        assert '***...' in str(exc)

    def test_api_error_includes_response_body(self):
        err = _http_error(422, 'Unprocessable', b'{"detail": "bad input"}')
        exc = self.api._api_error('POST', 'http://test', {}, err)
        assert 'bad input' in str(exc)

    def test_api_error_includes_payload_size(self):
        err = _http_error(400, 'Bad Request')
        exc = self.api._api_error('PUT', 'http://test', {}, err, data_size=1024)
        assert '1024' in str(exc)

    def test_api_error_no_payload_size_omits_field(self):
        err = _http_error(400, 'Bad Request')
        exc = self.api._api_error('GET', 'http://test', {}, err, data_size=0)
        assert 'Payload' not in str(exc)

    def test_api_error_returns_runtime_error(self):
        err = _http_error(503, 'Service Unavailable')
        exc = self.api._api_error('GET', 'http://test', {}, err)
        assert isinstance(exc, RuntimeError)

    def test_api_error_non_sensitive_header_not_masked(self):
        err     = _http_error(400, 'Bad Request')
        headers = {'Content-Type': 'application/json'}
        exc     = self.api._api_error('POST', 'http://test', headers, err)
        assert 'application/json' in str(exc)

    def test_api_error_none_headers_ok(self):
        err = _http_error(400, 'Bad Request')
        exc = self.api._api_error('GET', 'http://test', None, err)
        assert isinstance(exc, RuntimeError)

    def test_api_error_unreadable_body_does_not_raise(self):
        """Lines 269-270: when error.read() raises, the body is silently ignored."""
        err = _UnreadableError()
        exc = self.api._api_error('GET', 'http://test', {}, err)
        assert isinstance(exc, RuntimeError)
        # body should be absent since it couldn't be read
        assert 'stream closed' not in str(exc)




# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

class Test_Vault__API__Constants:

    def test_max_batch_ops_is_positive(self):
        assert MAX_BATCH_OPS > 0

    def test_transient_codes_include_502_503_504(self):
        assert 502 in TRANSIENT_STATUS_CODES
        assert 503 in TRANSIENT_STATUS_CODES
        assert 504 in TRANSIENT_STATUS_CODES

    def test_retry_delays_are_sorted(self):
        assert RETRY_DELAYS == sorted(RETRY_DELAYS)


# ---------------------------------------------------------------------------
# list_files() normalisation — uses In_Memory backend
# ---------------------------------------------------------------------------

class Test_Vault__API__List_Files:

    def setup_method(self):
        self.api = Vault__API__In_Memory()
        self.api.setup()

    def test_list_files_empty(self):
        files = self.api.list_files('vault1')
        assert files == []

    def test_list_files_returns_file_ids(self):
        self.api.write('vault1', 'data/obj1', 'wk', b'content')
        self.api.write('vault1', 'data/obj2', 'wk', b'content2')
        files = self.api.list_files('vault1')
        assert 'data/obj1' in files
        assert 'data/obj2' in files

    def test_list_files_prefix_filter(self):
        self.api.write('vault1', 'data/obj1', 'wk', b'a')
        self.api.write('vault1', 'refs/ref1', 'wk', b'b')
        files = self.api.list_files('vault1', prefix='data/')
        assert all(f.startswith('data/') for f in files)
        assert 'refs/ref1' not in files

    def test_list_files_different_vaults_isolated(self):
        self.api.write('vaultA', 'f1', 'wk', b'a')
        self.api.write('vaultB', 'f2', 'wk', b'b')
        assert self.api.list_files('vaultA') == ['f1']
        assert self.api.list_files('vaultB') == ['f2']


# ---------------------------------------------------------------------------
# batch_read() via In_Memory (covers the chunked iteration path)
# ---------------------------------------------------------------------------

class Test_Vault__API__Batch_Read:

    def setup_method(self):
        self.api = Vault__API__In_Memory()
        self.api.setup()

    def test_batch_read_empty_list(self):
        result = self.api.batch_read('v1', [])
        assert result == {}

    def test_batch_read_single_file(self):
        self.api.write('v1', 'f1', 'wk', b'hello')
        result = self.api.batch_read('v1', ['f1'])
        assert result['f1'] == b'hello'

    def test_batch_read_missing_file_returns_none(self):
        result = self.api.batch_read('v1', ['missing'])
        assert result['missing'] is None

    def test_batch_read_multiple_files(self):
        self.api.write('v1', 'a', 'wk', b'aaa')
        self.api.write('v1', 'b', 'wk', b'bbb')
        result = self.api.batch_read('v1', ['a', 'b'])
        assert result['a'] == b'aaa'
        assert result['b'] == b'bbb'

    def test_batch_read_mixed_present_and_missing(self):
        self.api.write('v1', 'present', 'wk', b'data')
        result = self.api.batch_read('v1', ['present', 'absent'])
        assert result['present'] == b'data'
        assert result['absent'] is None


# ---------------------------------------------------------------------------
# delete_vault() via In_Memory
# ---------------------------------------------------------------------------

class Test_Vault__API__Delete_Vault:

    def setup_method(self):
        self.api = Vault__API__In_Memory()
        self.api.setup()

    def test_delete_vault_removes_all_files(self):
        self.api.write('v1', 'f1', 'wk', b'data')
        self.api.write('v1', 'f2', 'wk', b'more')
        result = self.api.delete_vault('v1', 'wk')
        assert result['status'] == 'deleted'
        assert result['files_deleted'] == 2
        assert self.api.list_files('v1') == []

    def test_delete_vault_empty_vault_ok(self):
        result = self.api.delete_vault('empty-vault', 'wk')
        assert result['status'] == 'deleted'
        assert result['files_deleted'] == 0

    def test_delete_vault_only_deletes_own_vault(self):
        self.api.write('v1', 'f1', 'wk', b'a')
        self.api.write('v2', 'f2', 'wk', b'b')
        self.api.delete_vault('v1', 'wk')
        assert self.api.list_files('v2') == ['f2']


# ---------------------------------------------------------------------------
# write / read / delete via In_Memory (covers Vault__API surface used by Backend)
# ---------------------------------------------------------------------------

class Test_Vault__API__CRUD:

    def setup_method(self):
        self.api = Vault__API__In_Memory()
        self.api.setup()

    def test_write_returns_ok(self):
        result = self.api.write('v1', 'file', 'wk', b'payload')
        assert result == {'status': 'ok'}

    def test_read_after_write(self):
        self.api.write('v1', 'file', 'wk', b'payload')
        data = self.api.read('v1', 'file')
        assert data == b'payload'

    def test_read_missing_raises(self):
        with pytest.raises(RuntimeError, match='Not found'):
            self.api.read('v1', 'no-such-file')

    def test_delete_returns_ok(self):
        self.api.write('v1', 'f', 'wk', b'd')
        result = self.api.delete('v1', 'f', 'wk')
        assert result == {'status': 'ok'}

    def test_delete_removes_file(self):
        self.api.write('v1', 'f', 'wk', b'd')
        self.api.delete('v1', 'f', 'wk')
        with pytest.raises(RuntimeError):
            self.api.read('v1', 'f')


# ---------------------------------------------------------------------------
# batch() CAS (write-if-match) via In_Memory
# ---------------------------------------------------------------------------

class Test_Vault__API__Batch_CAS:

    def setup_method(self):
        self.api = Vault__API__In_Memory()
        self.api.setup()

    def _b64(self, data: bytes) -> str:
        import base64
        return base64.b64encode(data).decode()

    def test_write_if_match_succeeds_when_content_matches(self):
        self.api.write('v', 'f', 'wk', b'v1')
        ops    = [{'op': 'write-if-match', 'file_id': 'f',
                   'match': self._b64(b'v1'),
                   'data': self._b64(b'v2')}]
        result = self.api.batch('v', 'wk', ops)
        assert result['status'] == 'ok'
        assert self.api.read('v', 'f') == b'v2'

    def test_write_if_match_conflict_when_content_differs(self):
        self.api.write('v', 'f', 'wk', b'v1')
        ops    = [{'op': 'write-if-match', 'file_id': 'f',
                   'match': self._b64(b'wrong'),
                   'data': self._b64(b'v2')}]
        result = self.api.batch('v', 'wk', ops)
        assert result['status'] == 'conflict'
        # original content unchanged
        assert self.api.read('v', 'f') == b'v1'

    def test_write_if_match_empty_match_always_writes(self):
        ops    = [{'op': 'write-if-match', 'file_id': 'f',
                   'match': '',
                   'data': self._b64(b'new')}]
        result = self.api.batch('v', 'wk', ops)
        assert result['status'] == 'ok'
        assert self.api.read('v', 'f') == b'new'


# ---------------------------------------------------------------------------
# presigned methods raise RuntimeError on In_Memory
# ---------------------------------------------------------------------------

class Test_Vault__API__Presigned_Not_Available:

    def setup_method(self):
        self.api = Vault__API__In_Memory()
        self.api.setup()

    def test_presigned_initiate_raises(self):
        with pytest.raises(RuntimeError, match='presigned_not_available'):
            self.api.presigned_initiate('v', 'f', 1024, 1, 'wk')

    def test_presigned_complete_raises(self):
        with pytest.raises(RuntimeError, match='presigned_not_available'):
            self.api.presigned_complete('v', 'f', 'uid', [], 'wk')

    def test_presigned_cancel_raises(self):
        with pytest.raises(RuntimeError, match='presigned_not_available'):
            self.api.presigned_cancel('v', 'uid', 'f', 'wk')

    def test_presigned_read_url_raises(self):
        with pytest.raises(RuntimeError, match='presigned_not_available'):
            self.api.presigned_read_url('v', 'f')
