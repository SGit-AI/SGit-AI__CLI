"""Tests for Vault__API__In_Memory tombstone support (Brief 02 Commit 1)."""
import pytest
from sgit_ai.network.api.Vault__API__In_Memory import Vault__API__In_Memory


class Test_Vault__API__In_Memory__Tombstone:

    def setup_method(self):
        self.api = Vault__API__In_Memory()
        self.api.setup()
        self.vault_id  = 'vault-abc123'
        self.write_key = 'fake-write-key'

    def test_delete_vault_creates_tombstone(self):
        self.api.write(self.vault_id, 'file1', self.write_key, b'data')
        self.api.delete_vault(self.vault_id, self.write_key)
        assert self.api.is_tombstoned(self.vault_id)

    def test_delete_vault_removes_all_files(self):
        self.api.write(self.vault_id, 'f1', self.write_key, b'a')
        self.api.write(self.vault_id, 'f2', self.write_key, b'b')
        result = self.api.delete_vault(self.vault_id, self.write_key)
        assert result['files_deleted'] == 2
        assert self.api.list_files(self.vault_id) == []

    def test_write_to_tombstoned_vault_raises_403(self):
        self.api.delete_vault(self.vault_id, self.write_key)
        with pytest.raises(RuntimeError, match='403'):
            self.api.write(self.vault_id, 'file1', self.write_key, b'data')

    def test_batch_to_tombstoned_vault_raises_403(self):
        self.api.delete_vault(self.vault_id, self.write_key)
        with pytest.raises(RuntimeError, match='403'):
            self.api.batch(self.vault_id, self.write_key,
                           [{'op': 'write', 'file_id': 'f1', 'data': ''}])

    def test_delete_file_on_tombstoned_vault_raises_403(self):
        self.api.delete_vault(self.vault_id, self.write_key)
        with pytest.raises(RuntimeError, match='403'):
            self.api.delete(self.vault_id, 'any_file', self.write_key)

    def test_read_still_allowed_after_tombstone(self):
        self.api.write(self.vault_id, 'file1', self.write_key, b'data')
        self.api.delete_vault(self.vault_id, self.write_key)
        # After delete_vault files are gone — but read should not raise 403
        with pytest.raises(RuntimeError, match='Not found'):
            self.api.read(self.vault_id, 'file1')

    def test_second_vault_unaffected_by_tombstone(self):
        other_vault = 'vault-other'
        self.api.write(other_vault, 'file1', self.write_key, b'other data')
        self.api.delete_vault(self.vault_id, self.write_key)
        assert not self.api.is_tombstoned(other_vault)
        assert self.api.read(other_vault, 'file1') == b'other data'
        self.api.write(other_vault, 'file2', self.write_key, b'more data')

    def test_tombstone_error_message_contains_guidance(self):
        self.api.delete_vault(self.vault_id, self.write_key)
        try:
            self.api.write(self.vault_id, 'file1', self.write_key, b'x')
            assert False, 'should have raised'
        except RuntimeError as e:
            msg = str(e)
            assert 'permanently deleted' in msg
            assert 'clone the new vault' in msg.lower()

    def test_is_tombstoned_false_for_live_vault(self):
        self.api.write(self.vault_id, 'f1', self.write_key, b'x')
        assert not self.api.is_tombstoned(self.vault_id)

    def test_double_delete_vault_idempotent(self):
        self.api.write(self.vault_id, 'f1', self.write_key, b'x')
        self.api.delete_vault(self.vault_id, self.write_key)
        result = self.api.delete_vault(self.vault_id, self.write_key)
        assert result['status'] == 'deleted'
        assert self.api.is_tombstoned(self.vault_id)
