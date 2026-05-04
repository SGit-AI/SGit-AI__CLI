import json
import os
import re
import shutil
import tempfile
import time
import zipfile
import pytest

from sgit_ai.crypto.Vault__Crypto      import Vault__Crypto
from sgit_ai.core.Vault__Sync          import Vault__Sync
from sgit_ai.api.Vault__API__In_Memory import Vault__API__In_Memory
from tests.unit.sync.vault_test_env    import Vault__Test_Env


class Test_Vault__Sync__Uninit:
    """Tests for sync.uninit().

    Each test gets an isolated copy of a pre-built vault (init + 'hello.txt' committed)
    via the Vault__Test_Env snapshot pattern.  Uninit is a destructive operation so every
    test must have its own copy — restore() provides that at ~3 ms cost.
    """

    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        # Build snapshot: vault named 'my-vault' with hello.txt committed
        cls._env.setup_single_vault(files={'hello.txt': 'hello world'})

    def setup_method(self):
        self.env       = self._env.restore()
        self.crypto    = self.env.crypto
        self.api       = self.env.api
        self.sync      = self.env.sync
        self.directory = self.env.vault_dir

    def teardown_method(self):
        self.env.cleanup()

    # --- uninit tests ---

    def test_uninit_creates_backup_zip(self):
        result = self.sync.uninit(self.directory)

        assert os.path.isfile(result['backup_path'])
        assert result['backup_path'].endswith('.zip')

    def test_uninit_backup_naming_convention(self):
        # The snapshot vault dir is named 'vault' (from setup_single_vault)
        before_sec = int(time.time())
        result     = self.sync.uninit(self.directory)
        after_sec  = int(time.time())

        backup_name = os.path.basename(result['backup_path'])
        # Pattern: .vault__{name}__{timestamp}.zip
        assert backup_name.startswith('.vault__vault__')
        assert backup_name.endswith('.zip')
        # Extract timestamp from filename
        m = re.search(r'__(\d+)\.zip$', backup_name)
        assert m, f'No timestamp in backup name: {backup_name}'
        ts = int(m.group(1))
        # Timestamp must be in seconds (not milliseconds)
        assert before_sec <= ts <= after_sec + 1
        assert ts < 10_000_000_000   # definitely seconds, not ms

    def test_uninit_backup_timestamp_is_seconds_not_ms(self):
        result      = self.sync.uninit(self.directory)
        backup_name = os.path.basename(result['backup_path'])
        m           = re.search(r'__(\d+)\.zip$', backup_name)
        ts          = int(m.group(1))
        # seconds have 10 digits, milliseconds have 13
        assert len(str(ts)) == 10

    def test_uninit_removes_sg_vault_dir(self):
        sg_dir = os.path.join(self.directory, '.sg_vault')
        assert os.path.isdir(sg_dir)

        self.sync.uninit(self.directory)

        assert not os.path.isdir(sg_dir)

    def test_uninit_preserves_working_files(self):
        self.sync.uninit(self.directory)

        assert os.path.isfile(os.path.join(self.directory, 'hello.txt'))
        with open(os.path.join(self.directory, 'hello.txt')) as f:
            assert f.read() == 'hello world'

    def test_uninit_counts_working_files(self):
        result = self.sync.uninit(self.directory)

        assert result['working_files'] == 1   # only hello.txt

    def test_uninit_backup_is_valid_zip(self):
        result = self.sync.uninit(self.directory)

        with zipfile.ZipFile(result['backup_path'], 'r') as zf:
            names = zf.namelist()
        assert any('.sg_vault' in n for n in names)

    def test_uninit_backup_contains_sg_vault_structure(self):
        result = self.sync.uninit(self.directory)

        with zipfile.ZipFile(result['backup_path'], 'r') as zf:
            names = zf.namelist()
        # Must have key vault files
        assert any('vault_key' in n for n in names)
        assert any('config.json' in n for n in names)

    def test_uninit_returns_backup_size(self):
        result = self.sync.uninit(self.directory)

        assert result['backup_size'] > 0
        assert result['backup_size'] == os.path.getsize(result['backup_path'])

    def test_uninit_raises_if_not_a_vault(self):
        # Use a fresh empty directory (not the snapshot vault)
        not_a_vault = os.path.join(self.env.tmp_dir, 'not-a-vault')
        os.makedirs(not_a_vault)
        with pytest.raises(RuntimeError, match='Not a vault'):
            self.sync.uninit(not_a_vault)

    def test_uninit_result_contains_sg_vault_dir(self):
        result = self.sync.uninit(self.directory)
        assert '.sg_vault' in result['sg_vault_dir']


