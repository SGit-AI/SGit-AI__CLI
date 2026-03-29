from sgit_ai.api.API__Transfer import API__Transfer, LAMBDA_RESPONSE_LIMIT


class Test_API__Transfer__Upload_Large:
    """Unit tests for the multipart presigned upload path (_upload_large).

    These tests use method-level monkey-patching so no real HTTP calls are made,
    but the full _upload_large logic (key names, part slicing, completion) is
    exercised.  This catches schema mismatches like the part_urls / parts bug.
    """

    PART_SIZE  = 5 * 1024 * 1024       # 5 MB (server min)
    PAYLOAD    = b'X' * (6 * 1024 * 1024)  # 6 MB → forces large-upload path

    def setup_method(self):
        self.api = API__Transfer(base_url='https://dev.send.sgraph.ai',
                                 access_token='test-token')
        self.api.setup()

        # Track calls so tests can assert on them
        self._caps_calls      = 0
        self._initiate_calls  = []
        self._upload_calls    = []
        self._complete_calls  = []
        self._cancel_calls    = []

        # Inject stubs
        self.api.presigned_capabilities = self._stub_caps
        self.api.presigned_initiate     = self._stub_initiate
        self.api.upload_part            = self._stub_upload_part
        self.api.presigned_complete     = self._stub_complete
        self.api.presigned_cancel       = self._stub_cancel

    # --- stubs ---

    def _stub_caps(self):
        self._caps_calls += 1
        return {
            'presigned_upload'   : True,
            'multipart_upload'   : True,
            'presigned_download' : True,
            'direct_upload'      : True,
            'max_part_size'      : 10 * 1024 * 1024,
            'min_part_size'      : self.PART_SIZE,
            'max_parts'          : 10000,
        }

    def _stub_initiate(self, transfer_id, file_size_bytes, num_parts):
        self._initiate_calls.append(dict(transfer_id=transfer_id,
                                         file_size_bytes=file_size_bytes,
                                         num_parts=num_parts))
        part_urls = [
            dict(part_number=i + 1, upload_url=f'https://s3.example.com/part{i + 1}')
            for i in range(num_parts)
        ]
        return dict(upload_id='mock-upload-id', part_urls=part_urls)

    def _stub_upload_part(self, upload_url, part_data):
        self._upload_calls.append(dict(url=upload_url, size=len(part_data)))
        return f'etag-{len(self._upload_calls)}'

    def _stub_complete(self, transfer_id, upload_id, parts):
        self._complete_calls.append(dict(transfer_id=transfer_id,
                                         upload_id=upload_id,
                                         parts=parts))
        return {}

    def _stub_cancel(self, transfer_id, upload_id):
        self._cancel_calls.append(dict(transfer_id=transfer_id, upload_id=upload_id))
        return {}

    # --- tests ---

    def test_large_payload_triggers_upload_large(self):
        assert len(self.PAYLOAD) > LAMBDA_RESPONSE_LIMIT
        self.api._upload_large('xfer-001', self.PAYLOAD)
        assert self._caps_calls == 1

    def test_initiate_called_with_correct_size(self):
        self.api._upload_large('xfer-001', self.PAYLOAD)
        assert len(self._initiate_calls) == 1
        assert self._initiate_calls[0]['file_size_bytes'] == len(self.PAYLOAD)

    def test_all_parts_uploaded(self):
        self.api._upload_large('xfer-001', self.PAYLOAD)
        # 6 MB payload, 5 MB min part → 2 parts
        assert len(self._upload_calls) == 2

    def test_parts_cover_full_payload(self):
        self.api._upload_large('xfer-001', self.PAYLOAD)
        total = sum(c['size'] for c in self._upload_calls)
        assert total == len(self.PAYLOAD)

    def test_complete_called_once_with_etags(self):
        self.api._upload_large('xfer-001', self.PAYLOAD)
        assert len(self._complete_calls) == 1
        parts = self._complete_calls[0]['parts']
        assert all('etag' in p and 'part_number' in p for p in parts)

    def test_cancel_called_on_upload_failure(self):
        def _fail(url, data):
            raise RuntimeError('S3 unavailable')
        self.api.upload_part = _fail

        import pytest
        with pytest.raises(RuntimeError, match='S3 unavailable'):
            self.api._upload_large('xfer-001', self.PAYLOAD)

        assert len(self._cancel_calls) == 1
        assert self._cancel_calls[0]['upload_id'] == 'mock-upload-id'

    def test_no_presigned_upload_raises(self):
        self.api.presigned_capabilities = lambda: {'presigned_upload': False}

        import pytest
        with pytest.raises(RuntimeError, match='does not support presigned uploads'):
            self.api._upload_large('xfer-001', self.PAYLOAD)

    def test_error_includes_payload_size_and_caps(self):
        caps = {'presigned_upload': False, 'reason': 'disabled'}
        self.api.presigned_capabilities = lambda: caps

        import pytest
        with pytest.raises(RuntimeError) as exc_info:
            self.api._upload_large('xfer-001', self.PAYLOAD)
        msg = str(exc_info.value)
        assert '6.0 MB' in msg
        assert 'disabled' in msg


class Test_API__Transfer:

    def setup_method(self):
        self.api = API__Transfer(base_url='https://send.sgraph.ai', access_token='test-token-123')
        self.api.setup()

    def test_setup_default_base_url(self):
        api = API__Transfer()
        api.setup()
        assert str(api.base_url) == 'https://dev.send.sgraph.ai'

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
