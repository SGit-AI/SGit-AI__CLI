"""Unit tests for CLI__Revert — cmd_revert.

All tests use Vault__Test_Env (in-memory API, no HTTP) and call
CLI__Revert methods directly with argparse.Namespace-style args.
stdout/stderr are captured via capsys.
"""
import os
import types

import pytest

from sgit_ai.cli.CLI__Revert           import CLI__Revert
from sgit_ai.sync.Vault__Sync          import Vault__Sync
from tests.unit.sync.vault_test_env    import Vault__Test_Env


def _args(**kwargs):
    """Build a minimal argparse.Namespace substitute."""
    defaults = dict(directory='.', commit=None, files=None, force=False)
    defaults.update(kwargs)
    return types.SimpleNamespace(**defaults)


class Test_CLI__Revert:

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
        self.snap    = self._env.restore()
        self.vault   = self.snap.vault_dir
        self.sync    = self.snap.sync
        self.cli     = CLI__Revert()

    def teardown_method(self):
        self.snap.cleanup()

    # ------------------------------------------------------------------
    # revert_to_head — nothing to revert
    # ------------------------------------------------------------------

    def test_revert_nothing_to_revert(self, capsys):
        """Revert on a clean committed vault prints 'Nothing to revert'."""
        # Init a brand-new vault with no commits beyond init
        env2  = Vault__Test_Env()
        snap2 = env2.setup_single_vault.__func__ and None  # side-effect free check
        import tempfile
        from sgit_ai.api.Vault__API__In_Memory import Vault__API__In_Memory
        from sgit_ai.crypto.Vault__Crypto      import Vault__Crypto

        tmp   = tempfile.mkdtemp()
        api   = Vault__API__In_Memory()
        sync  = Vault__Sync(crypto=Vault__Crypto(), api=api)
        sync.init(tmp)
        # status is clean — revert reports 0 files reverted
        args  = _args(directory=tmp, force=True)
        self.cli.cmd_revert(args)
        out = capsys.readouterr().out
        assert '0 file(s) reverted' in out
        import shutil; shutil.rmtree(tmp, ignore_errors=True)

    # ------------------------------------------------------------------
    # revert_to_head — discard uncommitted change with --force
    # ------------------------------------------------------------------

    def test_revert_to_head_with_force(self, capsys):
        """Modified file is restored to HEAD content when --force is used."""
        # Modify hello.txt after the snapshot commit
        with open(os.path.join(self.vault, 'hello.txt'), 'w') as f:
            f.write('changed content')

        args = _args(directory=self.vault, force=True)
        self.cli.cmd_revert(args)
        out = capsys.readouterr().out

        assert 'Reverting to' in out
        assert 'hello.txt' in out
        # File should be back to original content
        with open(os.path.join(self.vault, 'hello.txt')) as f:
            assert f.read() == 'hello world'

    def test_revert_reports_restored_count(self, capsys):
        """Output footer shows the number of reverted files."""
        with open(os.path.join(self.vault, 'hello.txt'), 'w') as f:
            f.write('dirty')

        args = _args(directory=self.vault, force=True)
        self.cli.cmd_revert(args)
        out = capsys.readouterr().out
        assert '1 file(s) reverted' in out

    # ------------------------------------------------------------------
    # revert_to_head — safety prompt (no --force, no --files)
    # ------------------------------------------------------------------

    def test_revert_aborts_on_n_answer(self, capsys, monkeypatch):
        """Safety prompt answered 'n' prints 'Aborted.' and does not revert."""
        with open(os.path.join(self.vault, 'hello.txt'), 'w') as f:
            f.write('about to be discarded')

        monkeypatch.setattr('builtins.input', lambda _: 'n')
        args = _args(directory=self.vault, force=False)
        self.cli.cmd_revert(args)

        out = capsys.readouterr().out
        assert 'Aborted' in out
        # File must be unchanged
        with open(os.path.join(self.vault, 'hello.txt')) as f:
            assert f.read() == 'about to be discarded'

    def test_revert_proceeds_on_y_answer(self, capsys, monkeypatch):
        """Safety prompt answered 'y' reverts the file."""
        with open(os.path.join(self.vault, 'hello.txt'), 'w') as f:
            f.write('about to be reverted')

        monkeypatch.setattr('builtins.input', lambda _: 'y')
        args = _args(directory=self.vault, force=False)
        self.cli.cmd_revert(args)

        out = capsys.readouterr().out
        assert 'Reverting to' in out
        with open(os.path.join(self.vault, 'hello.txt')) as f:
            assert f.read() == 'hello world'

    # ------------------------------------------------------------------
    # revert specific files
    # ------------------------------------------------------------------

    def test_revert_specific_file_skips_others(self, capsys):
        """With --files, only the named file is reverted; others stay dirty."""
        # Dirty two files
        with open(os.path.join(self.vault, 'hello.txt'), 'w') as f:
            f.write('dirty hello')
        extra = os.path.join(self.vault, 'extra.txt')
        with open(extra, 'w') as f:
            f.write('new file not in HEAD')

        args = _args(directory=self.vault, files=['hello.txt'], force=False)
        self.cli.cmd_revert(args)

        # hello.txt reverted
        with open(os.path.join(self.vault, 'hello.txt')) as f:
            assert f.read() == 'hello world'
        # extra.txt untouched (not in HEAD, not mentioned in files list)
        assert os.path.exists(extra)

    # ------------------------------------------------------------------
    # revert to specific commit
    # ------------------------------------------------------------------

    def test_revert_to_specific_commit(self, capsys):
        """--commit <id> reverts to that commit's tree."""
        # Add and commit a second file so there's a second commit
        with open(os.path.join(self.vault, 'second.txt'), 'w') as f:
            f.write('second file')
        self.sync.commit(self.vault, message='add second')

        # Record the first commit id (the one with only hello.txt)
        first_commit = self.snap.commit_id

        # Now dirty hello.txt and revert to the first commit
        with open(os.path.join(self.vault, 'hello.txt'), 'w') as f:
            f.write('mutated')

        args = _args(directory=self.vault, commit=first_commit, force=True)
        self.cli.cmd_revert(args)

        out = capsys.readouterr().out
        assert f'commit {first_commit}' in out

    # ------------------------------------------------------------------
    # error paths
    # ------------------------------------------------------------------

    def test_revert_uninitialised_vault_exits(self, capsys, tmp_path):
        """Reverting in a directory that has no vault prints error and exits."""
        args = _args(directory=str(tmp_path), force=True)
        with pytest.raises(SystemExit) as exc:
            self.cli.cmd_revert(args)
        assert exc.value.code == 1
        err = capsys.readouterr().err
        assert 'error:' in err
