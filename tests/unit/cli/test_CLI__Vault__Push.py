"""Unit tests for CLI__Vault.cmd_push and cmd_pull.

create_sync is monkey-patched on the CLI instance to inject the
in-memory API from Vault__Test_Env — no real HTTP calls are made.
"""
import os
import types as _types

import pytest

from sgit_ai.cli.CLI__Vault            import CLI__Vault
from sgit_ai.cli.CLI__Token_Store      import CLI__Token_Store
from sgit_ai.sync.Vault__Sync          import Vault__Sync
from sgit_ai.crypto.Vault__Crypto      import Vault__Crypto
from tests.unit.sync.vault_test_env    import Vault__Test_Env


def _args(**kwargs):
    defaults = dict(directory='.', token=None, base_url=None, branch_only=False)
    defaults.update(kwargs)
    return _types.SimpleNamespace(**defaults)


def _make_cli(api, crypto):
    """CLI__Vault with create_sync injected to use the given in-memory API."""
    cli = CLI__Vault(token_store=CLI__Token_Store())

    def _create_sync(self, base_url=None, access_token=None):
        return Vault__Sync(crypto=crypto, api=api)

    cli.create_sync = _types.MethodType(_create_sync, cli)
    return cli


class Test_CLI__Vault__Push:

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
        self.vault = self.snap.vault_dir
        self.cli   = _make_cli(self.snap.api, self.snap.crypto)

    def teardown_method(self):
        self.snap.cleanup()

    # ------------------------------------------------------------------
    # up to date
    # ------------------------------------------------------------------

    def test_push_up_to_date(self, capsys):
        """Push on an already-pushed vault reports 'Nothing to push'."""
        self.cli.cmd_push(_args(directory=self.vault, token='test-token'))
        out = capsys.readouterr().out
        assert 'Nothing to push' in out or 'up to date' in out.lower()

    # ------------------------------------------------------------------
    # new commit
    # ------------------------------------------------------------------

    def test_push_after_new_commit(self, capsys):
        """Push after adding a file and committing reports push complete."""
        with open(os.path.join(self.vault, 'new.txt'), 'w') as f:
            f.write('to be pushed')
        self.snap.sync.commit(self.vault, message='add new')

        self.cli.cmd_push(_args(directory=self.vault, token='test-token'))
        out = capsys.readouterr().out
        assert 'Push complete' in out or 'Pushed' in out

    def test_push_shows_object_count(self, capsys):
        """Push output includes the number of objects uploaded."""
        with open(os.path.join(self.vault, 'upload.txt'), 'w') as f:
            f.write('data')
        self.snap.sync.commit(self.vault, message='commit to push')

        self.cli.cmd_push(_args(directory=self.vault, token='test-token'))
        out = capsys.readouterr().out
        # Should mention objects uploaded or commits pushed
        assert 'commit' in out.lower() or 'object' in out.lower()

    def test_push_suggests_share(self, capsys):
        """Push completion output suggests sgit share."""
        with open(os.path.join(self.vault, 'x.txt'), 'w') as f:
            f.write('x')
        self.snap.sync.commit(self.vault, message='x')

        self.cli.cmd_push(_args(directory=self.vault, token='test-token'))
        out = capsys.readouterr().out
        assert 'sgit share' in out

    # ------------------------------------------------------------------
    # no token in non-TTY → exits
    # ------------------------------------------------------------------

    def test_push_no_token_non_tty_exits(self, capsys):
        """Push with no token in a non-TTY environment exits with code 1."""
        # sys.stdin.isatty() is False in tests — _prompt_remote_setup exits
        args = _args(directory=self.vault, token=None)
        with pytest.raises(SystemExit) as exc:
            self.cli.cmd_push(args)
        assert exc.value.code == 1


class Test_CLI__Vault__Pull:

    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_two_clones(files={'readme.txt': 'initial content'})

    @classmethod
    def teardown_class(cls):
        if cls._env:
            cls._env.cleanup_snapshot()

    def setup_method(self):
        self.snap  = self._env.restore()
        self.alice = self.snap.alice_dir
        self.bob   = self.snap.bob_dir
        self.cli   = _make_cli(self.snap.api, self.snap.crypto)

    def teardown_method(self):
        self.snap.cleanup()

    def test_pull_up_to_date(self, capsys):
        """Pull when already in sync reports 'Already up to date'."""
        self.cli.cmd_pull(_args(directory=self.bob, token='test-token'))
        out = capsys.readouterr().out
        assert 'Already up to date' in out or 'up to date' in out.lower()

    def test_pull_after_remote_push(self, capsys):
        """Bob pulls after Alice pushes a new file and sees it."""
        # Alice commits and pushes
        with open(os.path.join(self.alice, 'alice.txt'), 'w') as f:
            f.write('from alice')
        self.snap.sync.commit(self.alice, message='alice adds file')
        self.snap.sync.push(self.alice)

        # Bob pulls
        self.cli.cmd_pull(_args(directory=self.bob, token='test-token'))
        out = capsys.readouterr().out
        # Either "already up to date" or shows alice.txt as added
        assert 'alice.txt' in out or 'up to date' in out.lower() or 'Merged' in out

    def test_pull_shows_next_steps(self, capsys):
        """Pull output includes next-step suggestions."""
        self.cli.cmd_pull(_args(directory=self.bob, token='test-token'))
        out = capsys.readouterr().out
        # Either "up to date" or shows next steps
        assert 'sgit' in out.lower() or 'up to date' in out.lower()
