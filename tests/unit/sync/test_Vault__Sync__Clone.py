import json
import os
import tempfile
import shutil

from sg_send_cli.crypto.Vault__Crypto        import Vault__Crypto
from sg_send_cli.sync.Vault__Sync            import Vault__Sync
from sg_send_cli.sync.Vault__Storage         import Vault__Storage
from sg_send_cli.api.Vault__API__In_Memory   import Vault__API__In_Memory


class Test_Vault__Sync__Clone:

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

    def _init_and_push(self, vault_key='test-pass:testvault'):
        directory = self._vault_dir('origin')
        result    = self.sync.init(directory, vault_key=vault_key)
        self.sync.push(directory)
        return directory, result

    # --- clone basics ---

    def test_clone_creates_directory(self):
        vault_key = 'test-pass:testvault'
        self._init_and_push(vault_key)

        clone_dir = self._vault_dir('cloned')
        result    = self.sync.clone(vault_key, clone_dir)

        assert os.path.isdir(clone_dir)
        assert result['directory'] == clone_dir
        assert result['vault_id']  == 'testvault'

    def test_clone_creates_bare_structure(self):
        vault_key = 'test-pass:testvault'
        self._init_and_push(vault_key)

        clone_dir = self._vault_dir('cloned')
        self.sync.clone(vault_key, clone_dir)

        storage = Vault__Storage()
        assert os.path.isdir(storage.bare_dir(clone_dir))
        assert os.path.isdir(storage.bare_data_dir(clone_dir))
        assert os.path.isdir(storage.bare_refs_dir(clone_dir))
        assert os.path.isdir(storage.bare_keys_dir(clone_dir))
        assert os.path.isdir(storage.bare_indexes_dir(clone_dir))
        assert os.path.isdir(storage.local_dir(clone_dir))

    def test_clone_writes_vault_key(self):
        vault_key = 'test-pass:testvault'
        self._init_and_push(vault_key)

        clone_dir = self._vault_dir('cloned')
        self.sync.clone(vault_key, clone_dir)

        vk_path = os.path.join(clone_dir, '.sg_vault', 'local', 'vault_key')
        assert os.path.isfile(vk_path)
        with open(vk_path) as f:
            assert f.read().strip() == vault_key

    def test_clone_creates_local_config(self):
        vault_key = 'test-pass:testvault'
        self._init_and_push(vault_key)

        clone_dir = self._vault_dir('cloned')
        result    = self.sync.clone(vault_key, clone_dir)

        storage     = Vault__Storage()
        config_path = storage.local_config_path(clone_dir)
        assert os.path.isfile(config_path)
        with open(config_path) as f:
            config = json.load(f)
        assert config['my_branch_id'] == result['branch_id']

    def test_clone_creates_clone_branch(self):
        vault_key = 'test-pass:testvault'
        self._init_and_push(vault_key)

        clone_dir = self._vault_dir('cloned')
        result    = self.sync.clone(vault_key, clone_dir)

        assert result['branch_id'].startswith('branch-clone-')
        assert result['named_branch'].startswith('branch-named-')

    def test_clone_has_correct_commit(self):
        vault_key = 'test-pass:testvault'
        origin_dir, init_result = self._init_and_push(vault_key)

        clone_dir = self._vault_dir('cloned')
        result    = self.sync.clone(vault_key, clone_dir)

        assert result['commit_id'] == init_result['commit_id']

    def test_clone_status_is_clean(self):
        vault_key = 'test-pass:testvault'
        self._init_and_push(vault_key)

        clone_dir = self._vault_dir('cloned')
        self.sync.clone(vault_key, clone_dir)

        status = self.sync.status(clone_dir)
        assert status['clean']

    # --- clone with files ---

    def test_clone_extracts_working_copy(self):
        vault_key  = 'test-pass:testvault'
        origin_dir = self._vault_dir('origin')
        self.sync.init(origin_dir, vault_key=vault_key)

        with open(os.path.join(origin_dir, 'README.md'), 'w') as f:
            f.write('# Hello World\n')
        os.makedirs(os.path.join(origin_dir, 'docs'), exist_ok=True)
        with open(os.path.join(origin_dir, 'docs', 'notes.txt'), 'w') as f:
            f.write('Some notes\n')

        self.sync.commit(origin_dir, message='add files')
        self.sync.push(origin_dir)

        clone_dir = self._vault_dir('cloned')
        self.sync.clone(vault_key, clone_dir)

        assert os.path.isfile(os.path.join(clone_dir, 'README.md'))
        assert os.path.isfile(os.path.join(clone_dir, 'docs', 'notes.txt'))

        with open(os.path.join(clone_dir, 'README.md')) as f:
            assert f.read() == '# Hello World\n'

        with open(os.path.join(clone_dir, 'docs', 'notes.txt')) as f:
            assert f.read() == 'Some notes\n'

    def test_clone_then_status_clean(self):
        vault_key  = 'test-pass:testvault'
        origin_dir = self._vault_dir('origin')
        self.sync.init(origin_dir, vault_key=vault_key)

        with open(os.path.join(origin_dir, 'file.txt'), 'w') as f:
            f.write('content')

        self.sync.commit(origin_dir, message='add file')
        self.sync.push(origin_dir)

        clone_dir = self._vault_dir('cloned')
        self.sync.clone(vault_key, clone_dir)

        status = self.sync.status(clone_dir)
        assert status['clean']

    # --- clone round-trip (push from clone) ---

    def test_clone_commit_and_push(self):
        vault_key  = 'test-pass:testvault'
        origin_dir = self._vault_dir('origin')
        self.sync.init(origin_dir, vault_key=vault_key)

        with open(os.path.join(origin_dir, 'original.txt'), 'w') as f:
            f.write('from origin')

        self.sync.commit(origin_dir, message='origin file')
        self.sync.push(origin_dir)

        clone_dir = self._vault_dir('cloned')
        self.sync.clone(vault_key, clone_dir)

        with open(os.path.join(clone_dir, 'from-clone.txt'), 'w') as f:
            f.write('from clone')

        commit_result = self.sync.commit(clone_dir, message='clone file')
        assert commit_result['commit_id'].startswith('obj-')

        push_result = self.sync.push(clone_dir)
        assert push_result['status'] == 'pushed'

    # --- error cases ---

    def test_clone_fails_on_non_empty_directory(self):
        vault_key = 'test-pass:testvault'
        self._init_and_push(vault_key)

        clone_dir = self._vault_dir('cloned')
        os.makedirs(clone_dir)
        with open(os.path.join(clone_dir, 'existing.txt'), 'w') as f:
            f.write('stuff')

        import pytest
        with pytest.raises(RuntimeError, match='not empty'):
            self.sync.clone(vault_key, clone_dir)

    # --- branches visible after clone ---

    def test_clone_branches_show_all(self):
        vault_key  = 'test-pass:testvault'
        self._init_and_push(vault_key)

        clone_dir = self._vault_dir('cloned')
        self.sync.clone(vault_key, clone_dir)

        branches_result = self.sync.branches(clone_dir)
        branches        = branches_result['branches']

        names = [b['name'] for b in branches]
        assert 'current' in names
        assert 'local'   in names

        types = {b['name']: b['branch_type'] for b in branches}
        assert types['current'] == 'named'

        current_branches = [b for b in branches if b['is_current']]
        assert len(current_branches) == 1
        assert current_branches[0]['name'] == 'local'
