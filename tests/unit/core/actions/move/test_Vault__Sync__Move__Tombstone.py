import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '_helpers'))
from vault_test_env import Vault__Test_Env

from sgit_ai.core.Vault__Sync                   import Vault__Sync
from sgit_ai.core.actions.move.Vault__Sync__Move  import Vault__Sync__Move
from sgit_ai.crypto.Vault__Crypto               import Vault__Crypto
from sgit_ai.network.api.Vault__API__In_Memory  import Vault__API__In_Memory


class Test_Vault__Sync__Move__Tombstone:
    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_single_vault(files={'data.txt': 'content'})

    def setup_method(self):
        self.env = self._env.restore()

    def teardown_method(self):
        self.env.cleanup()

    def _old_vault_id(self):
        return self.env.crypto.derive_keys_from_vault_key(self.env.vault_key)['vault_id']

    def _old_write_key(self):
        return self.env.crypto.derive_keys_from_vault_key(self.env.vault_key)['write_key']

    def _move(self):
        Vault__Sync__Move(crypto=self.env.crypto, api=self.env.api).move(
            self.env.vault_dir, reason='tombstone-test')

    def test_old_vault_id_rejects_writes_after_move(self):
        old_id    = self._old_vault_id()
        write_key = self._old_write_key()
        self._move()
        with pytest.raises(RuntimeError, match='403'):
            self.env.api.write(old_id, 'bare/data/test', write_key, b'data')

    def test_old_vault_id_reads_return_not_found(self):
        old_id = self._old_vault_id()
        self._move()
        with pytest.raises(RuntimeError, match='[Nn]ot found|not_found|404'):
            self.env.api.read(old_id, 'bare/data/nonexistent')

    def test_in_memory_api_tombstone_behaviour(self):
        api = Vault__API__In_Memory()
        api.setup()
        crypto = Vault__Crypto()

        vault_key = 'tombstonetestpassphrase12:tstv0001'
        keys      = crypto.derive_keys_from_vault_key(vault_key)
        vault_id  = keys['vault_id']
        write_key = keys['write_key']

        api.write(vault_id, 'bare/data/obj-cas-imm-abc', write_key, b'test')
        assert api.read(vault_id, 'bare/data/obj-cas-imm-abc') == b'test'

        api.tombstone_vault(vault_id, write_key)
        assert api.is_tombstoned(vault_id)

        with pytest.raises(RuntimeError, match='403'):
            api.write(vault_id, 'bare/data/obj-cas-imm-new', write_key, b'new')

        with pytest.raises(RuntimeError):
            api.read(vault_id, 'bare/data/obj-cas-imm-abc')

        result2 = api.tombstone_vault(vault_id, write_key)
        assert result2['status'] == 'deleted'
        assert api.is_tombstoned(vault_id)

    def test_old_vault_push_fails_after_move(self):
        import shutil, tempfile
        old_key = self.env.vault_key
        self._move()

        old_snapshot_dir = tempfile.mkdtemp()
        try:
            old_id    = self.env.crypto.derive_keys_from_vault_key(old_key)['vault_id']
            write_key = self.env.crypto.derive_keys_from_vault_key(old_key)['write_key']
            assert self.env.api.is_tombstoned(old_id)
            with pytest.raises(RuntimeError, match='403'):
                self.env.api.write(old_id, 'bare/refs/test', write_key, b'data')
        finally:
            shutil.rmtree(old_snapshot_dir, ignore_errors=True)
