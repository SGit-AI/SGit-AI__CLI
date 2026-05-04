"""Unit tests for CLI__Diff — cmd_diff and _print_result.

Tests use Vault__Test_Env (in-memory API, no HTTP) and call
CLI__Diff methods directly with argparse.Namespace-style args.
"""
import os
import types

import pytest

from sgit_ai.cli.CLI__Diff             import CLI__Diff
from tests.unit.sync.vault_test_env    import Vault__Test_Env


def _args(**kwargs):
    defaults = dict(directory='.', remote=False, commit=None, files_only=False)
    defaults.update(kwargs)
    return types.SimpleNamespace(**defaults)


class Test_CLI__Diff:

    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_single_vault(files={'hello.txt': 'hello world\n',
                                           'data.txt':  'line1\nline2\n'})

    @classmethod
    def teardown_class(cls):
        if cls._env:
            cls._env.cleanup_snapshot()

    def setup_method(self):
        self.snap  = self._env.restore()
        self.vault = self.snap.vault_dir
        self.sync  = self.snap.sync
        self.cli   = CLI__Diff()

    def teardown_method(self):
        self.snap.cleanup()

    # ------------------------------------------------------------------
    # no changes — clean working copy
    # ------------------------------------------------------------------

    def test_diff_clean_vault_shows_no_changes(self, capsys):
        """Diff against HEAD on a clean vault reports 'No changes'."""
        args = _args(directory=self.vault)
        self.cli.cmd_diff(args)
        out = capsys.readouterr().out
        assert 'No changes' in out

    # ------------------------------------------------------------------
    # modified file
    # ------------------------------------------------------------------

    def test_diff_modified_file_shows_tilde(self, capsys):
        """Modified file appears with ~ prefix in diff output."""
        with open(os.path.join(self.vault, 'hello.txt'), 'w') as f:
            f.write('hello world\nmodified line\n')

        args = _args(directory=self.vault)
        self.cli.cmd_diff(args)
        out = capsys.readouterr().out
        assert '~ hello.txt' in out

    def test_diff_modified_shows_summary_line(self, capsys):
        """Summary line reports '1 modified' when one file is changed."""
        with open(os.path.join(self.vault, 'hello.txt'), 'w') as f:
            f.write('changed')

        args = _args(directory=self.vault)
        self.cli.cmd_diff(args)
        out = capsys.readouterr().out
        assert '1 modified' in out

    def test_diff_modified_includes_inline_diff(self, capsys):
        """Without --files-only, inline unified diff text is printed."""
        with open(os.path.join(self.vault, 'hello.txt'), 'w') as f:
            f.write('hello world\nnew line added\n')

        args = _args(directory=self.vault, files_only=False)
        self.cli.cmd_diff(args)
        out = capsys.readouterr().out
        # unified diff markers
        assert '@@' in out or '+new line added' in out

    def test_diff_files_only_suppresses_inline_diff(self, capsys):
        """With --files-only, inline diff text is suppressed."""
        with open(os.path.join(self.vault, 'hello.txt'), 'w') as f:
            f.write('hello world\nadded\n')

        args = _args(directory=self.vault, files_only=True)
        self.cli.cmd_diff(args)
        out = capsys.readouterr().out
        assert '~ hello.txt' in out
        assert '@@' not in out

    # ------------------------------------------------------------------
    # added file
    # ------------------------------------------------------------------

    def test_diff_added_file_shows_plus(self, capsys):
        """A new untracked file appears with + prefix and byte count."""
        with open(os.path.join(self.vault, 'new.txt'), 'w') as f:
            f.write('brand new file')

        args = _args(directory=self.vault)
        self.cli.cmd_diff(args)
        out = capsys.readouterr().out
        assert '+ new.txt' in out
        assert '1 added' in out

    # ------------------------------------------------------------------
    # deleted file
    # ------------------------------------------------------------------

    def test_diff_deleted_file_shows_minus(self, capsys):
        """A deleted tracked file appears with - prefix."""
        os.remove(os.path.join(self.vault, 'hello.txt'))

        args = _args(directory=self.vault)
        self.cli.cmd_diff(args)
        out = capsys.readouterr().out
        assert '- hello.txt' in out
        assert '1 deleted' in out

    # ------------------------------------------------------------------
    # multiple changes
    # ------------------------------------------------------------------

    def test_diff_multiple_changes_summary(self, capsys):
        """Summary correctly counts multiple simultaneous changes."""
        with open(os.path.join(self.vault, 'hello.txt'), 'w') as f:
            f.write('modified')
        with open(os.path.join(self.vault, 'extra.txt'), 'w') as f:
            f.write('new file')

        args = _args(directory=self.vault)
        self.cli.cmd_diff(args)
        out = capsys.readouterr().out
        assert '1 modified' in out
        assert '1 added' in out

    # ------------------------------------------------------------------
    # diff vs specific commit
    # ------------------------------------------------------------------

    def test_diff_vs_commit_uses_commit_ref(self, capsys):
        """--commit <id> diffs working copy against that commit."""
        # Make a second commit
        with open(os.path.join(self.vault, 'second.txt'), 'w') as f:
            f.write('second')
        self.sync.commit(self.vault, message='second commit')

        first_commit = self.snap.commit_id

        # Now diff against the first commit — second.txt should appear as added
        args = _args(directory=self.vault, commit=first_commit)
        self.cli.cmd_diff(args)
        out = capsys.readouterr().out
        # second.txt is new relative to first commit
        assert 'second.txt' in out

    # ------------------------------------------------------------------
    # diff vs remote
    # ------------------------------------------------------------------

    def test_diff_remote_on_up_to_date_vault(self, capsys):
        """Diff vs remote on an up-to-date vault reports no changes."""
        # The snapshot already did init + commit + push, so remote == HEAD
        args = _args(directory=self.vault, remote=True)
        self.cli.cmd_diff(args)
        out = capsys.readouterr().out
        assert 'No changes' in out

    def test_diff_remote_after_local_commit(self, capsys):
        """After a local commit not yet pushed, diff vs remote shows new objects."""
        with open(os.path.join(self.vault, 'unpushed.txt'), 'w') as f:
            f.write('not pushed yet')
        self.sync.commit(self.vault, message='unpushed commit')

        args = _args(directory=self.vault, remote=True)
        self.cli.cmd_diff(args)
        out = capsys.readouterr().out
        assert 'unpushed.txt' in out

    # ------------------------------------------------------------------
    # error paths
    # ------------------------------------------------------------------

    def test_diff_uninitialised_vault_exits(self, capsys, tmp_path):
        """Diffing in an uninitialised directory exits with code 1."""
        args = _args(directory=str(tmp_path))
        with pytest.raises(SystemExit) as exc:
            self.cli.cmd_diff(args)
        assert exc.value.code == 1
        assert 'error:' in capsys.readouterr().err

    def test_diff_runtime_error_exits(self, monkeypatch, capsys):
        """RuntimeError from diff_vs_head → prints error, sys.exit(1)."""
        from sgit_ai.sync.Vault__Diff import Vault__Diff
        monkeypatch.setattr(Vault__Diff, 'diff_vs_head',
                            lambda self, d: (_ for _ in ()).throw(
                                RuntimeError('vault state corrupt')))
        args = _args(directory=self.vault)
        with pytest.raises(SystemExit) as exc:
            self.cli.cmd_diff(args)
        assert exc.value.code == 1
        assert 'vault state corrupt' in capsys.readouterr().err

    def test_diff_file_not_found_exits(self, capsys):
        """FileNotFoundError raised when vault_key is deleted → prints error, sys.exit(1)."""
        # Deleting the vault_key file causes _init_components to raise FileNotFoundError
        vault_key_path = os.path.join(self.vault, '.sg_vault', 'local', 'vault_key')
        os.remove(vault_key_path)
        args = _args(directory=self.vault)
        with pytest.raises(SystemExit) as exc:
            self.cli.cmd_diff(args)
        assert exc.value.code == 1
        assert 'error:' in capsys.readouterr().err

    # ------------------------------------------------------------------
    # binary modified file (lines 55-61)
    # ------------------------------------------------------------------

    def test_diff_binary_modified_shows_sizes_and_hashes(self, capsys):
        """Binary modified file (containing null bytes) shows before/after sizes and hashes."""
        # Write a binary file (with null bytes so it is detected as binary), commit it,
        # then overwrite it with different binary content so the diff reports 'modified'
        binary_before = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR' + bytes(range(20))
        binary_after  = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR' + bytes(range(20, 40))

        img_path = os.path.join(self.vault, 'image.png')
        with open(img_path, 'wb') as f:
            f.write(binary_before)
        self.sync.commit(self.vault, message='add binary image')

        # Now modify the binary file so it shows as 'modified' in diff
        with open(img_path, 'wb') as f:
            f.write(binary_after)

        args = _args(directory=self.vault)
        self.cli.cmd_diff(args)
        out = capsys.readouterr().out
        assert '~ image.png' in out
        assert '(binary)' in out
        assert 'before:' in out
        assert 'after:' in out
