import json
import os
import tempfile
import shutil
import pytest

from sg_send_cli.crypto.Vault__Crypto        import Vault__Crypto
from sg_send_cli.sync.Vault__Sync            import Vault__Sync
from sg_send_cli.api.Vault__API__In_Memory   import Vault__API__In_Memory


class Test_Vault__Sync__Init:

    def setup_method(self):
        self.tmp_dir  = tempfile.mkdtemp()
        self.crypto   = Vault__Crypto()
        self.api      = Vault__API__In_Memory()
        self.api.setup()
        self.sync     = Vault__Sync(crypto=self.crypto, api=self.api)

    def teardown_method(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def _vault_dir(self, name='my-vault'):
        return os.path.join(self.tmp_dir, name)

    def test_init_creates_sg_vault_structure(self):
        directory = self._vault_dir()
        result    = self.sync.init(directory)

        assert os.path.isdir(os.path.join(directory, '.sg_vault'))
        assert os.path.isdir(os.path.join(directory, '.sg_vault', 'bare', 'data'))
        assert os.path.isdir(os.path.join(directory, '.sg_vault', 'bare', 'refs'))
        assert os.path.isdir(os.path.join(directory, '.sg_vault', 'bare', 'keys'))
        assert os.path.isdir(os.path.join(directory, '.sg_vault', 'bare', 'indexes'))
        assert os.path.isdir(os.path.join(directory, '.sg_vault', 'local'))
        assert os.path.isfile(os.path.join(directory, '.sg_vault', 'VAULT-KEY'))

    def test_init_returns_vault_key_and_id(self):
        directory = self._vault_dir()
        result    = self.sync.init(directory)

        assert 'vault_key' in result
        assert 'vault_id'  in result
        assert 'directory'  in result
        assert ':' in result['vault_key']
        assert result['vault_id'] in result['vault_key']

    def test_init_with_custom_vault_key(self):
        directory = self._vault_dir()
        vault_key = 'my-passphrase:my-vault-id'
        result    = self.sync.init(directory, vault_key=vault_key)

        assert result['vault_key'] == vault_key
        assert result['vault_id']  == 'my-vault-id'

        stored_key = open(os.path.join(directory, '.sg_vault', 'VAULT-KEY')).read().strip()
        assert stored_key == vault_key

    def test_init_generates_random_key_when_not_provided(self):
        dir1   = self._vault_dir('v1')
        dir2   = self._vault_dir('v2')
        result1 = self.sync.init(dir1)
        result2 = self.sync.init(dir2)

        assert result1['vault_key'] != result2['vault_key']

    def test_init_returns_branch_info(self):
        directory = self._vault_dir()
        result    = self.sync.init(directory)

        assert 'branch_id' in result
        assert 'named_branch' in result
        assert 'commit_id' in result
        assert result['branch_id'].startswith('branch-clone-')
        assert result['named_branch'].startswith('branch-named-')

    def test_init_fails_on_non_empty_directory(self):
        directory = self._vault_dir()
        os.makedirs(directory)
        with open(os.path.join(directory, 'existing.txt'), 'w') as f:
            f.write('stuff')

        with pytest.raises(RuntimeError, match='not empty'):
            self.sync.init(directory)

    def test_init_vault_then_add_file_and_commit(self):
        directory = self._vault_dir()
        self.sync.init(directory)

        with open(os.path.join(directory, 'hello.txt'), 'w') as f:
            f.write('hello world')

        status = self.sync.status(directory)
        assert 'hello.txt' in status['added']

        result = self.sync.commit(directory)
        assert 'commit_id' in result

        status = self.sync.status(directory)
        assert status['clean']
