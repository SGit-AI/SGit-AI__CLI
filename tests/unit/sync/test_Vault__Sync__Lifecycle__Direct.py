"""Direct instantiation tests for Vault__Sync__Lifecycle (Tightening 5)."""
import os

import pytest

from sgit_ai.core.actions.lifecycle.Vault__Sync__Lifecycle import Vault__Sync__Lifecycle
from tests.unit.sync.vault_test_env      import Vault__Test_Env


class Test_Vault__Sync__Lifecycle__Direct:
    """Instantiate Vault__Sync__Lifecycle directly, not via the Vault__Sync facade."""

    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_single_vault(files={'data.txt': 'lifecycle content'})

    def setup_method(self):
        self.env       = self._env.restore()
        self.lifecycle = Vault__Sync__Lifecycle(crypto=self.env.crypto, api=self.env.api)
        self.directory = self.env.vault_dir

    def teardown_method(self):
        self.env.cleanup()

    def test_direct_instantiation(self):
        assert isinstance(self.lifecycle, Vault__Sync__Lifecycle)

    def test_uninit_removes_sg_vault(self):
        sg_dir = os.path.join(self.directory, '.sg_vault')
        assert os.path.isdir(sg_dir)
        self.lifecycle.uninit(self.directory)
        assert not os.path.isdir(sg_dir)

    def test_uninit_creates_backup_zip(self):
        result = self.lifecycle.uninit(self.directory)
        assert os.path.isfile(result['backup_path'])
        assert result['backup_path'].endswith('.zip')

    def test_uninit_preserves_working_files(self):
        self.lifecycle.uninit(self.directory)
        assert os.path.isfile(os.path.join(self.directory, 'data.txt'))

    def test_uninit_raises_if_not_vault(self):
        not_a_vault = os.path.join(self.env.tmp_dir, 'empty-dir')
        os.makedirs(not_a_vault)
        with pytest.raises(RuntimeError, match='Not a vault'):
            self.lifecycle.uninit(not_a_vault)

    def test_rekey_check_returns_expected_keys(self):
        result = self.lifecycle.rekey_check(self.directory)
        assert 'vault_id'   in result
        assert 'file_count' in result
        assert 'obj_count'  in result
        assert 'clean'      in result

    def test_rekey_wipe_removes_sg_vault(self):
        self.lifecycle.rekey_wipe(self.directory)
        sg_dir = os.path.join(self.directory, '.sg_vault')
        assert not os.path.isdir(sg_dir)

    def test_rekey_wipe_returns_objects_removed(self):
        result = self.lifecycle.rekey_wipe(self.directory)
        assert 'objects_removed' in result
        assert result['objects_removed'] >= 0

    def test_restore_from_backup_recreates_sg_vault(self):
        uninit_result = self.lifecycle.uninit(self.directory)
        backup_path   = uninit_result['backup_path']

        lc2    = Vault__Sync__Lifecycle(crypto=self.env.crypto, api=self.env.api)
        result = lc2.restore_from_backup(backup_path, self.directory)

        assert os.path.isdir(os.path.join(self.directory, '.sg_vault'))
        assert 'vault_id'  in result
        assert 'branch_id' in result

    def test_restore_from_backup_raises_if_zip_missing(self):
        with pytest.raises(RuntimeError, match='not found'):
            self.lifecycle.restore_from_backup('/no/such/file.zip', self.directory)
