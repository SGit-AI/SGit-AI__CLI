"""Unit tests for CLI__Vault commands not yet covered: uninit, branches,
merge_abort, remote_add/remove/list, clone, init, vault_show_key, info.

Strategy:
- Commands that call sync methods internally: monkeypatch the specific
  Vault__Sync method to return a canned result.
- Commands that use create_sync: use the _make_cli(snap) helper.
- Commands that are purely local (init, vault_show_key): use real temp vaults.
"""
import os
import sys
import types as _types

import pytest

from sgit_ai.cli.CLI__Vault          import CLI__Vault
from sgit_ai.cli.CLI__Token_Store    import CLI__Token_Store
from sgit_ai.cli.CLI__Credential_Store import CLI__Credential_Store
from sgit_ai.sync.Vault__Sync        import Vault__Sync
from sgit_ai.crypto.Vault__Crypto    import Vault__Crypto
from sgit_ai.api.Vault__API__In_Memory import Vault__API__In_Memory
from tests.unit.sync.vault_test_env  import Vault__Test_Env


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _make_cli(snap=None) -> CLI__Vault:
    """Build a CLI__Vault; if snap provided, override create_sync with in-memory API."""
    cli = CLI__Vault(token_store=CLI__Token_Store(), credential_store=CLI__Credential_Store())
    if snap:
        api, crypto = snap.api, snap.crypto
        def _create_sync(self, base_url=None, access_token=None):
            return Vault__Sync(crypto=crypto, api=api)
        cli.create_sync = _types.MethodType(_create_sync, cli)
    return cli


class _Args:
    """Minimal args namespace."""
    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)


# ---------------------------------------------------------------------------
# cmd_uninit
# ---------------------------------------------------------------------------

class Test_CLI__Vault__Uninit:

    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_single_vault(files={'data.txt': 'content'})

    @classmethod
    def teardown_class(cls):
        if cls._env:
            cls._env.cleanup_snapshot()

    def setup_method(self):
        self.snap  = self._env.restore()
        self.vault = self.snap.vault_dir

    def teardown_method(self):
        self.snap.cleanup()

    def test_cmd_uninit_prints_removing(self, monkeypatch, capsys):
        monkeypatch.setattr(Vault__Sync, 'uninit', lambda self, d: dict(
            backup_path   = '/tmp/fake.vault__v__123.zip',
            backup_size   = 1024,
            working_files = 3,
        ))
        cli = _make_cli()
        cli.cmd_uninit(_Args(directory=self.vault))
        out = capsys.readouterr().out
        assert 'Removing' in out or 'backup' in out.lower()

    def test_cmd_uninit_prints_vault_removed(self, monkeypatch, capsys):
        monkeypatch.setattr(Vault__Sync, 'uninit', lambda self, d: dict(
            backup_path   = '/tmp/fake.vault__v__123.zip',
            backup_size   = 2048,
            working_files = 1,
        ))
        cli = _make_cli()
        cli.cmd_uninit(_Args(directory=self.vault))
        assert 'Vault removed' in capsys.readouterr().out

    def test_cmd_uninit_real(self, tmp_path):
        """Actually uninit a real vault — no monkeypatching."""
        import shutil
        vault_dir = str(tmp_path / 'vault')
        shutil.copytree(self.vault, vault_dir)
        cli = _make_cli()
        cli.cmd_uninit(_Args(directory=vault_dir))
        # .sg_vault/ should be gone after uninit
        assert not os.path.isdir(os.path.join(vault_dir, '.sg_vault'))


# ---------------------------------------------------------------------------
# cmd_branches
# ---------------------------------------------------------------------------

class Test_CLI__Vault__Branches:

    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_single_vault(files={'f.txt': 'hi'})

    @classmethod
    def teardown_class(cls):
        if cls._env:
            cls._env.cleanup_snapshot()

    def setup_method(self):
        self.snap  = self._env.restore()
        self.vault = self.snap.vault_dir

    def teardown_method(self):
        self.snap.cleanup()

    def test_cmd_branches_no_branches(self, monkeypatch, capsys):
        monkeypatch.setattr(Vault__Sync, 'branches', lambda self, d: {'branches': []})
        cli = _make_cli()
        cli.cmd_branches(_Args(directory=self.vault))
        assert 'No branches' in capsys.readouterr().out

    def test_cmd_branches_shows_branch(self, monkeypatch, capsys):
        monkeypatch.setattr(Vault__Sync, 'branches', lambda self, d: {
            'branches': [dict(is_current=True, name='current',
                              branch_type='named', head_commit='abc123456789')]
        })
        cli = _make_cli()
        cli.cmd_branches(_Args(directory=self.vault))
        out = capsys.readouterr().out
        assert 'current' in out
        assert '*' in out

    def test_cmd_branches_non_current_no_star(self, monkeypatch, capsys):
        monkeypatch.setattr(Vault__Sync, 'branches', lambda self, d: {
            'branches': [dict(is_current=False, name='feature',
                              branch_type='clone', head_commit='deadbeef1234')]
        })
        cli = _make_cli()
        cli.cmd_branches(_Args(directory=self.vault))
        out = capsys.readouterr().out
        assert 'feature' in out
        assert '* ' not in out


