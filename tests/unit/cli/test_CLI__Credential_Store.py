import os
import json
import time
import tempfile
import shutil
import pytest
from sg_send_cli.cli.CLI__Credential_Store import CLI__Credential_Store


class Test_CLI__Credential_Store:

    def setup_method(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.store   = CLI__Credential_Store()
        self.store.setup(sg_send_dir=self.tmp_dir)
        self.passphrase = 'test-passphrase-for-creds'

    def teardown_method(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_add_and_get_vault_key(self):
        self.store.add_vault(self.passphrase, 'my-vault', 'abc123def456:s09yqbpj')
        result = self.store.get_vault_key(self.passphrase, 'my-vault')
        assert result == 'abc123def456:s09yqbpj'

    def test_list_vaults(self):
        self.store.add_vault(self.passphrase, 'beta-vault', 'key1:id1')
        self.store.add_vault(self.passphrase, 'alpha-vault', 'key2:id2')
        aliases = self.store.list_vaults(self.passphrase)
        assert aliases == ['alpha-vault', 'beta-vault']

    def test_remove_vault(self):
        self.store.add_vault(self.passphrase, 'temp', 'key:id')
        assert self.store.remove_vault(self.passphrase, 'temp') is True
        assert self.store.get_vault_key(self.passphrase, 'temp') is None

    def test_remove_missing_vault(self):
        assert self.store.remove_vault(self.passphrase, 'nope') is False

    def test_resolve_vault_key__direct_key(self):
        result = self.store.resolve_vault_key('passphrase123:vaultid1')
        assert result == 'passphrase123:vaultid1'

    def test_resolve_vault_key__alias_lookup(self):
        self.store.add_vault(self.passphrase, 'deploy', 'mykey123:abcd1234')
        result = self.store.resolve_vault_key('deploy', passphrase=self.passphrase)
        assert result == 'mykey123:abcd1234'

    def test_resolve_vault_key__missing_alias_raises(self):
        with pytest.raises(RuntimeError, match='No vault key found'):
            self.store.resolve_vault_key('nonexistent', passphrase=self.passphrase)

    def test_touch_activity_writes_timestamp(self):
        self.store._touch_activity()
        lock_path = self.store._lock_state_path()
        assert os.path.isfile(lock_path)
        with open(lock_path, 'r') as f:
            state = json.load(f)
        assert 'last_activity' in state
        assert time.time() - state['last_activity'] < 5

    def test_auto_lock__recent_activity_passes(self):
        self.store._touch_activity()
        self.store._check_auto_lock()
        assert os.path.isfile(self.store._lock_state_path())

    def test_auto_lock__expired_activity_locks(self):
        lock_path = self.store._lock_state_path()
        state = {'last_activity': time.time() - 3600}
        os.makedirs(os.path.dirname(lock_path), exist_ok=True)
        with open(lock_path, 'w') as f:
            json.dump(state, f)
        self.store._check_auto_lock()
        assert not os.path.isfile(lock_path)

    def test_sg_send_dir_created(self):
        new_dir = os.path.join(self.tmp_dir, 'new-home')
        store   = CLI__Credential_Store()
        store.setup(sg_send_dir=new_dir)
        assert os.path.isdir(new_dir)

    def test_wrong_passphrase_fails(self):
        self.store.add_vault(self.passphrase, 'secret', 'key:id')
        with pytest.raises(Exception):
            self.store.get_vault_key('wrong-pass', 'secret')
