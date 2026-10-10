"""Tests for brief 10: chmod 0600 on .sg_vault/local/ files.

Verifies that every file written under .sg_vault/local/ is created with
owner-only permissions (0600), preventing other users on a multi-user host
from reading key material.  AppSec findings F02 / F07 / F11.
"""
from tests._helpers.vault_test_env import TEST_VAULT_KEYS
import os
import shutil
import tempfile

from sgit_ai.network.api.Vault__API__In_Memory  import Vault__API__In_Memory
from sgit_ai.cli.CLI__Token_Store       import CLI__Token_Store
from sgit_ai.crypto.Vault__Crypto       import Vault__Crypto
from sgit_ai.storage.Vault__Storage        import Vault__Storage
from sgit_ai.core.Vault__Sync           import Vault__Sync


def _mode(path: str) -> int:
    return os.stat(path).st_mode & 0o777


class Test_Vault__Sync__File_Modes:
    """Assertion: every .sg_vault/local/* write produces a 0600 file."""

    def setup_method(self):
        self.tmp    = tempfile.mkdtemp()
        self.crypto = Vault__Crypto()
        self.api    = Vault__API__In_Memory()
        self.api.setup()
        self.sync    = Vault__Sync(crypto=self.crypto, api=self.api)
        self.storage = Vault__Storage()

    def teardown_method(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    # -- init -----------------------------------------------------------------

    def test_init_vault_key_is_0600(self):
        vault_dir = os.path.join(self.tmp, 'vault')
        self.sync.init(vault_dir)
        path = self.storage.vault_key_path(vault_dir)
        assert os.path.isfile(path), 'vault_key not created'
        assert _mode(path) == 0o600, f'expected 0600, got {oct(_mode(path))}'

    def test_init_config_json_is_0600(self):
        vault_dir = os.path.join(self.tmp, 'vault')
        self.sync.init(vault_dir)
        path = self.storage.local_config_path(vault_dir)
        assert os.path.isfile(path), 'config.json not created'
        assert _mode(path) == 0o600, f'expected 0600, got {oct(_mode(path))}'

    # -- clone (full edit clone) ----------------------------------------------

    def _setup_origin_with_content(self, origin: str):
        r = self.sync.init(origin, vault_key=TEST_VAULT_KEYS[0])
        vault_key = r['vault_key']
        with open(os.path.join(origin, 'seed.txt'), 'w') as fh:
            fh.write('seed')
        self.sync.commit(origin, message='seed')
        self.sync.push(origin)
        return vault_key

    def test_clone_vault_key_is_0600(self):
        origin = os.path.join(self.tmp, 'origin')
        clone  = os.path.join(self.tmp, 'clone')
        vault_key = self._setup_origin_with_content(origin)
        self.sync.clone(vault_key, clone)
        path = self.storage.vault_key_path(clone)
        assert os.path.isfile(path), 'cloned vault_key not created'
        assert _mode(path) == 0o600, f'expected 0600, got {oct(_mode(path))}'

    def test_clone_config_json_is_0600(self):
        origin = os.path.join(self.tmp, 'origin')
        clone  = os.path.join(self.tmp, 'clone')
        vault_key = self._setup_origin_with_content(origin)
        self.sync.clone(vault_key, clone)
        path = self.storage.local_config_path(clone)
        assert os.path.isfile(path), 'cloned config.json not created'
        assert _mode(path) == 0o600, f'expected 0600, got {oct(_mode(path))}'

    # -- read-only clone ------------------------------------------------------

    def test_read_only_clone_clone_mode_json_is_0600(self):
        """clone_read_only writes clone_mode.json — it must be 0600."""
        origin = os.path.join(self.tmp, 'origin_ro')
        clone  = os.path.join(self.tmp, 'clone_ro')
        vault_key = self._setup_origin_with_content(origin)
        passphrase, vault_id = self.crypto.parse_vault_key(vault_key)
        read_key     = self.crypto.derive_read_key(passphrase, vault_id)
        read_key_hex = read_key.hex()
        self.sync.clone_read_only(vault_id, read_key_hex, clone)
        cm_path = self.storage.clone_mode_path(clone)
        assert os.path.isfile(cm_path), 'clone_mode.json not created by clone_read_only'
        assert _mode(cm_path) == 0o600, f'expected 0600, got {oct(_mode(cm_path))}'

    # -- token store ----------------------------------------------------------

    def test_token_store_save_token_is_0600(self):
        vault_dir = os.path.join(self.tmp, 'vault_tok')
        self.sync.init(vault_dir)
        store = CLI__Token_Store()
        store.save_token('test-token-abc', vault_dir)
        path = os.path.join(vault_dir, '.sg_vault', 'local', 'token')
        assert os.path.isfile(path), 'token file not created'
        assert _mode(path) == 0o600, f'expected 0600, got {oct(_mode(path))}'

    def test_token_store_save_base_url_is_0600(self):
        vault_dir = os.path.join(self.tmp, 'vault_url')
        self.sync.init(vault_dir)
        store = CLI__Token_Store()
        store.save_base_url('https://example.com', vault_dir)
        path = os.path.join(vault_dir, '.sg_vault', 'local', 'base_url')
        assert os.path.isfile(path), 'base_url file not created'
        assert _mode(path) == 0o600, f'expected 0600, got {oct(_mode(path))}'

    # -- rekey ----------------------------------------------------------------

    def test_rekey_new_vault_key_is_0600(self):
        vault_dir = os.path.join(self.tmp, 'vault_rekey')
        r = self.sync.init(vault_dir)
        vault_key = r['vault_key']
        # Write a file and commit so push has something to do
        with open(os.path.join(vault_dir, 'file.txt'), 'w') as fh:
            fh.write('hello')
        self.sync.commit(vault_dir, message='seed')
        self.sync.push(vault_dir)
        # Rekey
        self.sync.rekey(vault_dir)
        path = self.storage.vault_key_path(vault_dir)
        assert os.path.isfile(path), 'vault_key not present after rekey'
        assert _mode(path) == 0o600, f'expected 0600, got {oct(_mode(path))}'


class Test_Vault__Sync__File_Modes__Key_Bearing_Files:
    """Security review 0.21 (F9): three files that carry key material were written
    with the umask's mode (usually world-readable). Checked under a permissive umask."""

    def setup_method(self):
        self._old_umask = os.umask(0o022)

    def teardown_method(self):
        os.umask(self._old_umask)

    def test_bare_checkout_vault_key_is_0600(self, bare_vault_workspace):
        ws = bare_vault_workspace('small_vault')
        ws['bare'].checkout(ws['tmp_dir'], ws['vault_key'])
        assert _mode(os.path.join(ws['tmp_dir'], '.sg_vault', 'local', 'vault_key')) == 0o600

    def test_backup_zip_with_the_key_is_0600(self):
        from tests._helpers.vault_test_env              import Vault__Test_Env
        from sgit_ai.core.actions.backup.Vault__Backup import Vault__Backup
        env = Vault__Test_Env(); env.setup_single_vault(files={'a.txt': 'a'}); snap = env.restore()
        try:
            result = Vault__Backup().backup(snap.vault_dir, output_dir=snap.tmp_dir, include_key=True)
            path   = result.get('zip_path') or result.get('path') or next(
                os.path.join(snap.tmp_dir, f) for f in os.listdir(snap.tmp_dir) if f.endswith('.zip'))
            assert _mode(path) == 0o600
        finally:
            snap.cleanup(); env.cleanup_snapshot()

    def test_secrets_store_is_0600(self):
        from sgit_ai.secrets.Secrets__Store import Secrets__Store
        tmp   = tempfile.mkdtemp()
        try:
            path  = os.path.join(tmp, 'vaults.enc')
            store = Secrets__Store(store_path=path)
            store.store('a passphrase for the test', 'k', 'v')
            assert _mode(path) == 0o600
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
