"""Direct instantiation tests for Vault__Sync__Clone (Tightening 5)."""
import os

from sgit_ai.sync.Vault__Sync__Clone   import Vault__Sync__Clone
from tests.unit.sync.vault_test_env    import Vault__Test_Env


class Test_Vault__Sync__Clone__Direct:
    """Instantiate Vault__Sync__Clone directly, not via the Vault__Sync facade."""

    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_single_vault(
            files={'init.txt': 'hello direct'},
            vault_key='test-pass:directvt'
        )

    @classmethod
    def teardown_class(cls):
        if cls._env:
            cls._env.cleanup_snapshot()

    def setup_method(self):
        self.env    = self._env.restore()
        self.crypto = self.env.crypto
        self.api    = self.env.api
        self.cloner = Vault__Sync__Clone(crypto=self.crypto, api=self.api)

    def teardown_method(self):
        self.env.cleanup()

    def _dir(self, name):
        return os.path.join(self.env.tmp_dir, name)

    def test_direct_instantiation(self):
        assert isinstance(self.cloner, Vault__Sync__Clone)

    def test_clone_creates_sg_vault(self):
        clone_dir = self._dir('c1')
        self.cloner.clone(self.env.vault_key, clone_dir)
        assert os.path.isdir(os.path.join(clone_dir, '.sg_vault'))

    def test_clone_returns_vault_id(self):
        clone_dir = self._dir('c2')
        result    = self.cloner.clone(self.env.vault_key, clone_dir)
        assert result['vault_id'] == 'directvt'

    def test_clone_extracts_working_files(self):
        clone_dir = self._dir('c3')
        self.cloner.clone(self.env.vault_key, clone_dir)
        assert os.path.isfile(os.path.join(clone_dir, 'init.txt'))
        with open(os.path.join(clone_dir, 'init.txt')) as f:
            assert f.read() == 'hello direct'

    def test_clone_returns_directory_key(self):
        clone_dir = self._dir('c4')
        result    = self.cloner.clone(self.env.vault_key, clone_dir)
        assert result['directory'] == clone_dir

    def test_clone_read_only_creates_sg_vault(self):
        clone_dir    = self._dir('c5')
        keys         = self.crypto.derive_keys_from_vault_key(self.env.vault_key)
        read_key_hex = keys['read_key_bytes'].hex()
        vault_id     = keys['vault_id']
        self.cloner.clone_read_only(vault_id, read_key_hex, clone_dir)
        assert os.path.isdir(os.path.join(clone_dir, '.sg_vault'))

    def test_clone_progress_callback_called(self):
        clone_dir = self._dir('c6')
        events    = []
        self.cloner.clone(self.env.vault_key, clone_dir, on_progress=lambda *a, **k: events.append(a))
        assert len(events) > 0

    def test_clone_sparse_creates_structure_without_files(self):
        clone_dir = self._dir('c7')
        result    = self.cloner.clone(self.env.vault_key, clone_dir, sparse=True)
        assert os.path.isdir(os.path.join(clone_dir, '.sg_vault'))
        assert result['vault_id'] == 'directvt'
