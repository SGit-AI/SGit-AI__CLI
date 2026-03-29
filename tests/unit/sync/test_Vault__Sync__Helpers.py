import json
import os
import tempfile
import shutil
from sgit_ai.sync.Vault__Sync            import Vault__Sync, SG_VAULT_DIR
from sgit_ai.crypto.Vault__Crypto        import Vault__Crypto
from sgit_ai.objects.Vault__Object_Store import Vault__Object_Store
from sgit_ai.objects.Vault__Ref_Manager  import Vault__Ref_Manager
from sgit_ai.schemas.Schema__Object_Commit import Schema__Object_Commit
from sgit_ai.schemas.Schema__Object_Tree   import Schema__Object_Tree
from sgit_ai.api.Vault__API__In_Memory     import Vault__API__In_Memory
from tests.unit.sync.vault_test_env        import Vault__Test_Env


class Test_Vault__Sync__Generate_Vault_Key:

    def setup_method(self):
        self.crypto = Vault__Crypto()
        self.api    = Vault__API__In_Memory().setup()
        self.sync   = Vault__Sync(crypto=self.crypto, api=self.api)

    def test_generate_vault_key__format(self):
        key = self.sync.generate_vault_key()
        assert ':' in key
        parts = key.split(':')
        assert len(parts) == 2
        assert len(parts[0]) == 24
        assert len(parts[1]) == 8

    def test_generate_vault_key__unique(self):
        key1 = self.sync.generate_vault_key()
        key2 = self.sync.generate_vault_key()
        assert key1 != key2

    def test_generate_vault_key__valid_chars(self):
        key = self.sync.generate_vault_key()
        passphrase, vault_id = key.rsplit(':', 1)
        assert all(c.isalnum() for c in passphrase)
        assert all(c.isalnum() for c in vault_id)


class Test_Vault__Sync__Scan_Local:

    def setup_method(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.sync    = Vault__Sync(crypto=Vault__Crypto(), api=Vault__API__In_Memory().setup())

    def teardown_method(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_scan__empty_directory(self):
        result = self.sync._scan_local_directory(self.tmp_dir)
        assert result == {}

    def test_scan__ignores_sg_vault(self):
        sg_vault_dir = os.path.join(self.tmp_dir, SG_VAULT_DIR)
        os.makedirs(sg_vault_dir)
        with open(os.path.join(sg_vault_dir, 'some_file'), 'w') as f:
            f.write('internal')
        result = self.sync._scan_local_directory(self.tmp_dir)
        assert result == {}

    def test_scan__ignores_dotfiles(self):
        with open(os.path.join(self.tmp_dir, '.hidden'), 'w') as f:
            f.write('hidden')
        result = self.sync._scan_local_directory(self.tmp_dir)
        assert result == {}

    def test_scan__finds_regular_files(self):
        with open(os.path.join(self.tmp_dir, 'readme.md'), 'w') as f:
            f.write('hello')
        result = self.sync._scan_local_directory(self.tmp_dir)
        assert 'readme.md' in result
        assert result['readme.md']['size'] == 5

    def test_scan__nested_files(self):
        os.makedirs(os.path.join(self.tmp_dir, 'docs'))
        with open(os.path.join(self.tmp_dir, 'docs', 'api.md'), 'w') as f:
            f.write('api docs')
        result = self.sync._scan_local_directory(self.tmp_dir)
        assert 'docs/api.md' in result

    def test_scan__forward_slashes(self):
        os.makedirs(os.path.join(self.tmp_dir, 'a', 'b'))
        with open(os.path.join(self.tmp_dir, 'a', 'b', 'c.txt'), 'w') as f:
            f.write('deep')
        result = self.sync._scan_local_directory(self.tmp_dir)
        assert 'a/b/c.txt' in result


class Test_Vault__Sync__Init_And_Status:
    """Tests that need an initialised vault use the snapshot pattern.

    Tests that specifically test the init path itself (error cases, structure)
    still do their own lightweight init so assertions remain correct.
    """

    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_single_vault()

    def setup_method(self):
        self.env  = self._env.restore()
        self.sync = self.env.sync
        self.api  = self.env.api
        # Also keep a spare tmp_dir for tests that need their own vault dirs
        self._own_tmp = tempfile.mkdtemp()

    def teardown_method(self):
        self.env.cleanup()
        shutil.rmtree(self._own_tmp, ignore_errors=True)

    def test_init__creates_vault_structure(self):
        vault_dir = os.path.join(self._own_tmp, 'my-vault')
        api       = Vault__API__In_Memory().setup()
        sync      = Vault__Sync(crypto=Vault__Crypto(), api=api)
        result    = sync.init(vault_dir)
        assert os.path.isdir(os.path.join(vault_dir, SG_VAULT_DIR))
        assert os.path.isfile(os.path.join(vault_dir, SG_VAULT_DIR, 'local', 'vault_key'))
        assert 'vault_key' in result
        assert 'vault_id' in result

    def test_init__with_custom_vault_key(self):
        vault_dir = os.path.join(self._own_tmp, 'custom-vault')
        api       = Vault__API__In_Memory().setup()
        sync      = Vault__Sync(crypto=Vault__Crypto(), api=api)
        result    = sync.init(vault_dir, vault_key='my-custom-key:abcd1234')
        assert result['vault_key'] == 'my-custom-key:abcd1234'
        assert result['vault_id']  == 'abcd1234'

    def test_init__non_empty_directory_fails(self):
        vault_dir = os.path.join(self._own_tmp, 'non-empty')
        os.makedirs(vault_dir)
        with open(os.path.join(vault_dir, 'existing.txt'), 'w') as f:
            f.write('already here')
        import pytest
        api  = Vault__API__In_Memory().setup()
        sync = Vault__Sync(crypto=Vault__Crypto(), api=api)
        with pytest.raises(RuntimeError, match='not empty'):
            sync.init(vault_dir)

    def test_status__clean_after_init(self):
        # Snapshot vault is freshly initialised (no files), so status is clean
        status = self.sync.status(self.env.vault_dir)
        assert status['clean']    is True
        assert status['added']    == []
        assert status['modified'] == []
        assert status['deleted']  == []

    def test_status__detects_added_file(self):
        with open(os.path.join(self.env.vault_dir, 'new-file.txt'), 'w') as f:
            f.write('new content')
        status = self.sync.status(self.env.vault_dir)
        assert 'new-file.txt' in status['added']
        assert status['clean'] is False

    def test_commit__commits_new_files(self):
        with open(os.path.join(self.env.vault_dir, 'test.txt'), 'w') as f:
            f.write('commit me')
        result = self.sync.commit(self.env.vault_dir)
        assert 'commit_id' in result
        assert 'branch_id' in result

    def test_commit__then_status_clean(self):
        with open(os.path.join(self.env.vault_dir, 'file.txt'), 'w') as f:
            f.write('content')
        self.sync.commit(self.env.vault_dir)
        status = self.sync.status(self.env.vault_dir)
        assert status['clean'] is True
