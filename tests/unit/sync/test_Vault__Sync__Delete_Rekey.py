"""Tests for Vault__API__In_Memory.delete_vault and Vault__Sync.delete_on_remote / rekey."""
import os

import pytest

from sgit_ai.network.api.Vault__API__In_Memory import Vault__API__In_Memory
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
        from sgit_ai.storage.Vault__Storage import Vault__Storage
        storage   = Vault__Storage()
        mode_path = storage.clone_mode_path(self.env.vault_dir)
        c         = self.sync._init_components(self.env.vault_dir)
        with open(mode_path, 'w') as f:
            json.dump({'mode': 'read-only', 'vault_id': c.vault_id, 'read_key': 'a' * 64}, f)
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
        from sgit_ai.storage.Vault__Storage import Vault__Storage
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
# Rekey step-methods (check / wipe / init / commit)
# ---------------------------------------------------------------------------

class Test_Vault__Sync__Rekey__Steps:

    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_single_vault(files={'doc.md': 'hello', 'sub/note.txt': 'sub'})

    def setup_method(self):
        self.env  = self._env.restore()
        self.sync = self.env.sync

    def teardown_method(self):
        self.env.cleanup()

    def test_rekey_check_returns_vault_info(self):
        info = self.sync.rekey_check(self.env.vault_dir)
        assert 'vault_id'   in info
        assert 'file_count' in info
        assert 'obj_count'  in info
        assert 'clean'      in info
        assert info['file_count'] >= 1
        assert info['obj_count']  >= 1

    def test_rekey_check_does_not_modify_vault(self):
        from sgit_ai.storage.Vault__Storage import Vault__Storage
        key_before = open(Vault__Storage().vault_key_path(self.env.vault_dir)).read()
        self.sync.rekey_check(self.env.vault_dir)
        key_after = open(Vault__Storage().vault_key_path(self.env.vault_dir)).read()
        assert key_before == key_after

    def test_rekey_wipe_removes_objects(self):
        result = self.sync.rekey_wipe(self.env.vault_dir)
        assert result['objects_removed'] >= 1
        from sgit_ai.storage.Vault__Storage import Vault__Storage
        assert not os.path.isdir(Vault__Storage().sg_vault_dir(self.env.vault_dir))

    def test_rekey_wipe_keeps_working_files(self):
        self.sync.rekey_wipe(self.env.vault_dir)
        assert os.path.isfile(os.path.join(self.env.vault_dir, 'doc.md'))

    def test_rekey_init_creates_new_key(self):
        self.sync.rekey_wipe(self.env.vault_dir)
        result = self.sync.rekey_init(self.env.vault_dir)
        assert 'vault_key' in result
        assert 'vault_id'  in result
        assert result['vault_key'] != self.env.vault_key

    def test_rekey_commit_re_encrypts_files(self):
        self.sync.rekey_wipe(self.env.vault_dir)
        self.sync.rekey_init(self.env.vault_dir)
        result = self.sync.rekey_commit(self.env.vault_dir)
        assert result['file_count'] >= 1
        status = self.sync.status(self.env.vault_dir)
        assert status['clean'] is True


# ---------------------------------------------------------------------------
# Rekey corner cases
# ---------------------------------------------------------------------------

