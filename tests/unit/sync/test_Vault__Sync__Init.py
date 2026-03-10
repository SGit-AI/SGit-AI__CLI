import json
import os
import tempfile
import shutil
import pytest

from sg_send_cli.crypto.Vault__Crypto        import Vault__Crypto
from sg_send_cli.api.Vault__API              import Vault__API
from sg_send_cli.sync.Vault__Sync            import Vault__Sync


class Vault__API__In_Memory(Vault__API):
    """API that stores writes in memory instead of hitting a server."""

    def setup(self):
        self._store = {}
        return self

    def write(self, vault_id: str, file_id: str, write_key: str, payload: bytes) -> dict:
        self._store[f'{vault_id}/{file_id}'] = payload
        return {'status': 'ok'}

    def read(self, vault_id: str, file_id: str) -> bytes:
        key = f'{vault_id}/{file_id}'
        if key not in self._store:
            raise RuntimeError(f'Not found: {key}')
        return self._store[key]


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
        assert os.path.isdir(os.path.join(directory, '.sg_vault', 'objects'))
        assert os.path.isfile(os.path.join(directory, '.sg_vault', 'refs', 'head'))
        assert os.path.isfile(os.path.join(directory, '.sg_vault', 'VAULT-KEY'))
        assert os.path.isfile(os.path.join(directory, '.sg_vault', 'tree.json'))
        assert os.path.isfile(os.path.join(directory, '.sg_vault', 'settings.json'))

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

    def test_init_uploads_tree_and_settings(self):
        directory = self._vault_dir()
        vault_key = 'test-pass:test-vid'
        result    = self.sync.init(directory, vault_key=vault_key)

        keys     = self.crypto.derive_keys_from_vault_key(vault_key)
        vault_id = keys['vault_id']
        read_key = keys['read_key_bytes']

        tree_data = json.loads(self.crypto.decrypt(
            read_key, self.api.read(vault_id, keys['tree_file_id'])))
        assert tree_data['version'] == 1
        assert '/' in tree_data['tree']

        settings_data = json.loads(self.crypto.decrypt(
            read_key, self.api.read(vault_id, keys['settings_file_id'])))
        assert settings_data['vault_id'] == vault_id

    def test_init_fails_on_non_empty_directory(self):
        directory = self._vault_dir()
        os.makedirs(directory)
        with open(os.path.join(directory, 'existing.txt'), 'w') as f:
            f.write('stuff')

        with pytest.raises(RuntimeError, match='not empty'):
            self.sync.init(directory)

    def test_init_vault_can_be_cloned(self):
        directory  = self._vault_dir('original')
        vault_key  = 'round-trip:rt-vault'
        self.sync.init(directory, vault_key=vault_key)

        clone_dir  = self._vault_dir('cloned')
        clone_path = self.sync.clone(vault_key, clone_dir)

        assert os.path.isdir(os.path.join(clone_path, '.sg_vault'))
        assert os.path.isfile(os.path.join(clone_path, '.sg_vault', 'VAULT-KEY'))

    def test_init_vault_then_add_file_and_push(self):
        directory = self._vault_dir()
        vault_key = 'push-test:push-vid'
        self.sync.init(directory, vault_key=vault_key)

        with open(os.path.join(directory, 'hello.txt'), 'w') as f:
            f.write('hello world')

        status = self.sync.status(directory)
        assert 'hello.txt' in status['added']

        result = self.sync.push(directory)
        assert 'hello.txt' in result['added']

        status = self.sync.status(directory)
        assert status['clean']
