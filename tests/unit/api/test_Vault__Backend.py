"""Tests for Vault__Backend abstract base class.

Covers:
  Lines 14, 17, 20, 23: NotImplementedError raised for each abstract method
  Lines 46-50: exists() via base-class try/except logic
"""
import pytest

from sgit_ai.network.api.Vault__Backend import Vault__Backend


class Test_Vault__Backend:

    def setup_method(self):
        self.backend = Vault__Backend()

    def test_read_raises_not_implemented(self):
        """Line 14: read() raises NotImplementedError."""
        with pytest.raises(NotImplementedError, match='read'):
            self.backend.read('some-id')

    def test_write_raises_not_implemented(self):
        """Line 17: write() raises NotImplementedError."""
        with pytest.raises(NotImplementedError, match='write'):
            self.backend.write('some-id', b'data')

    def test_delete_raises_not_implemented(self):
        """Line 20: delete() raises NotImplementedError."""
        with pytest.raises(NotImplementedError, match='delete'):
            self.backend.delete('some-id')

    def test_list_files_raises_not_implemented(self):
        """Line 23: list_files() raises NotImplementedError."""
        with pytest.raises(NotImplementedError, match='list_files'):
            self.backend.list_files()

    def test_exists_returns_true_when_read_succeeds(self):
        """Lines 46-48: read succeeds → exists returns True."""
        import unittest.mock
        with unittest.mock.patch.object(Vault__Backend, 'read', return_value=b'data'):
            assert self.backend.exists('some-id') is True

    def test_exists_returns_false_on_file_not_found(self):
        """Lines 46, 49-50: read raises FileNotFoundError → exists returns False."""
        import unittest.mock
        with unittest.mock.patch.object(Vault__Backend, 'read',
                                        side_effect=FileNotFoundError('missing')):
            assert self.backend.exists('some-id') is False

    def test_exists_returns_false_on_runtime_error(self):
        """Lines 46, 49-50: read raises RuntimeError → exists returns False."""
        import unittest.mock
        with unittest.mock.patch.object(Vault__Backend, 'read',
                                        side_effect=RuntimeError('corrupt')):
            assert self.backend.exists('some-id') is False
