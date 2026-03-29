import json
import os
import tempfile
import shutil
from sgit_ai.crypto.Vault__Crypto        import Vault__Crypto
from sgit_ai.objects.Vault__Ref_Manager  import Vault__Ref_Manager
from sgit_ai.sync.Vault__Bare        import Vault__Bare
from sgit_ai.sync.Vault__Sync        import Vault__Sync
from tests.unit.sync.vault_test_env  import Vault__Test_Env


class Test_Vault__Bare:

    _env = None

    @classmethod
    def setup_class(cls):
        """Create a vault snapshot that represents a bare-state vault once.

        We init a vault with two files, commit, advance the named ref to match
        the clone (simulating a push), then remove the working-copy files and
        the vault_key to produce the bare state.  This setup is done once and
        then restored cheaply for each test.
        """
        import copy

        from sgit_ai.api.Vault__API__In_Memory import Vault__API__In_Memory

        crypto = Vault__Crypto()
        api    = Vault__API__In_Memory()
        api.setup()
        sync = Vault__Sync(crypto=crypto, api=api)

        snap_dir  = tempfile.mkdtemp()
        vault_dir = os.path.join(snap_dir, 'vault')

        result     = sync.init(vault_dir)
        vault_key  = result['vault_key']

        with open(os.path.join(vault_dir, 'config.json'), 'wb') as f:
            f.write(b'{"key": "value"}')
        os.makedirs(os.path.join(vault_dir, 'deploy'), exist_ok=True)
        with open(os.path.join(vault_dir, 'deploy', 'run.sh'), 'wb') as f:
            f.write(b'deploy script contents')

        commit_result = sync.commit(vault_dir, 'add test files')

        # Advance named ref to match clone (simulates push)
        keys    = crypto.derive_keys_from_vault_key(vault_key)
        sg_dir  = os.path.join(vault_dir, '.sg_vault')
        ref_mgr = Vault__Ref_Manager(vault_path=sg_dir, crypto=crypto)
        ref_mgr.write_ref(keys['ref_file_id'], commit_result['commit_id'],
                          keys['read_key_bytes'])

        # Remove working copy files and vault key to simulate bare state
        os.remove(os.path.join(vault_dir, 'config.json'))
        shutil.rmtree(os.path.join(vault_dir, 'deploy'))
        vault_key_path = os.path.join(vault_dir, '.sg_vault', 'local', 'vault_key')
        if os.path.isfile(vault_key_path):
            os.remove(vault_key_path)

        # Persist for restore()
        cls._snap_dir   = snap_dir
        cls._vault_key  = vault_key
        cls._snap_store = copy.deepcopy(api._store)

    def setup_method(self):
        import copy
        from sgit_ai.api.Vault__API__In_Memory import Vault__API__In_Memory

        self.tmp_dir  = tempfile.mkdtemp()
        self.crypto   = Vault__Crypto()

        # Restore directory tree
        src = os.path.join(self._snap_dir, 'vault')
        dst = os.path.join(self.tmp_dir, 'vault')
        shutil.copytree(src, dst)
        self.tmp_dir = dst

        self.vault_key = self._vault_key
        self.bare      = Vault__Bare(crypto=self.crypto)

        api = Vault__API__In_Memory()
        api.setup()
        api._store = copy.deepcopy(self._snap_store)
        self.sync  = Vault__Sync(crypto=self.crypto, api=api)

    def teardown_method(self):
        parent = os.path.dirname(self.tmp_dir)
        shutil.rmtree(parent, ignore_errors=True)

    def test_is_bare__bare_vault(self):
        assert self.bare.is_bare(self.tmp_dir) is True

    def test_is_bare__with_vault_key(self):
        local_dir = os.path.join(self.tmp_dir, '.sg_vault', 'local')
        os.makedirs(local_dir, exist_ok=True)
        with open(os.path.join(local_dir, 'vault_key'), 'w') as f:
            f.write(self.vault_key)
        assert self.bare.is_bare(self.tmp_dir) is False

    def test_checkout__extracts_files(self):
        self.bare.checkout(self.tmp_dir, self.vault_key)
        assert os.path.isfile(os.path.join(self.tmp_dir, 'config.json'))
        assert os.path.isfile(os.path.join(self.tmp_dir, 'deploy', 'run.sh'))
        with open(os.path.join(self.tmp_dir, 'config.json'), 'rb') as f:
            assert f.read() == b'{"key": "value"}'

    def test_checkout__writes_vault_key(self):
        self.bare.checkout(self.tmp_dir, self.vault_key)
        vault_key_path = os.path.join(self.tmp_dir, '.sg_vault', 'local', 'vault_key')
        assert os.path.isfile(vault_key_path)
        with open(vault_key_path, 'r') as f:
            assert f.read() == self.vault_key

    def test_clean__removes_plaintext_files(self):
        self.bare.checkout(self.tmp_dir, self.vault_key)
        assert os.path.isfile(os.path.join(self.tmp_dir, 'config.json'))
        self.bare.clean(self.tmp_dir)
        assert not os.path.isfile(os.path.join(self.tmp_dir, 'config.json'))
        assert not os.path.isfile(os.path.join(self.tmp_dir, 'deploy', 'run.sh'))

    def test_clean__removes_vault_key(self):
        self.bare.checkout(self.tmp_dir, self.vault_key)
        self.bare.clean(self.tmp_dir)
        assert not os.path.isfile(os.path.join(self.tmp_dir, '.sg_vault', 'local', 'vault_key'))

    def test_clean__preserves_bare_structure(self):
        self.bare.checkout(self.tmp_dir, self.vault_key)
        self.bare.clean(self.tmp_dir)
        assert os.path.isdir(os.path.join(self.tmp_dir, '.sg_vault', 'bare', 'data'))
        assert os.path.isdir(os.path.join(self.tmp_dir, '.sg_vault', 'bare', 'refs'))

    def test_roundtrip__checkout_clean_verify(self):
        self.bare.checkout(self.tmp_dir, self.vault_key)
        assert not self.bare.is_bare(self.tmp_dir)
        self.bare.clean(self.tmp_dir)
        assert self.bare.is_bare(self.tmp_dir)