class Test_Vault__Sync__Restore:
    """Tests for sync.restore_from_backup().

    Each test needs a vault that has been uninit-ed (producing a backup zip).
    We build the snapshot once (init + commit + uninit) and restore from it.
    """

    _env          = None
    _backup_path  = None   # path to the backup zip inside the snapshot dir

    @classmethod
    def setup_class(cls):
        # Build a vault, uninit it, capture the backup zip path
        crypto = Vault__Crypto()
        api    = Vault__API__In_Memory()
        api.setup()
        sync   = Vault__Sync(crypto=crypto, api=api)

        import copy
        snap_dir  = tempfile.mkdtemp()
        vault_dir = os.path.join(snap_dir, 'vault')
        init_result = sync.init(vault_dir)
        with open(os.path.join(vault_dir, 'data.txt'), 'w') as f:
            f.write('vault data')
        sync.commit(vault_dir, message='add data')

        uninit_result = sync.uninit(vault_dir)

        cls._snap_dir     = snap_dir
        cls._backup_path  = uninit_result['backup_path']
        cls._init_result  = init_result
        # No API state to snapshot here (uninit vault doesn't use remote)
        # Just store minimal info
        cls._crypto       = crypto

    @classmethod
    def teardown_class(cls):
        if cls._snap_dir and os.path.isdir(cls._snap_dir):
            shutil.rmtree(cls._snap_dir, ignore_errors=True)

    def setup_method(self):
        # Each test needs its own directory to restore into
        self.tmp_dir  = tempfile.mkdtemp()
        self.crypto   = Vault__Crypto()
        self.api      = Vault__API__In_Memory()
        self.api.setup()
        self.sync     = Vault__Sync(crypto=self.crypto, api=self.api)
        # Fresh target directory (with data.txt already there, as uninit preserves it)
        self.directory = os.path.join(self.tmp_dir, 'vault')
        os.makedirs(self.directory)
        # Put data.txt back (uninit preserves working files but we're in a new tmp)
        with open(os.path.join(self.directory, 'data.txt'), 'w') as f:
            f.write('vault data')
        self.backup_path = self.__class__._backup_path
        self.init_result = self.__class__._init_result

    def teardown_method(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    # --- restore_from_backup tests ---

    def test_restore_recreates_sg_vault(self):
        assert not os.path.isdir(os.path.join(self.directory, '.sg_vault'))

        self.sync.restore_from_backup(self.backup_path, self.directory)

        assert os.path.isdir(os.path.join(self.directory, '.sg_vault'))

    def test_restore_returns_vault_id_and_branch_id(self):
        result = self.sync.restore_from_backup(self.backup_path, self.directory)

        assert result['vault_id'] == self.init_result['vault_id']
        assert result['branch_id'].startswith('branch-clone-')

    def test_restore_vault_is_functional(self):
        self.sync.restore_from_backup(self.backup_path, self.directory)

        # Should be able to read status
        status = self.sync.status(self.directory)
        assert 'clean' in status

    def test_restore_round_trip_preserves_working_files(self):
        # data.txt should still be there (uninit doesn't remove working files)
        assert os.path.isfile(os.path.join(self.directory, 'data.txt'))

        self.sync.restore_from_backup(self.backup_path, self.directory)

        assert os.path.isfile(os.path.join(self.directory, 'data.txt'))

    def test_restore_raises_if_zip_not_found(self):
        with pytest.raises(RuntimeError, match='not found'):
            self.sync.restore_from_backup('/nonexistent/backup.zip', self.directory)

    def test_restore_raises_if_vault_already_exists(self):
        # Restore once
        self.sync.restore_from_backup(self.backup_path, self.directory)
        # Try to restore again without removing .sg_vault first
        with pytest.raises(RuntimeError, match='already exists'):
            self.sync.restore_from_backup(self.backup_path, self.directory)

    def test_restore_returns_directory(self):
        result = self.sync.restore_from_backup(self.backup_path, self.directory)
        assert os.path.abspath(result['directory']) == os.path.abspath(self.directory)


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
