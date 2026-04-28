"""Tests for Vault__API__In_Memory.delete_vault and Vault__Sync.delete_on_remote / rekey."""
import os

import pytest

from sgit_ai.api.Vault__API__In_Memory import Vault__API__In_Memory
from tests.unit.sync.vault_test_env    import Vault__Test_Env


# ---------------------------------------------------------------------------
# In-memory API: delete_vault
# ---------------------------------------------------------------------------

class Test_Vault__API__In_Memory__Delete_Vault:

    def setup_method(self):
        self.api = Vault__API__In_Memory()
        self.api.setup()

    def test_delete_vault_returns_deleted_status(self):
        self.api._store['v1/bare/data/blob1'] = b'data'
        self.api._store['v1/bare/refs/ref1']  = b'ref'
        result = self.api.delete_vault('v1', 'write_key_hex')
        assert result['status']    == 'deleted'
        assert result['vault_id']  == 'v1'
        assert result['files_deleted'] == 2

    def test_delete_vault_clears_all_vault_keys(self):
        self.api._store['v1/bare/data/blob1'] = b'a'
        self.api._store['v1/bare/refs/ref1']  = b'b'
        self.api._store['v2/bare/data/blob1'] = b'c'   # different vault — must survive
        self.api.delete_vault('v1', 'key')
        assert 'v1/bare/data/blob1' not in self.api._store
        assert 'v1/bare/refs/ref1'  not in self.api._store
        assert 'v2/bare/data/blob1' in self.api._store  # untouched

    def test_delete_vault_already_absent_returns_zero(self):
        result = self.api.delete_vault('nonexistent', 'key')
        assert result['status']        == 'deleted'
        assert result['files_deleted'] == 0

    def test_delete_vault_idempotent(self):
        self.api._store['v1/f'] = b'x'
        self.api.delete_vault('v1', 'k')
        result = self.api.delete_vault('v1', 'k')   # second call
        assert result['files_deleted'] == 0


# ---------------------------------------------------------------------------
# Vault__Sync: delete_on_remote
# ---------------------------------------------------------------------------

class Test_Vault__Sync__Delete_On_Remote:

    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_single_vault(files={'readme.md': 'content'})

    def setup_method(self):
        self.env  = self._env.restore()
        self.sync = self.env.sync

    def teardown_method(self):
        self.env.cleanup()

    def test_delete_on_remote_returns_deleted(self):
        result = self.sync.delete_on_remote(self.env.vault_dir)
        assert result['status'] == 'deleted'

    def test_delete_on_remote_clears_server_files(self):
        vault_id = self.sync._init_components(self.env.vault_dir).vault_id
        self.sync.delete_on_remote(self.env.vault_dir)
        remaining = self.env.api.list_files(vault_id, 'bare/')
        assert remaining == []

    def test_delete_on_remote_leaves_local_intact(self):
        self.sync.delete_on_remote(self.env.vault_dir)
        sg_vault = os.path.join(self.env.vault_dir, '.sg_vault')
        assert os.path.isdir(sg_vault)
        vault_key_path = os.path.join(sg_vault, 'local', 'vault_key')
        assert os.path.isfile(vault_key_path)

    def test_delete_on_remote_idempotent(self):
        self.sync.delete_on_remote(self.env.vault_dir)
        result = self.sync.delete_on_remote(self.env.vault_dir)
        assert result['files_deleted'] == 0

    def test_delete_on_remote_read_only_raises(self):
        import json
        from sgit_ai.sync.Vault__Storage import Vault__Storage
        storage   = Vault__Storage()
        mode_path = storage.clone_mode_path(self.env.vault_dir)
        c         = self.sync._init_components(self.env.vault_dir)
        with open(mode_path, 'w') as f:
            json.dump({'mode': 'read-only', 'vault_id': c.vault_id, 'read_key': 'aa'}, f)
        with pytest.raises(RuntimeError, match='read-only'):
            self.sync.delete_on_remote(self.env.vault_dir)


# ---------------------------------------------------------------------------
# Vault__Sync: rekey
# ---------------------------------------------------------------------------

class Test_Vault__Sync__Rekey:

    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_single_vault(files={'doc.md': 'hello', 'img/logo.png': 'png'})

    def setup_method(self):
        self.env  = self._env.restore()
        self.sync = self.env.sync

    def teardown_method(self):
        self.env.cleanup()

    def test_rekey_returns_new_vault_key(self):
        result = self.sync.rekey(self.env.vault_dir)
        assert 'vault_key' in result
        assert result['vault_key'] != self.env.vault_key

    def test_rekey_changes_vault_id(self):
        old_id = self.sync._init_components(self.env.vault_dir).vault_id
        result = self.sync.rekey(self.env.vault_dir)
        assert result['vault_id'] != old_id

    def test_rekey_working_files_preserved(self):
        self.sync.rekey(self.env.vault_dir)
        assert os.path.isfile(os.path.join(self.env.vault_dir, 'doc.md'))

    def test_rekey_local_vault_key_updated(self):
        result = self.sync.rekey(self.env.vault_dir)
        from sgit_ai.sync.Vault__Storage import Vault__Storage
        key_path = Vault__Storage().vault_key_path(self.env.vault_dir)
        with open(key_path) as f:
            saved_key = f.read().strip()
        assert saved_key == result['vault_key']

    def test_rekey_vault_usable_after_rekey(self):
        self.sync.rekey(self.env.vault_dir)
        status = self.sync.status(self.env.vault_dir)
        assert status['clean'] is True

    def test_rekey_custom_key(self):
        new_key = 'aaaaaaaaaaaaaaaaaaaaaaaa:bbbbbbbb'
        result  = self.sync.rekey(self.env.vault_dir, new_vault_key=new_key)
        assert result['vault_key'] == new_key


# ---------------------------------------------------------------------------
# CLI parsers
# ---------------------------------------------------------------------------

class Test_CLI__Delete_Rekey__Parsers:

    def test_delete_on_remote_parser(self):
        from sgit_ai.cli.CLI__Main import CLI__Main
        cli  = CLI__Main()
        args = cli.build_parser().parse_args(['delete-on-remote'])
        assert args.directory == '.'
        assert args.yes is False
        assert args.json is False

    def test_delete_on_remote_yes_flag(self):
        from sgit_ai.cli.CLI__Main import CLI__Main
        cli  = CLI__Main()
        args = cli.build_parser().parse_args(['delete-on-remote', '--yes'])
        assert args.yes is True

    def test_rekey_parser(self):
        from sgit_ai.cli.CLI__Main import CLI__Main
        cli  = CLI__Main()
        args = cli.build_parser().parse_args(['rekey'])
        assert args.directory == '.'
        assert args.yes is False
        assert args.new_key is None

    def test_rekey_new_key_flag(self):
        from sgit_ai.cli.CLI__Main import CLI__Main
        cli  = CLI__Main()
        args = cli.build_parser().parse_args(['rekey', '--new-key', 'abc:def'])
        assert args.new_key == 'abc:def'