class Test_Vault__Sync__Rekey__Corner_Cases:

    def _make_env(self, files):
        env_holder = Vault__Test_Env()
        env_holder.setup_single_vault(files=files)
        snap = env_holder.restore()
        return snap, snap.sync

    # --- content correctness ---

    def test_rekey_file_content_preserved(self):
        """Re-encryption must not corrupt file content."""
        payload = 'precise content check'
        env, sync = self._make_env({'note.txt': payload})
        sync.rekey(env.vault_dir)
        with open(os.path.join(env.vault_dir, 'note.txt')) as f:
            assert f.read() == payload
        env.cleanup()

    def test_rekey_binary_content_preserved(self):
        """Binary files must survive the wipe → init → commit cycle."""
        data = bytes(range(256))
        env, sync = self._make_env({'bin.dat': data})
        sync.rekey(env.vault_dir)
        with open(os.path.join(env.vault_dir, 'bin.dat'), 'rb') as f:
            assert f.read() == data
        env.cleanup()

    def test_rekey_subdirectory_files_committed(self):
        """Files in subdirectories must be re-encrypted (old code only checked top-level)."""
        env, sync = self._make_env({'a/b/deep.txt': 'deep content'})
        result = sync.rekey(env.vault_dir)
        assert result['commit_id'] is not None
        status = sync.status(env.vault_dir)
        assert status['clean'] is True
        env.cleanup()

    def test_rekey_check_counts_subdirectory_files(self):
        """rekey_check file_count must include files in subdirectories."""
        env, sync = self._make_env({'top.txt': 'a', 'sub/nested.txt': 'b'})
        info = sync.rekey_check(env.vault_dir)
        assert info['file_count'] >= 2
        env.cleanup()

    # --- empty vault ---

    def test_rekey_empty_vault_no_files(self):
        """rekey on a vault with no working files succeeds — empty tree commit."""
        env_holder = Vault__Test_Env()
        env_holder.setup_single_vault()        # no files
        env  = env_holder.restore()
        sync = env.sync
        result = sync.rekey(env.vault_dir)
        assert result['vault_key']
        assert result['vault_id']
        # empty vault gets an empty-tree commit (valid state, not an error)
        status = sync.status(env.vault_dir)
        assert status['clean'] is True
        env.cleanup()

    def test_rekey_commit_empty_directory_returns_zero(self):
        """rekey_commit on vault with no files creates an empty-tree commit."""
        env_holder = Vault__Test_Env()
        env_holder.setup_single_vault()
        env  = env_holder.restore()
        sync = env.sync
        sync.rekey_wipe(env.vault_dir)
        sync.rekey_init(env.vault_dir)
        result = sync.rekey_commit(env.vault_dir)
        assert result['file_count'] == 0
        # commit_id may be set (empty tree commit) or None; vault must be in clean state
        status = sync.status(env.vault_dir)
        assert status['clean'] is True
        env.cleanup()

    # --- wipe idempotency ---

    def test_rekey_wipe_on_already_wiped_is_safe(self):
        """rekey_wipe on a directory with no .sg_vault/ must not raise."""
        env, sync = self._make_env({'f.txt': 'x'})
        sync.rekey_wipe(env.vault_dir)
        result = sync.rekey_wipe(env.vault_dir)    # second wipe
        assert result['objects_removed'] == 0
        env.cleanup()

    # --- double rekey ---

    def test_double_rekey_produces_different_keys(self):
        """Running rekey twice gives two independent vault keys."""
        env, sync = self._make_env({'f.txt': 'data'})
        r1 = sync.rekey(env.vault_dir)
        r2 = sync.rekey(env.vault_dir)
        assert r1['vault_key'] != r2['vault_key']
        assert r1['vault_id']  != r2['vault_id']
        env.cleanup()

    def test_double_rekey_vault_still_clean(self):
        env, sync = self._make_env({'f.txt': 'data'})
        sync.rekey(env.vault_dir)
        sync.rekey(env.vault_dir)
        assert sync.status(env.vault_dir)['clean'] is True
        env.cleanup()

    # --- vault stays functional after rekey ---

    def test_rekey_then_commit_new_file_works(self):
        """After rekey the vault is fully usable — new commits succeed."""
        env, sync = self._make_env({'original.txt': 'original'})
        sync.rekey(env.vault_dir)
        new_file = os.path.join(env.vault_dir, 'added.txt')
        with open(new_file, 'w') as f:
            f.write('added after rekey')
        result = sync.commit(env.vault_dir, message='post-rekey commit')
        assert result['files_changed'] >= 1
        env.cleanup()

    def test_rekey_then_push_works(self):
        """After rekey the vault can be pushed (acts as a first push)."""
        env, sync = self._make_env({'doc.md': 'content'})
        sync.rekey(env.vault_dir)
        push_result = sync.push(env.vault_dir)
        assert push_result['status'] in ('pushed', 'up_to_date', 'resynced')
        env.cleanup()

    def test_rekey_then_status_lists_correct_files(self):
        """Status after rekey should show all original files, clean."""
        env, sync = self._make_env({'a.txt': 'a', 'b/c.txt': 'c'})
        sync.rekey(env.vault_dir)
        status = sync.status(env.vault_dir)
        assert status['clean'] is True
        assert not status.get('untracked')
        assert not status.get('modified')
        env.cleanup()

    # --- multiple files, exact count ---

    def test_rekey_commit_count_matches_file_count(self):
        """files_changed in rekey_commit should equal actual file count."""
        files = {'a.txt': 'a', 'b.txt': 'b', 'sub/c.txt': 'c'}
        env, sync = self._make_env(files)
        sync.rekey_wipe(env.vault_dir)
        sync.rekey_init(env.vault_dir)
        result = sync.rekey_commit(env.vault_dir)
        assert result['file_count'] == len(files)
        env.cleanup()


