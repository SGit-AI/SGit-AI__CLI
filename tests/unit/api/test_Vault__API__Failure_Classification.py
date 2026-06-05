"""Tests for Vault__API per-file failure classification in batch_read.

Verifies that the new ``failures`` plumbing distinguishes 'absent on server'
(404 / per-file status='not_found'), 'forbidden' (403 / status='forbidden'),
and 'transient' (5xx / network) so the pull layer can produce honest user
messages.
"""
import base64
import json
from io import BytesIO
from unittest.mock import patch
from urllib.error import HTTPError, URLError

import pytest

from sgit_ai.network.api.Vault__API                  import Vault__API
from sgit_ai.network.api.Vault__API__In_Memory       import Vault__API__In_Memory
from sgit_ai.safe_types.Enum__Fetch_Failure_Class    import Enum__Fetch_Failure_Class


# ---------------------------------------------------------------------------
# _classify_per_file_status — unit-level
# ---------------------------------------------------------------------------

class Test_Vault__API__Classify_Per_File_Status:

    def setup_method(self):
        self.api = Vault__API(base_url='https://example.com', access_token='tok').setup()

    def test_status_not_found_classifies_as_absent(self):
        result = {'file_id': 'bare/data/obj-cas-imm-aabbccdd1122', 'status': 'not_found'}
        f      = self.api._classify_per_file_status('bare/data/obj-cas-imm-aabbccdd1122',
                                                    'not_found', result)
        assert f.classification == Enum__Fetch_Failure_Class.ABSENT
        assert str(f.error_message) == 'not_found'

    def test_status_error_classifies_as_transient(self):
        result = {'file_id': 'bare/data/obj-cas-imm-aabbccdd1122',
                  'status': 'error', 'message': 'internalissue'}
        f      = self.api._classify_per_file_status('bare/data/obj-cas-imm-aabbccdd1122',
                                                    'error', result)
        assert f.classification == Enum__Fetch_Failure_Class.TRANSIENT
        assert 'internalissue' in str(f.error_message)

    def test_unknown_status_classifies_as_transient(self):
        result = {'file_id': 'bare/data/obj-cas-imm-aabbccdd1122', 'status': 'weird'}
        f      = self.api._classify_per_file_status('bare/data/obj-cas-imm-aabbccdd1122',
                                                    'weird', result)
        assert f.classification == Enum__Fetch_Failure_Class.TRANSIENT

    def test_status_forbidden_classifies_as_forbidden(self):
        result = {'file_id': 'bare/data/obj-cas-imm-aabbccdd1122', 'status': 'forbidden'}
        f      = self.api._classify_per_file_status('bare/data/obj-cas-imm-aabbccdd1122',
                                                    'forbidden', result)
        assert f.classification == Enum__Fetch_Failure_Class.FORBIDDEN

    def test_file_id_strips_bare_data_prefix(self):
        result = {'file_id': 'bare/data/obj-cas-imm-aabbccdd1122', 'status': 'not_found'}
        f      = self.api._classify_per_file_status('bare/data/obj-cas-imm-aabbccdd1122',
                                                    'not_found', result)
        assert str(f.file_id) == 'obj-cas-imm-aabbccdd1122'


# ---------------------------------------------------------------------------
# _classify_exception — single-file path
# ---------------------------------------------------------------------------

class Test_Vault__API__Classify_Exception:

    def setup_method(self):
        self.api = Vault__API(base_url='https://example.com', access_token='tok').setup()

    def test_http_404_classifies_as_absent(self):
        err = HTTPError('http://x', 404, 'Not Found', {}, BytesIO(b''))
        f   = self.api._classify_exception('bare/data/obj-cas-imm-aabbccdd1122', err)
        assert f.classification == Enum__Fetch_Failure_Class.ABSENT

    def test_runtime_error_with_http_404_in_message_classifies_as_absent(self):
        err = RuntimeError('API Error: HTTP 404 Not Found')
        f   = self.api._classify_exception('bare/data/obj-cas-imm-aabbccdd1122', err)
        assert f.classification == Enum__Fetch_Failure_Class.ABSENT

    def test_http_403_classifies_as_forbidden(self):
        err = HTTPError('http://x', 403, 'Forbidden', {}, BytesIO(b''))
        f   = self.api._classify_exception('bare/data/obj-cas-imm-aabbccdd1122', err)
        assert f.classification == Enum__Fetch_Failure_Class.FORBIDDEN

    def test_runtime_error_with_http_403_in_message_classifies_as_forbidden(self):
        """The real pull path wraps the HTTPError via _api_error into
        'API Error: HTTP 403 Forbidden' — the exact failure the user hit."""
        err = RuntimeError('API Error: HTTP 403 Forbidden')
        f   = self.api._classify_exception('bare/data/obj-cas-imm-aabbccdd1122', err)
        assert f.classification == Enum__Fetch_Failure_Class.FORBIDDEN

    def test_http_500_classifies_as_transient(self):
        err = HTTPError('http://x', 500, 'Internal Server Error', {}, BytesIO(b''))
        f   = self.api._classify_exception('bare/data/obj-cas-imm-aabbccdd1122', err)
        assert f.classification == Enum__Fetch_Failure_Class.TRANSIENT

    def test_url_error_classifies_as_transient(self):
        err = URLError('connection refused')
        f   = self.api._classify_exception('bare/data/obj-cas-imm-aabbccdd1122', err)
        assert f.classification == Enum__Fetch_Failure_Class.TRANSIENT

    def test_in_memory_not_found_runtime_classifies_as_absent(self):
        """The in-memory backend raises ``RuntimeError('Not found: ...')`` on missing
        keys — pull's single-blob fallback must classify that as ABSENT."""
        err = RuntimeError('Not found: vault1/obj-cas-imm-aabbccdd1122')
        f   = self.api._classify_exception('bare/data/obj-cas-imm-aabbccdd1122', err)
        assert f.classification == Enum__Fetch_Failure_Class.ABSENT


