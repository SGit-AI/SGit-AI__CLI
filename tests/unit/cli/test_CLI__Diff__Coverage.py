"""Coverage tests for CLI__Diff — cmd_log_file, cmd_show, diff_commits branch,
and the 'bare/data' hint in cmd_diff.

Missing lines targeted: 10-36 (cmd_log_file), 39-69 (cmd_show),
83 (diff_commits branch), 93 (bare/data hint in cmd_diff),
113-114 (two-commits labels), 174 (two-commits vs_label).
"""
import os
import types

import pytest

from sgit_ai.cli.CLI__Diff          import CLI__Diff
from sgit_ai.core.actions.diff.Vault__Diff       import Vault__Diff
from tests.unit.sync.vault_test_env import Vault__Test_Env


def _args(**kwargs):
    defaults = dict(directory='.', remote=False, commit=None, commit2=None,
                    files_only=False, file_path=None, commit_id=None)
    defaults.update(kwargs)
    return types.SimpleNamespace(**defaults)


class Test_CLI__Diff__Log_File:
    """Tests for cmd_log_file (lines 9-36)."""

    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_single_vault(files={'readme.md': 'initial content\n'})

    @classmethod
    def teardown_class(cls):
        if cls._env:
            cls._env.cleanup_snapshot()

    def setup_method(self):
        self.snap  = self._env.restore()
        self.vault = self.snap.vault_dir
        self.cli   = CLI__Diff()

    def teardown_method(self):
        self.snap.cleanup()

    def test_cmd_log_file_no_file_path_exits(self, capsys):
        """No file_path → 'error: file path is required', sys.exit(1)."""
        args = _args(directory=self.vault, file_path=None)
        with pytest.raises(SystemExit) as exc:
            self.cli.cmd_log_file(args)
        assert exc.value.code == 1
        assert 'file path is required' in capsys.readouterr().err

    def test_cmd_log_file_returns_entries(self, capsys):
        """log_file on a real vault returns and prints commit entries."""
        args = _args(directory=self.vault, file_path='readme.md')
        self.cli.cmd_log_file(args)
        out = capsys.readouterr().out
        assert 'readme.md' in out

    def test_cmd_log_file_no_entries_prints_message(self, capsys, monkeypatch):
        """Empty log → prints 'No commits found' (lines 27-29)."""
        monkeypatch.setattr(Vault__Diff, 'log_file', lambda self, d, fp, **kw: [])
        args = _args(directory=self.vault, file_path='nonexistent.txt')
        self.cli.cmd_log_file(args)
        out = capsys.readouterr().out
        assert 'No commits found' in out

    def test_cmd_log_file_file_not_found_exits(self, capsys, monkeypatch):
        """FileNotFoundError → prints error, sys.exit(1) (lines 20-22)."""
        monkeypatch.setattr(Vault__Diff, 'log_file',
                            lambda self, d, fp, **kw: (_ for _ in ()).throw(
                                FileNotFoundError('vault_key missing')))
        args = _args(directory=self.vault, file_path='a.txt')
        with pytest.raises(SystemExit) as exc:
            self.cli.cmd_log_file(args)
        assert exc.value.code == 1
        assert 'error:' in capsys.readouterr().err

    def test_cmd_log_file_runtime_error_exits(self, capsys, monkeypatch):
        """RuntimeError → prints error, sys.exit(1) (lines 23-25)."""
        monkeypatch.setattr(Vault__Diff, 'log_file',
                            lambda self, d, fp, **kw: (_ for _ in ()).throw(
                                RuntimeError('corrupt vault')))
        args = _args(directory=self.vault, file_path='a.txt')
        with pytest.raises(SystemExit) as exc:
            self.cli.cmd_log_file(args)
        assert exc.value.code == 1
        assert 'corrupt vault' in capsys.readouterr().err


