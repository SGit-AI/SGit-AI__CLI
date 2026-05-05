"""Unit tests for CLI__Stash — cmd_stash / cmd_stash_pop / cmd_stash_list / cmd_stash_drop.

All tests use Vault__Test_Env (in-memory API, no HTTP) and call
CLI__Stash methods directly with argparse.Namespace-style args.
"""
import os
import types

import pytest

from sgit_ai.cli.CLI__Stash            import CLI__Stash
from tests.unit.sync.vault_test_env    import Vault__Test_Env


def _args(**kwargs):
    defaults = dict(directory='.')
    defaults.update(kwargs)
    return types.SimpleNamespace(**defaults)


class Test_CLI__Stash:

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
        self.sync  = self.snap.sync
        self.cli   = CLI__Stash()

    def teardown_method(self):
        self.snap.cleanup()

    # ------------------------------------------------------------------
    # cmd_stash — nothing to stash
    # ------------------------------------------------------------------

    def test_stash_clean_vault_prints_nothing_to_stash(self, capsys):
        """Stashing a clean vault reports nothing to stash."""
        args = _args(directory=self.vault)
        self.cli.cmd_stash(args)
        out = capsys.readouterr().out
        assert 'Nothing to stash' in out

    # ------------------------------------------------------------------
    # cmd_stash — with dirty files
    # ------------------------------------------------------------------

    def test_stash_dirty_vault_saves_stash(self, capsys):
        """Stashing a vault with a modified file creates a stash entry."""
        with open(os.path.join(self.vault, 'hello.txt'), 'w') as f:
            f.write('modified')

        args = _args(directory=self.vault)
        self.cli.cmd_stash(args)
        out = capsys.readouterr().out

        assert 'Stashing 1 changes' in out
        assert 'hello.txt' in out
        assert 'Stash saved:' in out
        assert 'sgit stash pop' in out

    def test_stash_reverts_working_copy_to_head(self, capsys):
        """After stash, the working file is restored to HEAD content."""
        with open(os.path.join(self.vault, 'hello.txt'), 'w') as f:
            f.write('dirty content')

        args = _args(directory=self.vault)
        self.cli.cmd_stash(args)

        with open(os.path.join(self.vault, 'hello.txt')) as f:
            assert f.read() == 'hello'

    def test_stash_added_file_shown_with_plus(self, capsys):
        """A newly added file is shown with + prefix in stash output."""
        with open(os.path.join(self.vault, 'new.txt'), 'w') as f:
            f.write('brand new')

        args = _args(directory=self.vault)
        self.cli.cmd_stash(args)
        out = capsys.readouterr().out
        assert '+ new.txt' in out

    def test_stash_modified_file_shown_with_tilde(self, capsys):
        """A modified file is shown with ~ prefix in stash output."""
        with open(os.path.join(self.vault, 'hello.txt'), 'w') as f:
            f.write('changed')

        args = _args(directory=self.vault)
        self.cli.cmd_stash(args)
        out = capsys.readouterr().out
        assert '~ hello.txt' in out

    # ------------------------------------------------------------------
    # cmd_stash_pop
    # ------------------------------------------------------------------

    def test_stash_pop_restores_file(self, capsys):
        """Pop applies the stash and restores the modified content."""
        with open(os.path.join(self.vault, 'hello.txt'), 'w') as f:
            f.write('stashed content')

        # stash it
        self.cli.cmd_stash(_args(directory=self.vault))
        capsys.readouterr()  # clear output

        # pop it
        self.cli.cmd_stash_pop(_args(directory=self.vault))
        out = capsys.readouterr().out
        assert 'Stash applied and dropped' in out

        with open(os.path.join(self.vault, 'hello.txt')) as f:
            assert f.read() == 'stashed content'

    def test_stash_pop_empty_vault_prints_no_stash(self, capsys):
        """Pop on a vault with no stash prints 'No stash found.'"""
        args = _args(directory=self.vault)
        self.cli.cmd_stash_pop(args)
        out = capsys.readouterr().out
        assert 'No stash found' in out

    # ------------------------------------------------------------------
    # cmd_stash_list
    # ------------------------------------------------------------------

    def test_stash_list_empty_prints_no_stashes(self, capsys):
        """List on a vault with no stash prints 'No stashes found.'"""
        self.cli.cmd_stash_list(_args(directory=self.vault))
        out = capsys.readouterr().out
        assert 'No stashes found' in out

    def test_stash_list_after_stash_shows_entry(self, capsys):
        """List after a stash shows at least one stash@{0} entry."""
        with open(os.path.join(self.vault, 'hello.txt'), 'w') as f:
            f.write('about to be stashed')
        self.cli.cmd_stash(_args(directory=self.vault))
        capsys.readouterr()

        self.cli.cmd_stash_list(_args(directory=self.vault))
        out = capsys.readouterr().out
        assert 'stash@{0}' in out

    # ------------------------------------------------------------------
    # cmd_stash_drop
    # ------------------------------------------------------------------

    def test_stash_drop_empty_vault_prints_no_stash(self, capsys):
        """Drop on a vault with no stash prints 'No stash found.'"""
        self.cli.cmd_stash_drop(_args(directory=self.vault))
        out = capsys.readouterr().out
        assert 'No stash found' in out

    def test_stash_drop_removes_stash(self, capsys):
        """Drop removes the stash so a subsequent list shows nothing."""
        with open(os.path.join(self.vault, 'hello.txt'), 'w') as f:
            f.write('dirty for drop')
        self.cli.cmd_stash(_args(directory=self.vault))
        capsys.readouterr()

        self.cli.cmd_stash_drop(_args(directory=self.vault))
        out = capsys.readouterr().out
        assert 'Dropped stash:' in out

        # confirm it's gone
        self.cli.cmd_stash_list(_args(directory=self.vault))
        out2 = capsys.readouterr().out
        assert 'No stashes found' in out2

    # ------------------------------------------------------------------
    # error paths
    # ------------------------------------------------------------------

    def test_stash_uninitialised_vault_exits(self, capsys, tmp_path):
        """Stashing in an uninitialised directory exits with code 1."""
        args = _args(directory=str(tmp_path))
        with pytest.raises(SystemExit) as exc:
            self.cli.cmd_stash(args)
        assert exc.value.code == 1
        assert 'error:' in capsys.readouterr().err

    def test_stash_pop_uninitialised_vault_prints_no_stash(self, capsys, tmp_path):
        """Pop in an uninitialised directory reports no stash (no vault to read from)."""
        args = _args(directory=str(tmp_path))
        self.cli.cmd_stash_pop(args)
        out = capsys.readouterr().out
        assert 'No stash found' in out

    def test_stash_runtime_error_exits(self, monkeypatch, capsys):
        """RuntimeError from stash.stash() → prints error, sys.exit(1)."""
        from sgit_ai.core.actions.stash.Vault__Stash import Vault__Stash
        monkeypatch.setattr(Vault__Stash, 'stash',
                            lambda self, d: (_ for _ in ()).throw(
                                RuntimeError('stash state corrupt')))
        args = _args(directory=self.vault)
        with pytest.raises(SystemExit) as exc:
            self.cli.cmd_stash(args)
        assert exc.value.code == 1
        assert 'stash state corrupt' in capsys.readouterr().err

    def test_stash_deleted_file_shown_with_minus(self, capsys):
        """A deleted tracked file is shown with - prefix in stash output."""
        os.remove(os.path.join(self.vault, 'hello.txt'))

        args = _args(directory=self.vault)
        self.cli.cmd_stash(args)
        out = capsys.readouterr().out
        assert '- hello.txt' in out

    def test_stash_pop_runtime_error_exits(self, monkeypatch, capsys):
        """RuntimeError from stash.pop() → prints error, sys.exit(1)."""
        from sgit_ai.core.actions.stash.Vault__Stash import Vault__Stash
        monkeypatch.setattr(Vault__Stash, 'pop',
                            lambda self, d: (_ for _ in ()).throw(
                                RuntimeError('pop failed')))
        args = _args(directory=self.vault)
        with pytest.raises(SystemExit) as exc:
            self.cli.cmd_stash_pop(args)
        assert exc.value.code == 1
        assert 'pop failed' in capsys.readouterr().err

    def test_stash_pop_deleted_file_shown_with_minus(self, capsys):
        """When pop deletes files, they appear with - prefix."""
        # Delete hello.txt and stash — pop should re-delete it
        os.remove(os.path.join(self.vault, 'hello.txt'))
        self.cli.cmd_stash(_args(directory=self.vault))
        capsys.readouterr()

        self.cli.cmd_stash_pop(_args(directory=self.vault))
        out = capsys.readouterr().out
        assert '- hello.txt' in out

    def test_stash_list_file_not_found_exits(self, monkeypatch, capsys):
        """FileNotFoundError from stash.list_stashes() → prints error, sys.exit(1)."""
        from sgit_ai.core.actions.stash.Vault__Stash import Vault__Stash
        monkeypatch.setattr(Vault__Stash, 'list_stashes',
                            lambda self, d: (_ for _ in ()).throw(
                                FileNotFoundError('stash dir missing')))
        args = _args(directory=self.vault)
        with pytest.raises(SystemExit) as exc:
            self.cli.cmd_stash_list(args)
        assert exc.value.code == 1
        assert 'stash dir missing' in capsys.readouterr().err

    def test_stash_drop_file_not_found_exits(self, monkeypatch, capsys):
        """FileNotFoundError from stash.drop() → prints error, sys.exit(1)."""
        from sgit_ai.core.actions.stash.Vault__Stash import Vault__Stash
        monkeypatch.setattr(Vault__Stash, 'drop',
                            lambda self, d: (_ for _ in ()).throw(
                                FileNotFoundError('stash dir missing')))
        args = _args(directory=self.vault)
        with pytest.raises(SystemExit) as exc:
            self.cli.cmd_stash_drop(args)
        assert exc.value.code == 1
        assert 'stash dir missing' in capsys.readouterr().err

    def test_stash_pop_file_not_found_exits(self, monkeypatch, capsys):
        """Lines 59-60: FileNotFoundError from stash.pop() → prints error, sys.exit(1)."""
        from sgit_ai.core.actions.stash.Vault__Stash import Vault__Stash
        monkeypatch.setattr(Vault__Stash, 'pop',
                            lambda self, d: (_ for _ in ()).throw(
                                FileNotFoundError('zip file missing')))
        args = _args(directory=self.vault)
        with pytest.raises(SystemExit) as exc:
            self.cli.cmd_stash_pop(args)
        assert exc.value.code == 1
        assert 'zip file missing' in capsys.readouterr().err
