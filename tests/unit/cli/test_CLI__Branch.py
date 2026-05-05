"""Unit tests for CLI__Branch — cmd_branch_new, cmd_branch_list, cmd_switch.

Tests use Vault__Test_Env (in-memory API) and call CLI__Branch methods
directly with SimpleNamespace args. stdout/stderr captured via capsys.
"""
import os
import types

import pytest

from sgit_ai.cli.CLI__Branch           import CLI__Branch
from tests.unit.sync.vault_test_env    import Vault__Test_Env


def _args(**kwargs):
    defaults = dict(directory='.', name=None, name_or_id=None, from_branch=None)
    defaults.update(kwargs)
    return types.SimpleNamespace(**defaults)


class Test_CLI__Branch:

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
        self.cli   = CLI__Branch()

    def teardown_method(self):
        self.snap.cleanup()

    # ------------------------------------------------------------------
    # cmd_branch_list
    # ------------------------------------------------------------------

    def test_branch_list_shows_branches_header(self, capsys):
        """List shows 'Branches:' header when branches exist."""
        args = _args(directory=self.vault)
        self.cli.cmd_branch_list(args)
        out = capsys.readouterr().out
        assert 'Branches:' in out

    def test_branch_list_shows_default_branch(self, capsys):
        """List includes the default named branch ('current')."""
        args = _args(directory=self.vault)
        self.cli.cmd_branch_list(args)
        out = capsys.readouterr().out
        assert 'current' in out

    def test_branch_list_marks_current_branch(self, capsys):
        """Current branch is marked with * in the list."""
        args = _args(directory=self.vault)
        self.cli.cmd_branch_list(args)
        out = capsys.readouterr().out
        assert '*' in out

    def test_branch_list_uninitialised_vault_exits(self, capsys, tmp_path):
        """List on uninitialised directory exits with code 1."""
        args = _args(directory=str(tmp_path))
        with pytest.raises(SystemExit) as exc:
            self.cli.cmd_branch_list(args)
        assert exc.value.code == 1
        assert 'error:' in capsys.readouterr().err

    # ------------------------------------------------------------------
    # cmd_branch_new
    # ------------------------------------------------------------------

    def test_branch_new_creates_branch(self, capsys):
        """Creating a new branch prints the branch ID and switches to it."""
        args = _args(directory=self.vault, name='feature-x')
        self.cli.cmd_branch_new(args)
        out = capsys.readouterr().out
        assert 'feature-x' in out
        assert 'Branch ID:' in out
        assert "Switched to new branch 'feature-x'" in out

    def test_branch_new_without_name_exits(self, capsys):
        """cmd_branch_new with no name argument exits with code 1."""
        args = _args(directory=self.vault, name=None)
        with pytest.raises(SystemExit) as exc:
            self.cli.cmd_branch_new(args)
        assert exc.value.code == 1
        assert 'error:' in capsys.readouterr().err

    def test_branch_new_appears_in_list(self, capsys):
        """After creating a branch it appears in cmd_branch_list output."""
        self.cli.cmd_branch_new(_args(directory=self.vault, name='my-feature'))
        capsys.readouterr()

        self.cli.cmd_branch_list(_args(directory=self.vault))
        out = capsys.readouterr().out
        assert 'my-feature' in out

    def test_branch_new_uninitialised_vault_exits(self, capsys, tmp_path):
        """branch_new on uninitialised directory exits with code 1."""
        args = _args(directory=str(tmp_path), name='foo')
        with pytest.raises(SystemExit) as exc:
            self.cli.cmd_branch_new(args)
        assert exc.value.code == 1

    # ------------------------------------------------------------------
    # cmd_switch
    # ------------------------------------------------------------------

    def test_switch_to_existing_branch(self, capsys):
        """Switching to a newly created branch succeeds and prints confirmation."""
        # Create a new branch (this also switches to it)
        self.cli.cmd_branch_new(_args(directory=self.vault, name='target'))
        capsys.readouterr()

        # Switch back to 'current' (the default branch)
        self.cli.cmd_switch(_args(directory=self.vault, name_or_id='current'))
        out = capsys.readouterr().out
        assert 'current' in out

    def test_switch_without_name_exits(self, capsys):
        """cmd_switch with no name_or_id exits with code 1."""
        args = _args(directory=self.vault, name_or_id=None)
        with pytest.raises(SystemExit) as exc:
            self.cli.cmd_switch(args)
        assert exc.value.code == 1
        assert 'error:' in capsys.readouterr().err

    def test_switch_reports_files_checked_out(self, capsys):
        """Switch output includes a file checkout count."""
        # Create branch 'other' from clean state, then switch back to 'current'
        self.cli.cmd_branch_new(_args(directory=self.vault, name='other'))
        capsys.readouterr()

        self.cli.cmd_switch(_args(directory=self.vault, name_or_id='current'))
        out = capsys.readouterr().out
        assert 'file(s)' in out

    def test_switch_uninitialised_vault_exits(self, capsys, tmp_path):
        """switch on uninitialised directory exits with code 1."""
        args = _args(directory=str(tmp_path), name_or_id='main')
        with pytest.raises(SystemExit) as exc:
            self.cli.cmd_switch(args)
        assert exc.value.code == 1

    # ------------------------------------------------------------------
    # RuntimeError paths (lines 27-29, 50-52, 106-112)
    # ------------------------------------------------------------------

    def test_branch_new_runtime_error_exits(self, capsys):
        """RuntimeError from branch_new with invalid from_branch → prints error, sys.exit(1)."""
        # Passing a non-existent --from branch triggers RuntimeError('Source branch not found: ...')
        args = _args(directory=self.vault, name='clash', from_branch='nonexistent-branch-id-xyz')
        with pytest.raises(SystemExit) as exc:
            self.cli.cmd_branch_new(args)
        assert exc.value.code == 1
        err = capsys.readouterr().err
        assert 'error:' in err

    def test_branch_list_runtime_error_exits(self, monkeypatch, capsys):
        """RuntimeError from branch_list → prints error, sys.exit(1)."""
        from sgit_ai.core.actions.branch.Vault__Branch_Switch import Vault__Branch_Switch
        monkeypatch.setattr(Vault__Branch_Switch, 'branch_list',
                            lambda self, d: (_ for _ in ()).throw(
                                RuntimeError('state corrupt')))
        args = _args(directory=self.vault)
        with pytest.raises(SystemExit) as exc:
            self.cli.cmd_branch_list(args)
        assert exc.value.code == 1
        assert 'state corrupt' in capsys.readouterr().err

    def test_branch_list_no_branches(self, monkeypatch, capsys):
        """When no branches exist, prints 'No branches found.'"""
        from sgit_ai.core.actions.branch.Vault__Branch_Switch import Vault__Branch_Switch
        monkeypatch.setattr(Vault__Branch_Switch, 'branch_list',
                            lambda self, d: dict(branches=[], my_branch_id=''))
        args = _args(directory=self.vault)
        self.cli.cmd_branch_list(args)
        assert 'No branches found.' in capsys.readouterr().out

    def test_switch_runtime_error_generic_exits(self, capsys):
        """Switching to a non-existent branch name → prints 'error:', sys.exit(1)."""
        # 'nonexistent-ghost-branch' is not in the vault → RuntimeError('Branch not found: ...')
        args = _args(directory=self.vault, name_or_id='nonexistent-ghost-branch')
        with pytest.raises(SystemExit) as exc:
            self.cli.cmd_switch(args)
        assert exc.value.code == 1
        err = capsys.readouterr().err
        assert 'error:' in err

    def test_switch_uncommitted_changes_error(self, capsys):
        """Modified file + switch without --force → RuntimeError 'uncommitted changes'."""
        # Create a second branch to switch to
        self.cli.cmd_branch_new(_args(directory=self.vault, name='target-branch'))
        capsys.readouterr()

        # Switch back to 'current' first so we can have something to switch to
        self.cli.cmd_switch(_args(directory=self.vault, name_or_id='current'))
        capsys.readouterr()

        # Dirty the working copy (modify a tracked file)
        with open(os.path.join(self.vault, 'readme.txt'), 'w') as f:
            f.write('this content is uncommitted')

        # Switch without --force should raise RuntimeError about uncommitted changes
        args = _args(directory=self.vault, name_or_id='target-branch')
        with pytest.raises(SystemExit) as exc:
            self.cli.cmd_switch(args)
        assert exc.value.code == 1
        err = capsys.readouterr().err
        assert 'uncommitted changes' in err

    def test_switch_new_clone_not_reused(self, capsys):
        """Switching to a branch whose clone key files are removed forces a new clone (reused=False)."""
        import glob
        # Create a new named branch (this also creates a clone for it)
        self.cli.cmd_branch_new(_args(directory=self.vault, name='no-reuse-feature'))
        capsys.readouterr()

        # Switch back to 'current'
        self.cli.cmd_switch(_args(directory=self.vault, name_or_id='current'))
        capsys.readouterr()

        # Remove all .pem key files in the vault's local directory so the existing
        # clone branch for 'no-reuse-feature' can't be found as usable.
        local_dir = os.path.join(self.vault, '.sg_vault', 'local')
        for pem_file in glob.glob(os.path.join(local_dir, '*.pem')):
            os.remove(pem_file)

        # Switch to no-reuse-feature — no usable clone found → reused=False path
        self.cli.cmd_switch(_args(directory=self.vault, name_or_id='no-reuse-feature'))
        out = capsys.readouterr().out
        assert 'no-reuse-feature' in out
        # The reused=False path prints 'No local clone branch found' and 'new clone'
        assert 'new clone' in out.lower() or 'creating' in out.lower()