# ---------------------------------------------------------------------------
# cmd_merge_abort
# ---------------------------------------------------------------------------

class Test_CLI__Vault__MergeAbort:

    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_single_vault(files={'f.txt': 'data'})

    @classmethod
    def teardown_class(cls):
        if cls._env:
            cls._env.cleanup_snapshot()

    def setup_method(self):
        self.snap  = self._env.restore()
        self.vault = self.snap.vault_dir

    def teardown_method(self):
        self.snap.cleanup()

    def test_cmd_merge_abort_prints_restored(self, monkeypatch, capsys):
        monkeypatch.setattr(Vault__Sync, 'merge_abort', lambda self, d: {
            'restored_commit': 'obj-cas-imm-abc123',
            'removed_files': [],
        })
        cli = _make_cli()
        cli.cmd_merge_abort(_Args(directory=self.vault))
        assert 'aborted' in capsys.readouterr().out.lower()

    def test_cmd_merge_abort_prints_removed_files(self, monkeypatch, capsys):
        monkeypatch.setattr(Vault__Sync, 'merge_abort', lambda self, d: {
            'restored_commit': 'obj-cas-imm-abc123',
            'removed_files': ['conflict.txt', 'other.txt'],
        })
        cli = _make_cli()
        cli.cmd_merge_abort(_Args(directory=self.vault))
        out = capsys.readouterr().out
        assert 'conflict.txt' in out


# ---------------------------------------------------------------------------
# cmd_remote_add / cmd_remote_remove / cmd_remote_list
# ---------------------------------------------------------------------------

class Test_CLI__Vault__Remote:

    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_single_vault(files={'f.txt': 'x'})

    @classmethod
    def teardown_class(cls):
        if cls._env:
            cls._env.cleanup_snapshot()

    def setup_method(self):
        self.snap  = self._env.restore()
        self.vault = self.snap.vault_dir

    def teardown_method(self):
        self.snap.cleanup()

    def test_cmd_remote_add_prints_confirmation(self, monkeypatch, capsys):
        monkeypatch.setattr(Vault__Sync, 'remote_add',
                            lambda self, d, name, url, vid: {'name': name, 'url': url, 'vault_id': vid})
        cli = _make_cli()
        cli.cmd_remote_add(_Args(directory=self.vault, name='origin',
                                 url='https://example.com', remote_vault_id='vid-abc'))
        assert 'origin' in capsys.readouterr().out

    def test_cmd_remote_remove_prints_confirmation(self, monkeypatch, capsys):
        monkeypatch.setattr(Vault__Sync, 'remote_remove',
                            lambda self, d, name: {'removed': name})
        cli = _make_cli()
        cli.cmd_remote_remove(_Args(directory=self.vault, name='origin'))
        assert 'origin' in capsys.readouterr().out

    def test_cmd_remote_list_no_remotes(self, monkeypatch, capsys):
        monkeypatch.setattr(Vault__Sync, 'remote_list',
                            lambda self, d: {'remotes': []})
        cli = _make_cli()
        cli.cmd_remote_list(_Args(directory=self.vault))
        assert 'No remotes' in capsys.readouterr().out

    def test_cmd_remote_list_shows_remote(self, monkeypatch, capsys):
        monkeypatch.setattr(Vault__Sync, 'remote_list',
                            lambda self, d: {'remotes': [
                                {'name': 'origin', 'url': 'https://ex.com', 'vault_id': 'vid'}
                            ]})
        cli = _make_cli()
        cli.cmd_remote_list(_Args(directory=self.vault))
        out = capsys.readouterr().out
        assert 'origin' in out
        assert 'https://ex.com' in out


# ---------------------------------------------------------------------------
# cmd_vault_show_key
# ---------------------------------------------------------------------------

