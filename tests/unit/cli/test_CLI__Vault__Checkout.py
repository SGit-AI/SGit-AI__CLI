"""Coverage tests for CLI__Vault.cmd_checkout — the target-branch/commit/HEAD paths.

Missing lines 653-705:
  653-668: target='HEAD' → revert_to_head succeeds
  669-671: target='HEAD' → revert_to_head raises → error + exit
  673-683: target is branch ID/name → switcher.switch succeeds (Switched/Resumed)
  684-685: switch raises 'Branch not found' + non-branch target → fall through
  687-698: target is commit ID → revert_to_commit succeeds
  699-700: revert_to_commit raises → error + exit
"""
import os
import types as _types

import pytest

from sgit_ai.cli.CLI__Vault             import CLI__Vault
from sgit_ai.cli.CLI__Token_Store       import CLI__Token_Store
from sgit_ai.cli.CLI__Credential_Store  import CLI__Credential_Store
from sgit_ai.crypto.Vault__Crypto       import Vault__Crypto
from sgit_ai.core.actions.revert.Vault__Revert         import Vault__Revert
from sgit_ai.core.actions.branch.Vault__Branch_Switch  import Vault__Branch_Switch
from tests._helpers.vault_test_env      import Vault__Test_Env


class _Args:
    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)


class Test_CLI__Vault__Checkout__Target:

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
        self.cli   = CLI__Vault(token_store=CLI__Token_Store(),
                                credential_store=CLI__Credential_Store())

    def teardown_method(self):
        self.snap.cleanup()

    # ── HEAD path ──────────────────────────────────────────────────────────

    def test_checkout_head_success_lines_659_668(self, monkeypatch, capsys):
        """Lines 659-668: target='HEAD' + revert_to_head succeeds → prints restored."""
        monkeypatch.setattr(Vault__Revert, 'revert_to_head',
                            lambda self, d: dict(commit_id='abc123',
                                                 restored=['f.txt'], deleted=[]))
        self.cli.cmd_checkout(_Args(directory=self.vault, target='HEAD', force=False))
        out = capsys.readouterr().out
        assert 'Restored to HEAD' in out
        assert 'abc123' in out

    def test_checkout_head_lowercase_success(self, monkeypatch, capsys):
        """Lines 659-668: target='head' (lowercase) also triggers HEAD path."""
        monkeypatch.setattr(Vault__Revert, 'revert_to_head',
                            lambda self, d: dict(commit_id='def456',
                                                 restored=[], deleted=['old.txt']))
        self.cli.cmd_checkout(_Args(directory=self.vault, target='head', force=False))
        out = capsys.readouterr().out
        assert 'Restored to HEAD' in out

    def test_checkout_head_raises_exits_lines_669_671(self, monkeypatch, capsys):
        """Lines 669-671: target='HEAD', revert_to_head raises → error + exit."""
        monkeypatch.setattr(Vault__Revert, 'revert_to_head',
                            lambda self, d: (_ for _ in ()).throw(
                                RuntimeError('vault corrupt')))
        with pytest.raises(SystemExit) as exc:
            self.cli.cmd_checkout(_Args(directory=self.vault, target='HEAD', force=False))
        assert exc.value.code == 1
        assert 'vault corrupt' in capsys.readouterr().err

    # ── Branch switch path ─────────────────────────────────────────────────

    def test_checkout_branch_name_switched_lines_673_683(self, monkeypatch, capsys):
        """Lines 673-683: target is branch name → switcher.switch → 'Switched to'."""
        monkeypatch.setattr(Vault__Branch_Switch, 'switch',
                            lambda self, d, t, force=False: dict(
                                named_name='feature', new_clone_branch_id='clone-abc',
                                files_restored=3, reused=False))
        self.cli.cmd_checkout(_Args(directory=self.vault, target='feature', force=False))
        out = capsys.readouterr().out
        assert 'Switched to' in out
        assert 'feature' in out

    def test_checkout_branch_resumed_reused_flag(self, monkeypatch, capsys):
        """Lines 673-683: reused=True → 'Resumed' instead of 'Switched to'."""
        monkeypatch.setattr(Vault__Branch_Switch, 'switch',
                            lambda self, d, t, force=False: dict(
                                named_name='main', new_clone_branch_id='clone-def',
                                files_restored=1, reused=True))
        self.cli.cmd_checkout(_Args(directory=self.vault, target='main', force=False))
        out = capsys.readouterr().out
        assert 'Resumed' in out

    def test_checkout_branch_not_found_exits_non_branch_id(self, monkeypatch, capsys):
        """Line 684-685: switch raises 'Branch not found' with non-branch-id target → error + exit."""
        monkeypatch.setattr(Vault__Branch_Switch, 'switch',
                            lambda self, d, t, force=False: (_ for _ in ()).throw(
                                RuntimeError('Branch not found: feature')))
        # target is a branch-id pattern so _BRANCH_RE.match fires → goes to error path
        with pytest.raises(SystemExit) as exc:
            self.cli.cmd_checkout(_Args(directory=self.vault,
                                        target='branch-named-aabbccdd', force=False))
        assert exc.value.code == 1

    def test_checkout_branch_switch_other_error_exits(self, monkeypatch, capsys):
        """Lines 684: switch raises non-'Branch not found' error → error + exit."""
        monkeypatch.setattr(Vault__Branch_Switch, 'switch',
                            lambda self, d, t, force=False: (_ for _ in ()).throw(
                                RuntimeError('something else broke')))
        with pytest.raises(SystemExit) as exc:
            self.cli.cmd_checkout(_Args(directory=self.vault, target='my-branch', force=False))
        assert exc.value.code == 1
        assert 'something else broke' in capsys.readouterr().err

    # ── Commit revert path ─────────────────────────────────────────────────

    def test_checkout_commit_id_success_lines_687_698(self, monkeypatch, capsys):
        """Lines 687-698: target is hex commit ID → revert_to_commit → 'HEAD detached'."""
        commit_hex = 'a1b2c3d4e5f6'
        monkeypatch.setattr(Vault__Revert, 'revert_to_commit',
                            lambda self, d, t: dict(
                                commit_id=commit_hex, restored=['a.txt'], deleted=[]))
        self.cli.cmd_checkout(_Args(directory=self.vault, target=commit_hex, force=False))
        out = capsys.readouterr().out
        assert 'HEAD detached' in out
        assert commit_hex in out

    def test_checkout_commit_raises_exits_lines_699_700(self, monkeypatch, capsys):
        """Lines 699-700: revert_to_commit raises → error + exit."""
        commit_hex = 'deadbeef1234'
        monkeypatch.setattr(Vault__Revert, 'revert_to_commit',
                            lambda self, d, t: (_ for _ in ()).throw(
                                RuntimeError(f'commit {commit_hex} not found')))
        # Also patch switch so it falls through (Branch not found for non-branch target)
        monkeypatch.setattr(Vault__Branch_Switch, 'switch',
                            lambda self, d, t, force=False: (_ for _ in ()).throw(
                                RuntimeError('Branch not found: deadbeef1234')))
        with pytest.raises(SystemExit) as exc:
            self.cli.cmd_checkout(_Args(directory=self.vault, target=commit_hex, force=False))
        assert exc.value.code == 1
        assert 'not found' in capsys.readouterr().err