# ---------------------------------------------------------------------------
# _batch_read_chunk → failures dict population
# ---------------------------------------------------------------------------

class Test_Vault__API__Batch_Read_Chunk__Failures:
    """Drive ``_batch_read_chunk`` with a mocked ``_request`` so we can shape
    the server response and verify the failures dict population."""

    def setup_method(self):
        self.api = Vault__API(base_url='https://example.com', access_token='tok').setup()

    def _mock_response(self, results):
        return {'status': 'ok', 'results': results}

    def test_all_not_found_populates_absent_failures(self):
        fids   = ['bare/data/obj-cas-imm-aabbccdd1111',
                  'bare/data/obj-cas-imm-aabbccdd2222']
        result = self._mock_response([{'file_id': f, 'status': 'not_found'} for f in fids])
        payloads = {}
        failures = {}
        with patch.object(self.api, '_request', return_value=result):
            self.api._batch_read_chunk('v1', fids, payloads, failures)
        assert all(payloads[f] is None for f in fids)
        assert len(failures) == 2
        for f in fids:
            assert failures[f].classification == Enum__Fetch_Failure_Class.ABSENT

    def test_mixed_responses_classified_correctly(self):
        fids    = ['bare/data/obj-cas-imm-aabbccdd1111',
                   'bare/data/obj-cas-imm-aabbccdd2222',
                   'bare/data/obj-cas-imm-aabbccdd3333']
        result  = self._mock_response([
            {'file_id': fids[0], 'status': 'ok',
             'data': base64.b64encode(b'present-content').decode()},
            {'file_id': fids[1], 'status': 'not_found'},
            {'file_id': fids[2], 'status': 'error', 'message': 'oops'},
        ])
        payloads = {}
        failures = {}
        with patch.object(self.api, '_request', return_value=result):
            self.api._batch_read_chunk('v1', fids, payloads, failures)
        assert payloads[fids[0]] == b'present-content'
        assert failures[fids[1]].classification == Enum__Fetch_Failure_Class.ABSENT
        assert failures[fids[2]].classification == Enum__Fetch_Failure_Class.TRANSIENT

    def test_no_failures_dict_means_no_classification(self):
        fids   = ['bare/data/obj-cas-imm-aabbccdd1111']
        result = self._mock_response([{'file_id': fids[0], 'status': 'not_found'}])
        payloads = {}
        with patch.object(self.api, '_request', return_value=result):
            # When ``failures`` is None we must NOT raise — caller opts out.
            self.api._batch_read_chunk('v1', fids, payloads, None)
        assert payloads[fids[0]] is None


# ---------------------------------------------------------------------------
# Vault__API__In_Memory.batch_read also accepts and populates the failures dict.
# ---------------------------------------------------------------------------

class Test_Vault__API__In_Memory__Failures:

    def setup_method(self):
        self.api = Vault__API__In_Memory().setup()

    def test_missing_file_populates_absent_failure(self):
        failures = {}
        result   = self.api.batch_read('v1', ['missing'], failures=failures)
        assert result['missing'] is None
        assert failures['missing'].classification == Enum__Fetch_Failure_Class.ABSENT

    def test_present_file_no_failure_entry(self):
        self.api.write('v1', 'f1', 'wk', b'hello')
        failures = {}
        self.api.batch_read('v1', ['f1'], failures=failures)
        assert 'f1' not in failures

    def test_mixed_classification(self):
        self.api.write('v1', 'present', 'wk', b'data')
        failures = {}
        self.api.batch_read('v1', ['present', 'absent'], failures=failures)
        assert 'present' not in failures
        assert failures['absent'].classification == Enum__Fetch_Failure_Class.ABSENT

    def test_failures_none_is_default_no_classification(self):
        # legacy callers (no failures kwarg) keep working unchanged
        result = self.api.batch_read('v1', ['missing'])
        assert result['missing'] is None