class Test_CLI__Diff__Show:
    """Tests for cmd_show (lines 38-70)."""

    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_single_vault(files={'file.txt': 'hello\n'})

    @classmethod
    def teardown_class(cls):
        if cls._env:
            cls._env.cleanup_snapshot()

    def setup_method(self):
        self.snap      = self._env.restore()
        self.vault     = self.snap.vault_dir
        self.sync      = self.snap.sync
        self.commit_id = self.snap.commit_id
        self.cli       = CLI__Diff()

    def teardown_method(self):
        self.snap.cleanup()

    def test_cmd_show_no_commit_id_exits(self, capsys):
        """No commit_id → prints error, sys.exit(1) (lines 43-45)."""
        args = _args(directory=self.vault, commit_id=None)
        with pytest.raises(SystemExit) as exc:
            self.cli.cmd_show(args)
        assert exc.value.code == 1
        assert 'commit ID is required' in capsys.readouterr().err

    def test_cmd_show_success(self, capsys):
        """show_commit on a real vault prints commit id and Date (lines 60-67)."""
        args = _args(directory=self.vault, commit_id=self.commit_id)
        self.cli.cmd_show(args)
        out = capsys.readouterr().out
        assert self.commit_id in out
        assert 'Date:' in out

    def test_cmd_show_with_parent_prints_parent_line(self, capsys):
        """Commit with a parent shows 'parent <id>' (line 62)."""
        with open(os.path.join(self.vault, 'file.txt'), 'w') as f:
            f.write('modified\n')
        result = self.sync.commit(self.vault, message='second commit')
        second_commit_id = result['commit_id']

        args = _args(directory=self.vault, commit_id=second_commit_id)
        self.cli.cmd_show(args)
        out = capsys.readouterr().out
        assert 'parent' in out
        assert second_commit_id in out

    def test_cmd_show_file_not_found_with_bare_data_hint(self, capsys, monkeypatch):
        """FileNotFoundError with 'bare/data' in path → prints hint (lines 50-55)."""
        monkeypatch.setattr(Vault__Diff, 'show_commit',
                            lambda self, d, cid: (_ for _ in ()).throw(
                                FileNotFoundError('/vault/.sg_vault/bare/data/abc123')))
        args = _args(directory=self.vault, commit_id=self.commit_id)
        with pytest.raises(SystemExit) as exc:
            self.cli.cmd_show(args)
        assert exc.value.code == 1
        err = capsys.readouterr().err
        assert 'hint:' in err

    def test_cmd_show_runtime_error_exits(self, capsys, monkeypatch):
        """RuntimeError from show_commit → prints error, sys.exit(1) (lines 56-58)."""
        monkeypatch.setattr(Vault__Diff, 'show_commit',
                            lambda self, d, cid: (_ for _ in ()).throw(
                                RuntimeError('decode error')))
        args = _args(directory=self.vault, commit_id=self.commit_id)
        with pytest.raises(SystemExit) as exc:
            self.cli.cmd_show(args)
        assert exc.value.code == 1
        assert 'decode error' in capsys.readouterr().err


class Test_CLI__Diff__Two_Commits:
    """Tests for diff_commits mode: lines 83, 93, 113-114, 174."""

    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_single_vault(files={'a.txt': 'version one\n'})

    @classmethod
    def teardown_class(cls):
        if cls._env:
            cls._env.cleanup_snapshot()

    def setup_method(self):
        self.snap    = self._env.restore()
        self.vault   = self.snap.vault_dir
        self.sync    = self.snap.sync
        self.commit1 = self.snap.commit_id
        self.cli     = CLI__Diff()
        # Make a second commit so we have two commits to compare
        with open(os.path.join(self.vault, 'a.txt'), 'w') as f:
            f.write('version two\n')
        result = self.sync.commit(self.vault, message='second version')
        self.commit2 = result['commit_id']

    def teardown_method(self):
        self.snap.cleanup()

    def test_diff_two_commits_calls_diff_commits(self, capsys):
        """commit + commit2 args → diff_commits branch (line 83)."""
        args = _args(directory=self.vault, commit=self.commit1, commit2=self.commit2)
        self.cli.cmd_diff(args)
        out = capsys.readouterr().out
        # a.txt modified → '1 modified' in summary
        assert '1 modified' in out or 'modified' in out

    def test_diff_two_commits_vs_label_uses_arrow(self, capsys):
        """Two-commits summary uses 'commit_a → commit_b' format (line 174)."""
        args = _args(directory=self.vault, commit=self.commit1, commit2=self.commit2)
        self.cli.cmd_diff(args)
        out = capsys.readouterr().out
        assert '→' in out

    def test_diff_two_commits_diff_header_labels(self, capsys):
        """Inline diff headers use 'commit <id>' labels (lines 113-114)."""
        args = _args(directory=self.vault, commit=self.commit1, commit2=self.commit2,
                     files_only=False)
        self.cli.cmd_diff(args)
        out = capsys.readouterr().out
        # The unified diff for a.txt should include commit-labelled before/after
        assert 'commit ' in out

    def test_diff_file_not_found_bare_data_hint(self, capsys, monkeypatch):
        """FileNotFoundError with 'bare/data' path → prints hint (line 93)."""
        monkeypatch.setattr(Vault__Diff, 'diff_vs_head',
                            lambda self, d: (_ for _ in ()).throw(
                                FileNotFoundError('/vault/.sg_vault/bare/data/abc123')))
        args = _args(directory=self.vault)
        with pytest.raises(SystemExit) as exc:
            self.cli.cmd_diff(args)
        assert exc.value.code == 1
        err = capsys.readouterr().err
        assert 'hint:' in err
