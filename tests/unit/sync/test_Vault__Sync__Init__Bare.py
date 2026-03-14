import json
import os
import tempfile
import shutil

from sg_send_cli.crypto.Vault__Crypto        import Vault__Crypto
from sg_send_cli.sync.Vault__Sync            import Vault__Sync
from sg_send_cli.sync.Vault__Storage         import Vault__Storage
from sg_send_cli.api.Vault__API__In_Memory   import Vault__API__In_Memory


class Test_Vault__Sync__Init__Bare:

    def setup_method(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.crypto  = Vault__Crypto()
        self.api     = Vault__API__In_Memory()
        self.api.setup()
        self.sync    = Vault__Sync(crypto=self.crypto, api=self.api)

    def teardown_method(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def _vault_dir(self, name='my-vault'):
        return os.path.join(self.tmp_dir, name)

    def test_init_creates_bare_structure(self):
        directory = self._vault_dir()
        result    = self.sync.init(directory)
        storage   = Vault__Storage()

        assert os.path.isdir(storage.bare_dir(directory))
        assert os.path.isdir(storage.bare_data_dir(directory))
        assert os.path.isdir(storage.bare_refs_dir(directory))
        assert os.path.isdir(storage.bare_keys_dir(directory))
        assert os.path.isdir(storage.bare_indexes_dir(directory))
        assert os.path.isdir(storage.local_dir(directory))

    def test_init_returns_expected_keys(self):
        directory = self._vault_dir()
        result    = self.sync.init(directory)

        assert 'vault_key'    in result
        assert 'vault_id'     in result
        assert 'directory'    in result
        assert 'branch_id'    in result
        assert 'named_branch' in result
        assert 'commit_id'    in result

        assert result['branch_id'].startswith('branch-clone-')
        assert result['named_branch'].startswith('branch-named-')
        assert result['commit_id'].startswith('obj-')

    def test_init_creates_branch_index(self):
        directory = self._vault_dir()
        result    = self.sync.init(directory)
        storage   = Vault__Storage()

        indexes_dir = storage.bare_indexes_dir(directory)
        idx_files   = [f for f in os.listdir(indexes_dir) if f.startswith('idx-')]
        assert len(idx_files) == 1

    def test_init_creates_local_config(self):
        directory = self._vault_dir()
        result    = self.sync.init(directory)
        storage   = Vault__Storage()

        config_path = storage.local_config_path(directory)
        assert os.path.isfile(config_path)
        with open(config_path) as f:
            config = json.load(f)
        assert config['my_branch_id'] == result['branch_id']

    def test_init_writes_vault_key(self):
        directory = self._vault_dir()
        vault_key = 'my-passphrase:my-vault'
        result    = self.sync.init(directory, vault_key=vault_key)

        vk_path = os.path.join(directory, '.sg_vault', 'local', 'vault_key')
        assert os.path.isfile(vk_path)
        with open(vk_path) as f:
            assert f.read().strip() == vault_key

    def test_init_creates_refs(self):
        directory = self._vault_dir()
        result    = self.sync.init(directory)
        storage   = Vault__Storage()

        refs_dir  = storage.bare_refs_dir(directory)
        ref_files = [f for f in os.listdir(refs_dir) if f.startswith('ref-')]
        assert len(ref_files) == 2  # named branch ref + clone branch ref

    def test_init_creates_keys(self):
        directory = self._vault_dir()
        result    = self.sync.init(directory)
        storage   = Vault__Storage()

        keys_dir  = storage.bare_keys_dir(directory)
        key_files = [f for f in os.listdir(keys_dir) if f.startswith('key-')]
        assert len(key_files) >= 3  # at least: named pub + named priv + clone pub

    def test_init_fails_on_non_empty_directory(self):
        directory = self._vault_dir()
        os.makedirs(directory)
        with open(os.path.join(directory, 'existing.txt'), 'w') as f:
            f.write('stuff')

        import pytest
        with pytest.raises(RuntimeError, match='not empty'):
            self.sync.init(directory)

    def test_init_with_custom_vault_key(self):
        directory = self._vault_dir()
        result    = self.sync.init(directory, vault_key='test-pass:testvid1')
        assert result['vault_key'] == 'test-pass:testvid1'
        assert result['vault_id']  == 'testvid1'