class Test_CLI__Vault__ShowKey:

    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_single_vault(files={'f.txt': 'hi'})

    @classmethod
    def teardown_class(cls):
        if cls._env:
            cls._env.cleanup_snapshot()

    def setup_method(self):
        self.snap  = self._env.restore()
        self.vault = self.snap.vault_dir

    def teardown_method(self):
        self.snap.cleanup()

    def test_cmd_vault_show_key_prints_key(self, capsys):
        cli = _make_cli()
        cli.cmd_vault_show_key(_Args(directory=self.vault))
        out = capsys.readouterr().out
        assert 'Vault key:' in out
        assert self.snap.vault_key in out

    def test_cmd_vault_show_key_prints_vault_id(self, capsys):
        cli = _make_cli()
        cli.cmd_vault_show_key(_Args(directory=self.vault))
        assert 'Vault ID:' in capsys.readouterr().out

    def test_cmd_vault_show_key_no_key_exits(self, tmp_path, capsys):
        """No vault key in directory → sys.exit(1)."""
        empty_dir = str(tmp_path / 'empty')
        os.makedirs(empty_dir)
        cli = _make_cli()
        with pytest.raises(SystemExit) as exc_info:
            cli.cmd_vault_show_key(_Args(directory=empty_dir))
        assert exc_info.value.code == 1


# ---------------------------------------------------------------------------
# cmd_info
# ---------------------------------------------------------------------------

class Test_CLI__Vault__Info:

    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_single_vault(files={'readme.txt': 'hello'})

    @classmethod
    def teardown_class(cls):
        if cls._env:
            cls._env.cleanup_snapshot()

    def setup_method(self):
        self.snap  = self._env.restore()
        self.vault = self.snap.vault_dir

    def teardown_method(self):
        self.snap.cleanup()

    FAKE_STATUS = dict(clone_branch_id='branch-clone-abc', named_branch_id='current',
                       clone_head='obj-cas-abc123', push_status='up_to_date',
                       ahead=0, behind=0)

    def test_cmd_info_prints_vault_id(self, monkeypatch, capsys):
        cli = _make_cli(self.snap)
        monkeypatch.setattr(Vault__Sync, 'status', lambda self, d: Test_CLI__Vault__Info.FAKE_STATUS)
        cli.cmd_info(_Args(directory=self.vault, base_url=None))
        assert 'Vault ID:' in capsys.readouterr().out

    def test_cmd_info_no_vault_key_exits(self, tmp_path, capsys):
        empty = str(tmp_path / 'empty')
        os.makedirs(empty)
        cli = _make_cli()
        with pytest.raises(SystemExit) as exc_info:
            cli.cmd_info(_Args(directory=empty, base_url=None))
        assert exc_info.value.code == 1

    def test_cmd_info_prints_version(self, monkeypatch, capsys):
        cli = _make_cli(self.snap)
        monkeypatch.setattr(Vault__Sync, 'status', lambda self, d: Test_CLI__Vault__Info.FAKE_STATUS)
        cli.cmd_info(_Args(directory=self.vault, base_url=None))
        assert 'Version:' in capsys.readouterr().out

    def test_cmd_info_prints_passphrase(self, monkeypatch, capsys):
        """cmd_info always shows Passphrase: line."""
        cli = _make_cli(self.snap)
        monkeypatch.setattr(Vault__Sync, 'status', lambda self, d: Test_CLI__Vault__Info.FAKE_STATUS)
        cli.cmd_info(_Args(directory=self.vault, base_url=None))
        assert 'Passphrase:' in capsys.readouterr().out

    def test_cmd_info_simple_token_vault_shows_both_formats(self, monkeypatch, capsys, tmp_path):
        """For simple token vaults, cmd_info shows plain token AND combined token:vault_id."""
        import shutil
        from sgit_ai.sync.Vault__Storage import SG_VAULT_DIR

        token     = 'coral-equal-1234'
        vault_dir = str(tmp_path / 'vault')

        sync = Vault__Sync(crypto=Vault__Crypto(), api=Vault__API__In_Memory().setup())
        sync.init(vault_dir, token=token)

        cli = _make_cli()
        monkeypatch.setattr(Vault__Sync, 'status', lambda self, d: Test_CLI__Vault__Info.FAKE_STATUS)
        cli.cmd_info(_Args(directory=vault_dir, base_url=None))
        out = capsys.readouterr().out

        assert 'Passphrase:  coral-equal-1234'     in out   # plain token
        assert 'c4958581e0ab'                       in out   # hashed vault_id
        assert 'coral-equal-1234:c4958581e0ab'      in out   # combined key
        assert 'either form works'                  in out   # hint text


# ---------------------------------------------------------------------------
# cmd_clone (via create_sync override)
# ---------------------------------------------------------------------------

