"""Unit tests for CLI__Vault.cmd_status and cmd_commit.

Monkeypatches Vault__API in CLI__Vault to use Vault__API__In_Memory so no
network calls are made. Tests use Vault__Test_Env for vault state.
"""
import os
import types

import pytest

from sgit_ai.cli.CLI__Vault            import CLI__Vault
from sgit_ai.api.Vault__API__In_Memory import Vault__API__In_Memory
from sgit_ai.cli.CLI__Token_Store      import CLI__Token_Store
from tests.unit.sync.vault_test_env    import Vault__Test_Env


def _args(**kwargs):
    defaults = dict(directory='.', message='', explain=False, token=None, base_url=None)
    defaults.update(kwargs)
    return types.SimpleNamespace(**defaults)


def _make_cli(snap):
    """Return CLI__Vault whose Vault__API is the snapshot's in-memory store."""
    cli = CLI__Vault(token_store=CLI__Token_Store())
    # Inject a create_sync that always returns the snapshot's sync+API
    from sgit_ai.sync.Vault__Sync     import Vault__Sync
    from sgit_ai.crypto.Vault__Crypto import Vault__Crypto
    api    = snap.api
    crypto = snap.crypto

    def _create_sync(self, base_url=None, access_token=None):
        return Vault__Sync(crypto=crypto, api=api)

    import types as _types
    cli.create_sync = _types.MethodType(_create_sync, cli)
    return cli


class Test_CLI__Vault__Status:

    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_single_vault(files={'hello.txt': 'hello world'})

    @classmethod
    def teardown_class(cls):
        if cls._env:
            cls._env.cleanup_snapshot()

    def setup_method(self):
        self.snap  = self._env.restore()
        self.vault = self.snap.vault_dir
        self.cli   = _make_cli(self.snap)

    def teardown_method(self):
        self.snap.cleanup()

    # ------------------------------------------------------------------
    # clean vault
    # ------------------------------------------------------------------

    def test_status_clean_vault(self, capsys):
        """Status on a clean vault says 'Nothing to commit'."""
        self.cli.cmd_status(_args(directory=self.vault))
        out = capsys.readouterr().out
        assert 'Nothing to commit' in out

    def test_status_shows_branch_info(self, capsys):
        """Status header shows the branch ID."""
        self.cli.cmd_status(_args(directory=self.vault))
        out = capsys.readouterr().out
        assert 'On branch:' in out

    # ------------------------------------------------------------------
    # dirty vault
    # ------------------------------------------------------------------

    def test_status_added_file(self, capsys):
        """Status shows + prefix for a new untracked file."""
        with open(os.path.join(self.vault, 'new.txt'), 'w') as f:
            f.write('new')
        self.cli.cmd_status(_args(directory=self.vault))
        out = capsys.readouterr().out
        assert '+ new.txt' in out

    def test_status_modified_file(self, capsys):
        """Status shows ~ prefix for a modified tracked file."""
        with open(os.path.join(self.vault, 'hello.txt'), 'w') as f:
            f.write('changed')
        self.cli.cmd_status(_args(directory=self.vault))
        out = capsys.readouterr().out
        assert '~ hello.txt' in out

    def test_status_deleted_file(self, capsys):
        """Status shows - prefix for a deleted tracked file."""
        os.remove(os.path.join(self.vault, 'hello.txt'))
        self.cli.cmd_status(_args(directory=self.vault))
        out = capsys.readouterr().out
        assert '- hello.txt' in out

    def test_status_suggests_commit(self, capsys):
        """Status on dirty vault suggests running sgit commit."""
        with open(os.path.join(self.vault, 'hello.txt'), 'w') as f:
            f.write('dirty')
        self.cli.cmd_status(_args(directory=self.vault))
        out = capsys.readouterr().out
        assert 'sgit commit' in out

    # ------------------------------------------------------------------
    # --explain flag
    # ------------------------------------------------------------------

    def test_status_explain_flag(self, capsys):
        """--explain prints additional notes about the two-branch model."""
        self.cli.cmd_status(_args(directory=self.vault, explain=True))
        out = capsys.readouterr().out
        assert 'clone branch' in out


class Test_CLI__Vault__Commit:

    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_single_vault(files={'file.txt': 'initial'})

    @classmethod
    def teardown_class(cls):
        if cls._env:
            cls._env.cleanup_snapshot()

    def setup_method(self):
        self.snap  = self._env.restore()
        self.vault = self.snap.vault_dir
        self.cli   = _make_cli(self.snap)

    def teardown_method(self):
        self.snap.cleanup()

    def test_commit_new_file(self, capsys):
        """Committing a new file prints 'Committed N file(s)'."""
        with open(os.path.join(self.vault, 'new.txt'), 'w') as f:
            f.write('new content')
        self.cli.cmd_commit(_args(directory=self.vault, message='add new'))
        out = capsys.readouterr().out
        assert 'Committed' in out
        assert '1 file(s)' in out

    def test_commit_prints_commit_id(self, capsys):
        """Commit output includes the commit ID."""
        with open(os.path.join(self.vault, 'new.txt'), 'w') as f:
            f.write('x')
        self.cli.cmd_commit(_args(directory=self.vault, message='test'))
        out = capsys.readouterr().out
        assert 'Commit:' in out

    def test_commit_suggests_push(self, capsys):
        """Commit output suggests running sgit push next."""
        with open(os.path.join(self.vault, 'new.txt'), 'w') as f:
            f.write('x')
        self.cli.cmd_commit(_args(directory=self.vault, message='test'))
        out = capsys.readouterr().out
        assert 'sgit push' in out

    def test_commit_modified_file(self, capsys):
        """Committing a modified tracked file succeeds."""
        with open(os.path.join(self.vault, 'file.txt'), 'w') as f:
            f.write('modified content')
        self.cli.cmd_commit(_args(directory=self.vault, message='modify'))
        out = capsys.readouterr().out
        assert 'Committed' in out

    def test_commit_then_status_clean(self, capsys):
        """After commit, status reports clean working tree."""
        with open(os.path.join(self.vault, 'new.txt'), 'w') as f:
            f.write('x')
        self.cli.cmd_commit(_args(directory=self.vault, message='add'))
        capsys.readouterr()

        self.cli.cmd_status(_args(directory=self.vault))
        out = capsys.readouterr().out
        assert 'Nothing to commit' in out
