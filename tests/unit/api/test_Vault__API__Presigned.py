"""Tests for the presigned multipart upload/download methods on Vault__API and Vault__API__In_Memory."""
import pytest
from sgit_ai.api.Vault__API           import Vault__API, LARGE_BLOB_THRESHOLD
from sgit_ai.api.Vault__API__In_Memory import Vault__API__In_Memory


class Test_Vault__API__Presigned:

    def setup_method(self):
        self.api = Vault__API__In_Memory()
        self.api.setup()

    def test_large_blob_threshold_value(self):
        assert LARGE_BLOB_THRESHOLD == 4 * 1024 * 1024

    def test_presigned_initiate_raises_in_memory(self):
        with pytest.raises(RuntimeError, match='presigned_not_available'):
            self.api.presigned_initiate('vault-1', 'bare/data/obj-abc',
                                        5_000_000, 1, 'write-key')

    def test_presigned_complete_raises_in_memory(self):
        with pytest.raises(RuntimeError, match='presigned_not_available'):
            self.api.presigned_complete('vault-1', 'bare/data/obj-abc',
                                        'upload-id-123',
                                        [{'part_number': 1, 'etag': '"abc"'}],
                                        'write-key')

    def test_presigned_cancel_raises_in_memory(self):
        with pytest.raises(RuntimeError, match='presigned_not_available'):
            self.api.presigned_cancel('vault-1', 'upload-id-123',
                                      'bare/data/obj-abc', 'write-key')

    def test_presigned_read_url_raises_in_memory(self):
        with pytest.raises(RuntimeError, match='presigned_not_available'):
            self.api.presigned_read_url('vault-1', 'bare/data/obj-abc')

    def test_vault_api_has_presigned_methods(self):
        api = Vault__API()
        assert callable(api.presigned_initiate)
        assert callable(api.presigned_complete)
        assert callable(api.presigned_cancel)
        assert callable(api.presigned_read_url)