class Test_CLI__Vault__Clone:

    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_single_vault(files={'hello.txt': 'hello'})

    @classmethod
    def teardown_class(cls):
        if cls._env:
            cls._env.cleanup_snapshot()

    def setup_method(self):
        self.snap  = self._env.restore()

    def teardown_method(self):
        self.snap.cleanup()

    def test_cmd_clone_prints_cloned_into(self, monkeypatch, capsys, tmp_path):
        target = str(tmp_path / 'cloned')
        clone_result = dict(directory=target, vault_id='vid-abc',
                            share_token=None, branch_id='current', commit_id='abc123')
        monkeypatch.setattr(Vault__Sync, 'clone',
                            lambda self, vk, d, on_progress=None: clone_result)
        cli = _make_cli(self.snap)
        args = _Args(vault_key=self.snap.vault_key, directory=target,
                     token=None, base_url=None)
        cli.cmd_clone(args)
        out = capsys.readouterr().out
        assert 'Cloned into' in out

    def test_cmd_clone_auto_directory_from_vault_key(self, monkeypatch, capsys, tmp_path):
        """If directory is falsy, it is derived from the vault_key."""
        vault_key = self.snap.vault_key
        clone_result = dict(directory=vault_key, vault_id='vid-abc',
                            share_token=None, branch_id='current', commit_id=None)
        monkeypatch.setattr(Vault__Sync, 'clone',
                            lambda self, vk, d, on_progress=None: clone_result)
        cli = _make_cli(self.snap)
        args = _Args(vault_key=vault_key, directory='', token=None, base_url=None)
        cli.cmd_clone(args)
        assert 'Cloned into' in capsys.readouterr().out

    def test_cmd_clone_with_share_token_result(self, monkeypatch, capsys, tmp_path):
        target = str(tmp_path / 'shared')
        clone_result = dict(directory=target, vault_id='vid-abc',
                            share_token='cold-idle-7311', branch_id='current',
                            commit_id='abc', file_count=3)
        monkeypatch.setattr(Vault__Sync, 'clone',
                            lambda self, vk, d, on_progress=None: clone_result)
        cli = _make_cli(self.snap)
        args = _Args(vault_key='cold-idle-7311', directory=target,
                     token=None, base_url=None)
        cli.cmd_clone(args)
        out = capsys.readouterr().out
        assert 'cold-idle-7311' in out


# ---------------------------------------------------------------------------
# cmd_init — purely local, no API
# ---------------------------------------------------------------------------

class Test_CLI__Vault__Init:

    def test_cmd_init_creates_vault(self, capsys, tmp_path):
        """cmd_init on a fresh directory should create a vault."""
        vault_dir = str(tmp_path / 'new_vault')
        os.makedirs(vault_dir)
        cli = CLI__Vault(token_store=CLI__Token_Store(), credential_store=CLI__Credential_Store())
        cli.cmd_init(_Args(directory=vault_dir, vault_key=None,
                           restore=False, existing=False, token=None))
        out = capsys.readouterr().out
        assert 'Vault created' in out
        assert os.path.isdir(os.path.join(vault_dir, '.sg_vault'))

    def test_cmd_init_prints_vault_key(self, capsys, tmp_path):
        vault_dir = str(tmp_path / 'vault2')
        os.makedirs(vault_dir)
        cli = CLI__Vault(token_store=CLI__Token_Store(), credential_store=CLI__Credential_Store())
        cli.cmd_init(_Args(directory=vault_dir, vault_key=None,
                           restore=False, existing=False, token=None))
        assert 'Vault key:' in capsys.readouterr().out

    def test_cmd_init_no_restore_file_exits(self, monkeypatch, capsys, tmp_path):
        """--restore with no backup file → sys.exit(1)."""
        empty = str(tmp_path / 'empty')
        os.makedirs(empty)
        monkeypatch.setattr('sgit_ai.cli.CLI__Input.CLI__Input.prompt', lambda self, msg: None)
        cli = CLI__Vault(token_store=CLI__Token_Store(), credential_store=CLI__Credential_Store())
        with pytest.raises(SystemExit) as exc_info:
            cli.cmd_init(_Args(directory=empty, vault_key=None,
                               restore=True, existing=False, token=None))
        assert exc_info.value.code == 1

    def test_cmd_init_existing_dir_aborts_on_no(self, monkeypatch, capsys, tmp_path):
        """Non-empty directory + CLI__Input returns None → aborts without creating vault."""
        vault_dir = str(tmp_path / 'nonempty')
        os.makedirs(vault_dir)
        with open(os.path.join(vault_dir, 'existing.txt'), 'w') as f:
            f.write('data')
        monkeypatch.setattr('sgit_ai.cli.CLI__Input.CLI__Input.prompt', lambda self, msg: None)
        cli = CLI__Vault(token_store=CLI__Token_Store(), credential_store=CLI__Credential_Store())
        cli.cmd_init(_Args(directory=vault_dir, vault_key=None,
                           restore=False, existing=False, token=None))
        out = capsys.readouterr().out
        assert 'cancelled' in out.lower()
        assert not os.path.isdir(os.path.join(vault_dir, '.sg_vault'))
