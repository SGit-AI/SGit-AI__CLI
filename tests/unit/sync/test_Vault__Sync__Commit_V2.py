import json
import os
import tempfile
import shutil

from sg_send_cli.crypto.Vault__Crypto        import Vault__Crypto
from sg_send_cli.api.Vault__API              import Vault__API
from sg_send_cli.sync.Vault__Sync            import Vault__Sync


class Vault__API__In_Memory(Vault__API):

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


class Test_Vault__Sync__Commit_V2:

    def setup_method(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.crypto  = Vault__Crypto()
        self.api     = Vault__API__In_Memory()
        self.api.setup()
        self.sync    = Vault__Sync(crypto=self.crypto, api=self.api)

    def teardown_method(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def _init_vault(self, name='my-vault'):
        directory = os.path.join(self.tmp_dir, name)
        return self.sync.init(directory), directory

    def test_commit_after_adding_file(self):
        init_result, directory = self._init_vault()

        with open(os.path.join(directory, 'hello.txt'), 'w') as f:
            f.write('hello world')

        result = self.sync.commit(directory, message='Add hello.txt')
        assert 'commit_id' in result
        assert result['commit_id'].startswith('obj-')
        assert result['message'] == 'Add hello.txt'
        assert result['branch_id'] == init_result['branch_id']

    def test_status_v2_detects_added_file(self):
        init_result, directory = self._init_vault()

        status = self.sync.status(directory)
        assert status['clean'] is True

        with open(os.path.join(directory, 'new.txt'), 'w') as f:
            f.write('new content')

        status = self.sync.status(directory)
        assert 'new.txt' in status['added']
        assert status['clean'] is False

    def test_commit_then_status_is_clean(self):
        _, directory = self._init_vault()

        with open(os.path.join(directory, 'file.txt'), 'w') as f:
            f.write('content')

        self.sync.commit(directory, message='Add file')

        status = self.sync.status(directory)
        assert status['clean'] is True

    def test_commit_detects_modified_file(self):
        _, directory = self._init_vault()

        with open(os.path.join(directory, 'file.txt'), 'w') as f:
            f.write('v1')
        self.sync.commit(directory, message='Add file')

        with open(os.path.join(directory, 'file.txt'), 'w') as f:
            f.write('v2 longer')

        status = self.sync.status(directory)
        assert 'file.txt' in status['modified']

    def test_commit_detects_deleted_file(self):
        _, directory = self._init_vault()

        with open(os.path.join(directory, 'gone.txt'), 'w') as f:
            f.write('temp')
        self.sync.commit(directory, message='Add file')

        os.remove(os.path.join(directory, 'gone.txt'))

        status = self.sync.status(directory)
        assert 'gone.txt' in status['deleted']

    def test_multiple_commits_chain(self):
        _, directory = self._init_vault()

        with open(os.path.join(directory, 'a.txt'), 'w') as f:
            f.write('first')
        r1 = self.sync.commit(directory, message='First')

        with open(os.path.join(directory, 'b.txt'), 'w') as f:
            f.write('second')
        r2 = self.sync.commit(directory, message='Second')

        assert r1['commit_id'] != r2['commit_id']