# ---------------------------------------------------------------------------
# CLI parsers
# ---------------------------------------------------------------------------

class Test_CLI__Delete_Rekey__Parsers:

    def test_delete_on_remote_parser(self):
        from sgit_ai.cli.CLI__Main import CLI__Main
        cli  = CLI__Main()
        args = cli.build_parser().parse_args(['vault', 'delete-on-remote'])
        assert args.directory == '.'
        assert args.yes is False
        assert args.json is False

    def test_delete_on_remote_yes_flag(self):
        from sgit_ai.cli.CLI__Main import CLI__Main
        cli  = CLI__Main()
        args = cli.build_parser().parse_args(['vault', 'delete-on-remote', '--yes'])
        assert args.yes is True

    def test_rekey_wizard_parser(self):
        from sgit_ai.cli.CLI__Main import CLI__Main
        cli  = CLI__Main()
        args = cli.build_parser().parse_args(['vault', 'rekey'])
        assert args.directory == '.'
        assert args.yes is False
        assert args.new_key is None
        assert args.rekey_subcommand is None

    def test_rekey_new_key_flag(self):
        from sgit_ai.cli.CLI__Main import CLI__Main
        cli  = CLI__Main()
        args = cli.build_parser().parse_args(['vault', 'rekey', '--new-key', 'abc:def'])
        assert args.new_key == 'abc:def'

    def test_rekey_check_subcommand(self):
        from sgit_ai.cli.CLI__Main import CLI__Main
        cli  = CLI__Main()
        args = cli.build_parser().parse_args(['vault', 'rekey', 'check'])
        assert args.rekey_subcommand == 'check'
        assert args.directory == '.'

    def test_rekey_wipe_subcommand(self):
        from sgit_ai.cli.CLI__Main import CLI__Main
        cli  = CLI__Main()
        args = cli.build_parser().parse_args(['vault', 'rekey', 'wipe', '--yes'])
        assert args.rekey_subcommand == 'wipe'
        assert args.yes is True

    def test_rekey_init_subcommand(self):
        from sgit_ai.cli.CLI__Main import CLI__Main
        cli  = CLI__Main()
        args = cli.build_parser().parse_args(['vault', 'rekey', 'init', '--new-key', 'k:id'])
        assert args.rekey_subcommand == 'init'
        assert args.new_key == 'k:id'

    def test_rekey_commit_subcommand(self):
        from sgit_ai.cli.CLI__Main import CLI__Main
        cli  = CLI__Main()
        args = cli.build_parser().parse_args(['vault', 'rekey', 'commit', '/tmp/v'])
        assert args.rekey_subcommand == 'commit'
        assert args.directory == '/tmp/v'
