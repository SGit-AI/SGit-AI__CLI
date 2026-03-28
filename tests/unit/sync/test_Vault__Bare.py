import json
import os
import tempfile
import shutil
from sgit_ai.crypto.Vault__Crypto        import Vault__Crypto
from sgit_ai.objects.Vault__Ref_Manager  import Vault__Ref_Manager
from sgit_ai.sync.Vault__Bare        import Vault__Bare
from sgit_ai.sync.Vault__Sync        import Vault__Sync


class Test_Vault__Bare:

    def setup_method(self):
        self.tmp_dir   = tempfile.mkdtemp()
        self.crypto    = Vault__Crypto()
        self.bare      = Vault__Bare(crypto=self.crypto)
        self.sync      = Vault__Sync(crypto=self.crypto)
        self._create_test_vault()

    def teardown_method(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def _create_test_vault(self):
        """Create a vault using Vault__Sync, commit files, then make it bare."""
        result = self.sync.init(self.tmp_dir)
        self.vault_key = result['vault_key']

        # Add files
        with open(os.path.join(self.tmp_dir, 'config.json'), 'wb') as f:
            f.write(b'{"key": "value"}')
        os.makedirs(os.path.join(self.tmp_dir, 'deploy'), exist_ok=True)
        with open(os.path.join(self.tmp_dir, 'deploy', 'run.sh'), 'wb') as f:
            f.write(b'deploy script contents')

        commit_result = self.sync.commit(self.tmp_dir, 'add test files')

        # Advance named ref to match clone (simulates push)
        keys     = self.crypto.derive_keys_from_vault_key(self.vault_key)
        sg_dir   = os.path.join(self.tmp_dir, '.sg_vault')
        ref_mgr  = Vault__Ref_Manager(vault_path=sg_dir, crypto=self.crypto)
        ref_mgr.write_ref(keys['ref_file_id'], commit_result['commit_id'], keys['read_key_bytes'])

        # Remove working copy files and vault key to simulate bare state
        os.remove(os.path.join(self.tmp_dir, 'config.json'))
        shutil.rmtree(os.path.join(self.tmp_dir, 'deploy'))
        vault_key_path = os.path.join(self.tmp_dir, '.sg_vault', 'local', 'vault_key')
        if os.path.isfile(vault_key_path):
            os.remove(vault_key_path)

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
