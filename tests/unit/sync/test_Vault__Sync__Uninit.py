import json
import os
import re
import shutil
import tempfile
import time
import zipfile
import pytest

from sgit_ai.crypto.Vault__Crypto      import Vault__Crypto
from sgit_ai.sync.Vault__Sync          import Vault__Sync
from sgit_ai.api.Vault__API__In_Memory import Vault__API__In_Memory


class Test_Vault__Sync__Uninit:

    def setup_method(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.crypto  = Vault__Crypto()
        self.api     = Vault__API__In_Memory()
        self.api.setup()
        self.sync    = Vault__Sync(crypto=self.crypto, api=self.api)

    def teardown_method(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def _vault_dir(self, name='test-vault'):
        return os.path.join(self.tmp_dir, name)

    def _init_vault_with_files(self, name='test-vault'):
        directory = self._vault_dir(name)
        result    = self.sync.init(directory)
        with open(os.path.join(directory, 'hello.txt'), 'w') as f:
            f.write('hello world')
        self.sync.commit(directory, message='add hello.txt')
        return directory, result

    # --- uninit tests ---

    def test_uninit_creates_backup_zip(self):
        directory, _ = self._init_vault_with_files()
        result       = self.sync.uninit(directory)

        assert os.path.isfile(result['backup_path'])
        assert result['backup_path'].endswith('.zip')

    def test_uninit_backup_naming_convention(self):
        directory, _ = self._init_vault_with_files('my-vault')
        before_sec   = int(time.time())
        result       = self.sync.uninit(directory)
        after_sec    = int(time.time())

        backup_name = os.path.basename(result['backup_path'])
        # Pattern: .vault__{name}__{timestamp}.zip
        assert backup_name.startswith('.vault__my-vault__')
        assert backup_name.endswith('.zip')
        # Extract timestamp from filename
        m = re.search(r'__(\d+)\.zip$', backup_name)
        assert m, f'No timestamp in backup name: {backup_name}'
        ts = int(m.group(1))
        # Timestamp must be in seconds (not milliseconds)
        assert before_sec <= ts <= after_sec + 1
        assert ts < 10_000_000_000   # definitely seconds, not ms

    def test_uninit_backup_timestamp_is_seconds_not_ms(self):
        directory, _ = self._init_vault_with_files()
        result       = self.sync.uninit(directory)
        backup_name  = os.path.basename(result['backup_path'])
        m            = re.search(r'__(\d+)\.zip$', backup_name)
        ts           = int(m.group(1))
        # seconds have 10 digits, milliseconds have 13
        assert len(str(ts)) == 10

    def test_uninit_removes_sg_vault_dir(self):
        directory, _ = self._init_vault_with_files()
        sg_dir       = os.path.join(directory, '.sg_vault')
        assert os.path.isdir(sg_dir)

        self.sync.uninit(directory)

        assert not os.path.isdir(sg_dir)

    def test_uninit_preserves_working_files(self):
        directory, _ = self._init_vault_with_files()
        self.sync.uninit(directory)

        assert os.path.isfile(os.path.join(directory, 'hello.txt'))
        with open(os.path.join(directory, 'hello.txt')) as f:
            assert f.read() == 'hello world'

    def test_uninit_counts_working_files(self):
        directory, _ = self._init_vault_with_files()
        result       = self.sync.uninit(directory)

        assert result['working_files'] == 1   # only hello.txt

    def test_uninit_backup_is_valid_zip(self):
        directory, _ = self._init_vault_with_files()
        result       = self.sync.uninit(directory)

        with zipfile.ZipFile(result['backup_path'], 'r') as zf:
            names = zf.namelist()
        assert any('.sg_vault' in n for n in names)

    def test_uninit_backup_contains_sg_vault_structure(self):
        directory, _ = self._init_vault_with_files()
        result       = self.sync.uninit(directory)

        with zipfile.ZipFile(result['backup_path'], 'r') as zf:
            names = zf.namelist()
        # Must have key vault files
        assert any('vault_key' in n for n in names)
        assert any('config.json' in n for n in names)

    def test_uninit_returns_backup_size(self):
        directory, _ = self._init_vault_with_files()
        result       = self.sync.uninit(directory)

        assert result['backup_size'] > 0
        assert result['backup_size'] == os.path.getsize(result['backup_path'])

    def test_uninit_raises_if_not_a_vault(self):
        directory = self._vault_dir('not-a-vault')
        os.makedirs(directory)
        with pytest.raises(RuntimeError, match='Not a vault'):
            self.sync.uninit(directory)

    def test_uninit_result_contains_sg_vault_dir(self):
        directory, _ = self._init_vault_with_files()
        result       = self.sync.uninit(directory)
        assert '.sg_vault' in result['sg_vault_dir']


class Test_Vault__Sync__Restore:

    def setup_method(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.crypto  = Vault__Crypto()
        self.api     = Vault__API__In_Memory()
        self.api.setup()
        self.sync    = Vault__Sync(crypto=self.crypto, api=self.api)

    def teardown_method(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def _vault_dir(self, name='test-vault'):
        return os.path.join(self.tmp_dir, name)

    def _init_and_uninit(self, name='test-vault'):
        directory = self._vault_dir(name)
        init_result = self.sync.init(directory)
        with open(os.path.join(directory, 'data.txt'), 'w') as f:
            f.write('vault data')
        self.sync.commit(directory, message='add data')
        uninit_result = self.sync.uninit(directory)
        return directory, init_result, uninit_result

    # --- restore_from_backup tests ---

    def test_restore_recreates_sg_vault(self):
        directory, init_r, uninit_r = self._init_and_uninit()
        assert not os.path.isdir(os.path.join(directory, '.sg_vault'))

        self.sync.restore_from_backup(uninit_r['backup_path'], directory)

        assert os.path.isdir(os.path.join(directory, '.sg_vault'))

    def test_restore_returns_vault_id_and_branch_id(self):
        directory, init_r, uninit_r = self._init_and_uninit()
        result = self.sync.restore_from_backup(uninit_r['backup_path'], directory)

        assert result['vault_id'] == init_r['vault_id']
        assert result['branch_id'].startswith('branch-clone-')

    def test_restore_vault_is_functional(self):
        directory, init_r, uninit_r = self._init_and_uninit()
        self.sync.restore_from_backup(uninit_r['backup_path'], directory)

        # Should be able to read status
        status = self.sync.status(directory)
        assert 'clean' in status

    def test_restore_round_trip_preserves_working_files(self):
        directory, _, uninit_r = self._init_and_uninit()
        # data.txt should still be there (uninit doesn't remove working files)
        assert os.path.isfile(os.path.join(directory, 'data.txt'))

        self.sync.restore_from_backup(uninit_r['backup_path'], directory)

        assert os.path.isfile(os.path.join(directory, 'data.txt'))

    def test_restore_raises_if_zip_not_found(self):
        directory = self._vault_dir()
        os.makedirs(directory)
        with pytest.raises(RuntimeError, match='not found'):
            self.sync.restore_from_backup('/nonexistent/backup.zip', directory)

    def test_restore_raises_if_vault_already_exists(self):
        directory, init_r, uninit_r = self._init_and_uninit()
        # Restore once
        self.sync.restore_from_backup(uninit_r['backup_path'], directory)
        # Try to restore again without removing .sg_vault first
        with pytest.raises(RuntimeError, match='already exists'):
            self.sync.restore_from_backup(uninit_r['backup_path'], directory)

    def test_restore_returns_directory(self):
        directory, _, uninit_r = self._init_and_uninit()
        result = self.sync.restore_from_backup(uninit_r['backup_path'], directory)
        assert os.path.abspath(result['directory']) == os.path.abspath(directory)


class Test_Vault__Sync__Init__Allow_Nonempty:

    def setup_method(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.crypto  = Vault__Crypto()
        self.api     = Vault__API__In_Memory()
        self.api.setup()
        self.sync    = Vault__Sync(crypto=self.crypto, api=self.api)

    def teardown_method(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def _vault_dir(self, name='test-vault'):
        return os.path.join(self.tmp_dir, name)

    def test_init_allow_nonempty_skips_guard(self):
        directory = self._vault_dir()
        os.makedirs(directory)
        with open(os.path.join(directory, 'existing.txt'), 'w') as f:
            f.write('existing content')

        # Should NOT raise with allow_nonempty=True
        result = self.sync.init(directory, allow_nonempty=True)
        assert 'vault_id' in result

    def test_init_nonempty_without_flag_still_raises(self):
        directory = self._vault_dir()
        os.makedirs(directory)
        with open(os.path.join(directory, 'existing.txt'), 'w') as f:
            f.write('existing content')

        with pytest.raises(RuntimeError, match='not empty'):
            self.sync.init(directory, allow_nonempty=False)

    def test_init_allow_nonempty_preserves_existing_files(self):
        directory = self._vault_dir()
        os.makedirs(directory)
        with open(os.path.join(directory, 'existing.txt'), 'w') as f:
            f.write('keep me')

        self.sync.init(directory, allow_nonempty=True)

        assert os.path.isfile(os.path.join(directory, 'existing.txt'))
        with open(os.path.join(directory, 'existing.txt')) as f:
            assert f.read() == 'keep me'
