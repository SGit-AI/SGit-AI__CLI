import json
import os
import shutil

import pytest

from sgit_ai.crypto.Vault__Crypto        import Vault__Crypto
from sgit_ai.sync.Vault__Sync            import Vault__Sync
from sgit_ai.storage.Vault__Storage         import Vault__Storage
from sgit_ai.api.Vault__API__In_Memory   import Vault__API__In_Memory
from tests.unit.sync.vault_test_env      import Vault__Test_Env


class Test_Vault__Sync__Clone:

    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_single_vault(
            files={'init.txt': 'init'},
            vault_key='test-pass:tstvault'
        )

    @classmethod
    def teardown_class(cls):
        if cls._env:
            cls._env.cleanup_snapshot()

    def setup_method(self):
        self.env    = self._env.restore()
        self.crypto = self.env.crypto
        self.api    = self.env.api
        self.sync   = self.env.sync
        # The origin vault is at env.vault_dir; we put clones alongside it
        self.origin_dir = self.env.vault_dir

    def teardown_method(self):
        self.env.cleanup()

    def _vault_dir(self, name):
        return os.path.join(self.env.tmp_dir, name)

    # --- clone basics ---

    def test_clone_creates_directory(self):
        vault_key = self.env.vault_key
        clone_dir = self._vault_dir('cloned')
        result    = self.sync.clone(vault_key, clone_dir)

        assert os.path.isdir(clone_dir)
        assert result['directory'] == clone_dir
        assert result['vault_id']  == 'tstvault'

    def test_clone_creates_bare_structure(self):
        vault_key = self.env.vault_key
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
        vault_key = self.env.vault_key
        clone_dir = self._vault_dir('cloned')
        self.sync.clone(vault_key, clone_dir)

        vk_path = os.path.join(clone_dir, '.sg_vault', 'local', 'vault_key')
        assert os.path.isfile(vk_path)
        with open(vk_path) as f:
            assert f.read().strip() == vault_key

    def test_clone_creates_local_config(self):
        vault_key = self.env.vault_key
        clone_dir = self._vault_dir('cloned')
        result    = self.sync.clone(vault_key, clone_dir)

        storage     = Vault__Storage()
        config_path = storage.local_config_path(clone_dir)
        assert os.path.isfile(config_path)
        with open(config_path) as f:
            config = json.load(f)
        assert config['my_branch_id'] == result['branch_id']

    def test_clone_creates_clone_branch(self):
        vault_key = self.env.vault_key
        clone_dir = self._vault_dir('cloned')
        result    = self.sync.clone(vault_key, clone_dir)

        assert result['branch_id'].startswith('branch-clone-')
        assert result['named_branch'].startswith('branch-named-')

    def test_clone_has_correct_commit(self):
        vault_key = self.env.vault_key
        clone_dir = self._vault_dir('cloned')
        result    = self.sync.clone(vault_key, clone_dir)

        assert result['commit_id'] == self.env.commit_id

    def test_clone_status_is_clean(self):
        vault_key = self.env.vault_key
        clone_dir = self._vault_dir('cloned')
        self.sync.clone(vault_key, clone_dir)

        status = self.sync.status(clone_dir)
        assert status['clean']

    # --- clone with files ---

    def test_clone_two_parallel_subdirs(self):
        """Clone a vault pushed in two rounds: first before/, then after/.

        Regression test for the bug where only the first-pushed directory
        appeared in the cloned working copy (the named branch ref was not
        updated to the second commit on the server).
        """
        vault_key  = 'test-pass:tstvault'
        origin_dir = self._vault_dir('origin')
        self.sync.init(origin_dir, vault_key=vault_key)

        # First push: before/ directory only
        os.makedirs(os.path.join(origin_dir, 'before'))
        for i in range(3):
            with open(os.path.join(origin_dir, 'before', f'file{i}.txt'), 'w') as f:
                f.write(f'before file {i}')
        self.sync.commit(origin_dir, message='add before')
        push1 = self.sync.push(origin_dir)
        assert push1['status'] == 'pushed'

        # Second push: add after/ directory
        os.makedirs(os.path.join(origin_dir, 'after'))
        for i in range(3):
            with open(os.path.join(origin_dir, 'after', f'file{i}.txt'), 'w') as f:
                f.write(f'after file {i}')
        self.sync.commit(origin_dir, message='add after')
        push2 = self.sync.push(origin_dir)
        assert push2['status'] == 'pushed'

        # Clone should have BOTH before/ and after/
        clone_dir = self._vault_dir('cloned')
        self.sync.clone(vault_key, clone_dir)

        assert os.path.isdir(os.path.join(clone_dir, 'before')), 'before/ missing from clone'
        assert os.path.isdir(os.path.join(clone_dir, 'after')),  'after/ missing from clone'

        for i in range(3):
            with open(os.path.join(clone_dir, 'before', f'file{i}.txt')) as f:
                assert f.read() == f'before file {i}'
            with open(os.path.join(clone_dir, 'after', f'file{i}.txt')) as f:
                assert f.read() == f'after file {i}'

    def test_clone_extracts_working_copy(self):
        # This test creates its own origin (different files), uses a fresh API
        tmp_dir    = self.env.tmp_dir
        origin_dir = os.path.join(tmp_dir, 'origin2')
        self.sync.init(origin_dir, vault_key='test-pass:tstvault2')

        with open(os.path.join(origin_dir, 'README.md'), 'w') as f:
            f.write('# Hello World\n')
        os.makedirs(os.path.join(origin_dir, 'docs'), exist_ok=True)
        with open(os.path.join(origin_dir, 'docs', 'notes.txt'), 'w') as f:
            f.write('Some notes\n')

        self.sync.commit(origin_dir, message='add files')
        self.sync.push(origin_dir)

        clone_dir = os.path.join(tmp_dir, 'clone2')
        self.sync.clone('test-pass:tstvault2', clone_dir)

        assert os.path.isfile(os.path.join(clone_dir, 'README.md'))
        assert os.path.isfile(os.path.join(clone_dir, 'docs', 'notes.txt'))

        with open(os.path.join(clone_dir, 'README.md')) as f:
            assert f.read() == '# Hello World\n'

        with open(os.path.join(clone_dir, 'docs', 'notes.txt')) as f:
            assert f.read() == 'Some notes\n'

    def test_clone_then_status_clean(self):
        tmp_dir    = self.env.tmp_dir
        origin_dir = os.path.join(tmp_dir, 'origin3')
        self.sync.init(origin_dir, vault_key='test-pass:tstvault3')

        with open(os.path.join(origin_dir, 'file.txt'), 'w') as f:
            f.write('content')

        self.sync.commit(origin_dir, message='add file')
        self.sync.push(origin_dir)

        clone_dir = os.path.join(tmp_dir, 'clone3')
        self.sync.clone('test-pass:tstvault3', clone_dir)

        status = self.sync.status(clone_dir)
        assert status['clean']

    # --- clone round-trip (push from clone) ---

    def test_clone_commit_and_push(self):
        vault_key = self.env.vault_key
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
        vault_key = self.env.vault_key
        clone_dir = self._vault_dir('cloned')
        os.makedirs(clone_dir)
        with open(os.path.join(clone_dir, 'existing.txt'), 'w') as f:
            f.write('stuff')

        with pytest.raises(RuntimeError, match='not empty'):
            self.sync.clone(vault_key, clone_dir)

    # --- branches visible after clone ---

    def test_clone_branches_show_all(self):
        vault_key = self.env.vault_key
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
