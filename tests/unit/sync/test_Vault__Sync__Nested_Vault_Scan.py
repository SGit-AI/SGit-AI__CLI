"""A folder holding its own .sg_vault is another vault (phase 0, B5).

The scan used to descend into it, so the outer vault's next commit took the inner
vault's working files (a nested clone, later a worktree) into the outer vault."""
import os

from sgit_ai.core.Vault__Head_Paths     import Vault__Head_Paths
from tests.unit.sync.vault_test_env      import Vault__Test_Env


class Test_Vault__Sync__Nested_Vault_Scan:

    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_single_vault(files={'top.txt': 'top', 'keep/tracked.txt': 'tracked'})

    def setup_method(self):
        self.env  = self._env.restore()
        self.sync = self.env.sync
        self.dir  = self.env.vault_dir

    def teardown_method(self):
        self.env.cleanup()

    def _write(self, rel, text):
        path = os.path.join(self.dir, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w') as f:
            f.write(text)

    def _plant_nested_vault(self, folder):
        os.makedirs(os.path.join(self.dir, folder, '.sg_vault', 'local'), exist_ok=True)

    def _head_paths(self):
        return set(Vault__Head_Paths(crypto=self.env.crypto).paths(self.dir))

    def test_status_skips_a_nested_vault_and_names_it(self):
        self._plant_nested_vault('inner')
        self._write('inner/secret-of-another-vault.txt', 'not ours')
        result = self.sync.status(self.dir)
        assert 'inner/secret-of-another-vault.txt' not in result['added']
        assert result['nested'] == ['inner']

    def test_commit_never_takes_the_nested_vault_files(self):
        self._plant_nested_vault('inner')
        self._write('inner/secret-of-another-vault.txt', 'not ours')
        self._write('new.txt', 'ours')
        self.sync.commit(self.dir, message='add new.txt')
        paths = self._head_paths()
        assert 'new.txt' in paths
        assert not any(p.startswith('inner/') for p in paths)

    def test_tracked_files_under_a_folder_that_becomes_a_vault_are_not_deleted(self):
        self._plant_nested_vault('keep')                                  # keep/tracked.txt is committed
        result = self.sync.status(self.dir)
        assert 'keep/tracked.txt' not in result['deleted']
        self._write('other.txt', 'x')
        self.sync.commit(self.dir, message='other')
        assert 'keep/tracked.txt' in self._head_paths()

    def test_a_plain_folder_is_still_scanned(self):
        self._write('plain/file.txt', 'x')
        result = self.sync.status(self.dir)
        assert 'plain/file.txt' in result['added']
        assert result['nested'] == []
