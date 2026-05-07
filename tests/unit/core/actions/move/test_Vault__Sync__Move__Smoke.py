"""Smoke / happy-path tests for Vault__Sync__Move — Brief 03 §3a."""
import json
import os
import shutil
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '_helpers'))
from vault_test_env import Vault__Test_Env

from sgit_ai.core.Vault__Sync                  import Vault__Sync
from sgit_ai.core.actions.move.Vault__Sync__Move import Vault__Sync__Move
from sgit_ai.crypto.Vault__Crypto              import Vault__Crypto
from sgit_ai.network.api.Vault__API__In_Memory import Vault__API__In_Memory


class Test_Vault__Sync__Move__Smoke:
    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_single_vault(files={
            'readme.txt': 'readme content\n',
            'src/main.py': 'print("hello")\n',
        })

    def setup_method(self):
        self.env = self._env.restore()

    def teardown_method(self):
        self.env.cleanup()

    def _mover(self):
        return Vault__Sync__Move(crypto=self.env.crypto, api=self.env.api)

    def _move(self, **kwargs):
        return self._mover().move(self.env.vault_dir, reason='smoke-test', **kwargs)

    def _new_vault_key(self):
        return open(os.path.join(self.env.vault_dir, '.sg_vault', 'local', 'vault_key')).read().strip()

    def _old_vault_id(self):
        return self.env.crypto.derive_keys_from_vault_key(self.env.vault_key)['vault_id']

    # 1. move() returns a result without raising
    def test_move_returns_result(self):
        result = self._move()
        assert result is not None

    # 2. vault_id changes after move
    def test_vault_id_changes(self):
        old_id = self._old_vault_id()
        self._move()
        new_id = self.env.crypto.derive_keys_from_vault_key(self._new_vault_key())['vault_id']
        assert new_id != old_id

    # 3. vault_key changes after move (auto-generated)
    def test_vault_key_changes(self):
        old_key = self.env.vault_key
        self._move()
        assert self._new_vault_key() != old_key

    # 4. explicit new_vault_key is honoured
    def test_explicit_new_vault_key_used(self):
        explicit = 'explicitpassphrase123456:expl0001'
        self._move(new_vault_key=explicit)
        assert self._new_vault_key() == explicit

    # 5. old vault_id is tombstoned after move
    def test_old_vault_tombstoned(self):
        old_id = self._old_vault_id()
        self._move()
        assert self.env.api.is_tombstoned(old_id)

    # 6. .sg_vault_new is absent after successful move
    def test_no_sg_vault_new_after_move(self):
        self._move()
        assert not os.path.exists(os.path.join(self.env.vault_dir, '.sg_vault_new'))

    # 7. clone from new vault succeeds and has correct files
    def test_clone_from_new_vault(self):
        self._move()
        clone_dir = tempfile.mkdtemp()
        try:
            Vault__Sync(crypto=self.env.crypto, api=self.env.api).clone(
                self._new_vault_key(), clone_dir)
            assert os.path.isfile(os.path.join(clone_dir, 'readme.txt'))
            assert open(os.path.join(clone_dir, 'readme.txt')).read() == 'readme content\n'
            assert os.path.isfile(os.path.join(clone_dir, 'src', 'main.py'))
        finally:
            shutil.rmtree(clone_dir, ignore_errors=True)

    # 8. commit on moved vault succeeds
    def test_commit_after_move(self):
        self._move()
        with open(os.path.join(self.env.vault_dir, 'new_file.txt'), 'w') as fh:
            fh.write('new content')
        result = Vault__Sync(crypto=self.env.crypto, api=self.env.api).commit(
            self.env.vault_dir, message='post-move commit')
        assert result.get('commit_id')

    # 9. push after move succeeds
    def test_push_after_move(self):
        self._move()
        with open(os.path.join(self.env.vault_dir, 'extra.txt'), 'w') as fh:
            fh.write('extra')
        sync = Vault__Sync(crypto=self.env.crypto, api=self.env.api)
        sync.commit(self.env.vault_dir, message='extra commit')
        result = sync.push(self.env.vault_dir)
        assert result is not None

    # 10. status on moved vault works (clean)
    def test_status_after_move(self):
        self._move()
        sync   = Vault__Sync(crypto=self.env.crypto, api=self.env.api)
        status = sync.status(self.env.vault_dir)
        assert status is not None

    # 11. dry_run performs no state changes
    def test_dry_run_no_state_change(self):
        old_id = self._old_vault_id()
        old_key = self.env.vault_key
        self._move(dry_run=True)
        assert self._new_vault_key() == old_key
        assert not self.env.api.is_tombstoned(old_id)
        assert not os.path.exists(os.path.join(self.env.vault_dir, '.sg_vault_new'))

    # 12. move with explicit target_api_url (same in-memory API)
    def test_move_with_target_api_url(self):
        from sgit_ai.network.api.Vault__API import DEFAULT_BASE_URL
        result = self._mover().move(
            self.env.vault_dir,
            reason='target-url-test',
            target_api_url=DEFAULT_BASE_URL,
        )
        assert result is not None
        clone_dir = tempfile.mkdtemp()
        try:
            Vault__Sync(crypto=self.env.crypto, api=self.env.api).clone(
                self._new_vault_key(), clone_dir)
            assert os.path.isfile(os.path.join(clone_dir, 'readme.txt'))
        finally:
            shutil.rmtree(clone_dir, ignore_errors=True)

    # 13. config.json reflects new vault_id
    def test_config_reflects_new_vault_id(self):
        self._move()
        cfg_path = os.path.join(self.env.vault_dir, '.sg_vault', 'local', 'config.json')
        with open(cfg_path) as f:
            cfg = json.load(f)
        expected = self.env.crypto.derive_keys_from_vault_key(self._new_vault_key())['vault_id']
        assert cfg['vault_id'] == expected

    # 14. reason appears in move-history
    def test_reason_appears_in_history(self):
        self._mover().move(self.env.vault_dir, reason='my-custom-reason')
        hist = json.load(open(
            os.path.join(self.env.vault_dir, '.sg_vault', 'local', 'move-history.json')))
        assert hist['moves'][-1].get('reason') == 'my-custom-reason'

    # 15. old vault cannot be written to after move (tombstone enforced)
    def test_old_vault_write_rejected_after_move(self):
        old_id   = self._old_vault_id()
        old_keys = self.env.crypto.derive_keys_from_vault_key(self.env.vault_key)
        write_key = old_keys['write_key']
        self._move()
        with pytest.raises(RuntimeError, match='403|tombstoned|deleted'):
            self.env.api.write(old_id, 'bare/data/test', b'data', write_key)
