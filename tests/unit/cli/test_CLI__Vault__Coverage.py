"""Coverage-focused tests for CLI__Vault — commands not yet tested.

Covers: cmd_status variants, cmd_pull variants, cmd_push variants,
        cmd_checkout, cmd_clean, cmd_vault_add/list/remove/show, cmd_fsck,
        cmd_inspect_object/tree/log, cmd_cat_object, cmd_derive_keys.
"""
import os
import sys
import types as _types

import pytest

from sgit_ai.cli.CLI__Vault           import CLI__Vault
from sgit_ai.cli.CLI__Token_Store     import CLI__Token_Store
from sgit_ai.cli.CLI__Credential_Store import CLI__Credential_Store
from sgit_ai.sync.Vault__Sync         import Vault__Sync
from sgit_ai.sync.Vault__Bare         import Vault__Bare
from sgit_ai.objects.Vault__Inspector import Vault__Inspector
from sgit_ai.crypto.Vault__Crypto     import Vault__Crypto
from sgit_ai.api.Vault__API__In_Memory import Vault__API__In_Memory
from tests.unit.sync.vault_test_env   import Vault__Test_Env


def _make_cli(snap=None) -> CLI__Vault:
    cli = CLI__Vault(token_store=CLI__Token_Store(), credential_store=CLI__Credential_Store())
    if snap:
        api, crypto = snap.api, snap.crypto
        def _create_sync(self, base_url=None, access_token=None):
            return Vault__Sync(crypto=crypto, api=api)
        cli.create_sync = _types.MethodType(_create_sync, cli)
    return cli


class _Args:
    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)


# ---------------------------------------------------------------------------
# Shared Vault__Test_Env
# ---------------------------------------------------------------------------

class _VaultTest:
    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_single_vault(files={'f.txt': 'hello'})

    @classmethod
    def teardown_class(cls):
        if cls._env:
            cls._env.cleanup_snapshot()

    def setup_method(self):
        self.snap  = self._env.restore()
        self.vault = self.snap.vault_dir

    def teardown_method(self):
        self.snap.cleanup()


# ---------------------------------------------------------------------------
# cmd_status — various push_status / remote branches
# ---------------------------------------------------------------------------

class Test_CLI__Vault__Status(_VaultTest):

    def _status(self, monkeypatch, **overrides):
        base = dict(clone_branch_id='clone-abc', named_branch_id='named-xyz',
                    push_status='up_to_date', ahead=0, behind=0,
                    remote_configured=True, never_pushed=False, clean=True,
                    added=[], modified=[], deleted=[])
        base.update(overrides)
        monkeypatch.setattr(Vault__Sync, 'status', lambda self, d: base)
        cli = _make_cli()
        return cli

    def test_status_remote_not_configured(self, monkeypatch, capsys):
        cli = self._status(monkeypatch, remote_configured=False)
        cli.cmd_status(_Args(directory=self.vault, explain=False))
        assert 'not configured' in capsys.readouterr().out

    def test_status_up_to_date(self, monkeypatch, capsys):
        cli = self._status(monkeypatch, push_status='up_to_date', remote_configured=True)
        cli.cmd_status(_Args(directory=self.vault, explain=False))
        assert 'in sync' in capsys.readouterr().out

    def test_status_ahead(self, monkeypatch, capsys):
        cli = self._status(monkeypatch, push_status='ahead', ahead=2, remote_configured=True)
        cli.cmd_status(_Args(directory=self.vault, explain=False))
        assert 'ahead' in capsys.readouterr().out

    def test_status_behind(self, monkeypatch, capsys):
        cli = self._status(monkeypatch, push_status='behind', behind=1, remote_configured=True)
        cli.cmd_status(_Args(directory=self.vault, explain=False))
        out = capsys.readouterr().out
        assert 'new commit' in out or 'behind' in out

    def test_status_diverged(self, monkeypatch, capsys):
        cli = self._status(monkeypatch, push_status='diverged', ahead=1, behind=1,
                           remote_configured=True)
        cli.cmd_status(_Args(directory=self.vault, explain=False))
        assert 'diverged' in capsys.readouterr().out

    def test_status_never_pushed(self, monkeypatch, capsys):
        cli = self._status(monkeypatch, never_pushed=True, clone_branch_id='clone-abc')
        cli.cmd_status(_Args(directory=self.vault, explain=False))
        assert 'never been pushed' in capsys.readouterr().out

    def test_status_clean_ahead_with_remote(self, monkeypatch, capsys):
        cli = self._status(monkeypatch, clean=True, push_status='ahead', ahead=1,
                           remote_configured=True)
        cli.cmd_status(_Args(directory=self.vault, explain=False))
        assert 'waiting to be pushed' in capsys.readouterr().out

    def test_status_clean_up_to_date(self, monkeypatch, capsys):
        cli = self._status(monkeypatch, clean=True, push_status='up_to_date',
                           remote_configured=True)
        cli.cmd_status(_Args(directory=self.vault, explain=False))
        assert 'fully in sync' in capsys.readouterr().out

    def test_status_clean_no_remote(self, monkeypatch, capsys):
        cli = self._status(monkeypatch, clean=True, push_status='unknown',
                           remote_configured=False)
        cli.cmd_status(_Args(directory=self.vault, explain=False))
        assert 'clean' in capsys.readouterr().out.lower()

    def test_status_explain_flag(self, monkeypatch, capsys):
        cli = self._status(monkeypatch)
        cli.cmd_status(_Args(directory=self.vault, explain=True))
        assert 'two-branch' in capsys.readouterr().out.lower() or 'sgit' in capsys.readouterr().out


# ---------------------------------------------------------------------------
# cmd_pull — up_to_date, conflicts, merged variants
# ---------------------------------------------------------------------------

class Test_CLI__Vault__Pull(_VaultTest):

    def test_pull_up_to_date(self, monkeypatch, capsys):
        monkeypatch.setattr(Vault__Sync, 'pull',
                            lambda self, d, on_progress=None: dict(status='up_to_date'))
        cli = _make_cli(self.snap)
        cli.cmd_pull(_Args(directory=self.vault, token=None, base_url=None))
        assert 'up to date' in capsys.readouterr().out.lower()

    def test_pull_up_to_date_remote_unreachable(self, monkeypatch, capsys):
        monkeypatch.setattr(Vault__Sync, 'pull',
                            lambda self, d, on_progress=None: dict(
                                status='up_to_date', remote_unreachable=True))
        cli = _make_cli(self.snap)
        cli.cmd_pull(_Args(directory=self.vault, token=None, base_url=None))
        assert 'warning' in capsys.readouterr().out.lower()

    def test_pull_conflicts(self, monkeypatch, capsys):
        monkeypatch.setattr(Vault__Sync, 'pull',
                            lambda self, d, on_progress=None: dict(
                                status='conflicts', conflicts=['a.txt', 'b.txt']))
        cli = _make_cli(self.snap)
        cli.cmd_pull(_Args(directory=self.vault, token=None, base_url=None))
        out = capsys.readouterr().out
        assert 'CONFLICT' in out
        assert 'a.txt' in out

    def test_pull_merged_with_files(self, monkeypatch, capsys):
        monkeypatch.setattr(Vault__Sync, 'pull',
                            lambda self, d, on_progress=None: dict(
                                status='merged', added=['new.txt'], modified=['f.txt'],
                                deleted=['old.txt']))
        cli = _make_cli(self.snap)
        cli.cmd_pull(_Args(directory=self.vault, token=None, base_url=None))
        out = capsys.readouterr().out
        assert '+ new.txt' in out
        assert '~ f.txt' in out
        assert '- old.txt' in out

    def test_pull_merged_zero_changes(self, monkeypatch, capsys):
        monkeypatch.setattr(Vault__Sync, 'pull',
                            lambda self, d, on_progress=None: dict(
                                status='merged', added=[], modified=[], deleted=[]))
        cli = _make_cli(self.snap)
        cli.cmd_pull(_Args(directory=self.vault, token=None, base_url=None))
        out = capsys.readouterr().out
        assert 'no file changes' in out.lower()


# ---------------------------------------------------------------------------
# cmd_push — resynced, up_to_date, pushed_branch_only, normal
# ---------------------------------------------------------------------------

class Test_CLI__Vault__Push(_VaultTest):

    def test_push_resynced(self, monkeypatch, capsys):
        monkeypatch.setattr(Vault__Sync, 'push',
                            lambda self, d, branch_only=False, on_progress=None: dict(
                                status='resynced'))
        cli = _make_cli(self.snap)
        cli.cmd_push(_Args(directory=self.vault, token='tok', base_url=None, branch_only=False))
        assert 're-synced' in capsys.readouterr().out.lower()

    def test_push_up_to_date(self, monkeypatch, capsys):
        monkeypatch.setattr(Vault__Sync, 'push',
                            lambda self, d, branch_only=False, on_progress=None: dict(
                                status='up_to_date'))
        cli = _make_cli(self.snap)
        cli.cmd_push(_Args(directory=self.vault, token='tok', base_url=None, branch_only=False))
        assert 'Nothing to push' in capsys.readouterr().out

    def test_push_pushed_branch_only(self, monkeypatch, capsys):
        monkeypatch.setattr(Vault__Sync, 'push',
                            lambda self, d, branch_only=False, on_progress=None: dict(
                                status='pushed_branch_only',
                                objects_uploaded=5, commits_pushed=1,
                                commit_id='obj-cas-imm-abc', branch_ref_id='ref-pid-xyz'))
        cli = _make_cli(self.snap)
        cli.cmd_push(_Args(directory=self.vault, token='tok', base_url=None, branch_only=False))
        out = capsys.readouterr().out
        assert 'branch only' in out.lower()
        assert '1 commit' in out

    def test_push_normal(self, monkeypatch, capsys):
        monkeypatch.setattr(Vault__Sync, 'push',
                            lambda self, d, branch_only=False, on_progress=None: dict(
                                status='ok', objects_uploaded=3, commits_pushed=2,
                                commit_id='obj-cas-imm-def'))
        cli = _make_cli(self.snap)
        cli.cmd_push(_Args(directory=self.vault, token='tok', base_url=None, branch_only=False))
        out = capsys.readouterr().out
        assert 'Push complete' in out
        assert '2 commit' in out


# ---------------------------------------------------------------------------
# cmd_checkout / cmd_clean (bare vault commands)
# ---------------------------------------------------------------------------

class Test_CLI__Vault__BareOps(_VaultTest):

    def test_cmd_checkout_calls_bare(self, monkeypatch, capsys):
        monkeypatch.setattr(Vault__Bare, 'checkout', lambda self, d, vk: None)
        monkeypatch.setattr(Vault__Bare, 'list_files',
                            lambda self, d, vk: [{'path': 'a.txt', 'size': 10, 'blob_id': 'b1'}])
        cli = _make_cli()
        cli.cmd_checkout(_Args(directory=self.vault, vault_key=self.snap.vault_key))
        out = capsys.readouterr().out
        assert '1 files' in out or '1 file' in out

    def test_cmd_checkout_no_vault_key_exits(self, capsys, tmp_path):
        cli = _make_cli()
        with pytest.raises(SystemExit) as exc:
            cli.cmd_checkout(_Args(directory=str(tmp_path), vault_key=None))
        assert exc.value.code == 1

    def test_cmd_clean_prints_cleaned(self, monkeypatch, capsys):
        monkeypatch.setattr(Vault__Bare, 'clean', lambda self, d: None)
        cli = _make_cli()
        cli.cmd_clean(_Args(directory=self.vault))
        assert 'Cleaned' in capsys.readouterr().out


# ---------------------------------------------------------------------------
# cmd_vault_add / cmd_vault_list / cmd_vault_remove / cmd_vault_show
# ---------------------------------------------------------------------------

class Test_CLI__Vault__CredOps(_VaultTest):

    def test_cmd_vault_add(self, monkeypatch, capsys):
        monkeypatch.setattr('sgit_ai.cli.CLI__Credential_Store.CLI__Credential_Store._prompt_passphrase',
                            lambda self, confirm=False: 'test-pass')
        monkeypatch.setattr('getpass.getpass', lambda prompt='': 'vault-key:id')
        cli = _make_cli()
        cli.setup_credential_store(sg_send_dir=os.path.join(self.vault, '.sg_vault', 'local'))
        cli.cmd_vault_add(_Args(alias='my-vault', vault_key=None))
        assert 'my-vault' in capsys.readouterr().out

    def test_cmd_vault_list_empty(self, monkeypatch, capsys):
        monkeypatch.setattr('sgit_ai.cli.CLI__Credential_Store.CLI__Credential_Store._prompt_passphrase',
                            lambda self, confirm=False: 'pass')
        monkeypatch.setattr('sgit_ai.cli.CLI__Credential_Store.CLI__Credential_Store.list_vaults',
                            lambda self, pp: [])
        cli = _make_cli()
        cli.cmd_vault_list(_Args())
        assert 'No stored vaults' in capsys.readouterr().out

    def test_cmd_vault_list_shows_aliases(self, monkeypatch, capsys):
        monkeypatch.setattr('sgit_ai.cli.CLI__Credential_Store.CLI__Credential_Store._prompt_passphrase',
                            lambda self, confirm=False: 'pass')
        monkeypatch.setattr('sgit_ai.cli.CLI__Credential_Store.CLI__Credential_Store.list_vaults',
                            lambda self, pp: ['prod-vault', 'dev-vault'])
        cli = _make_cli()
        cli.cmd_vault_list(_Args())
        out = capsys.readouterr().out
        assert 'prod-vault' in out
        assert 'dev-vault' in out

    def test_cmd_vault_remove_found(self, monkeypatch, capsys):
        monkeypatch.setattr('sgit_ai.cli.CLI__Credential_Store.CLI__Credential_Store._prompt_passphrase',
                            lambda self, confirm=False: 'pass')
        monkeypatch.setattr('sgit_ai.cli.CLI__Credential_Store.CLI__Credential_Store.remove_vault',
                            lambda self, pp, alias: True)
        cli = _make_cli()
        cli.cmd_vault_remove(_Args(alias='my-vault'))
        assert 'Removed' in capsys.readouterr().out

    def test_cmd_vault_remove_not_found(self, monkeypatch, capsys):
        monkeypatch.setattr('sgit_ai.cli.CLI__Credential_Store.CLI__Credential_Store._prompt_passphrase',
                            lambda self, confirm=False: 'pass')
        monkeypatch.setattr('sgit_ai.cli.CLI__Credential_Store.CLI__Credential_Store.remove_vault',
                            lambda self, pp, alias: False)
        cli = _make_cli()
        cli.cmd_vault_remove(_Args(alias='ghost'))
        assert 'No vault found' in capsys.readouterr().out

    def test_cmd_vault_show_found(self, monkeypatch, capsys):
        monkeypatch.setattr('sgit_ai.cli.CLI__Credential_Store.CLI__Credential_Store._prompt_passphrase',
                            lambda self, confirm=False: 'pass')
        monkeypatch.setattr('sgit_ai.cli.CLI__Credential_Store.CLI__Credential_Store.get_vault_key',
                            lambda self, pp, alias: 'key123:vaultabc')
        cli = _make_cli()
        cli.cmd_vault_show(_Args(alias='my-vault'))
        assert 'key123:vaultabc' in capsys.readouterr().out

    def test_cmd_vault_show_not_found(self, monkeypatch, capsys):
        monkeypatch.setattr('sgit_ai.cli.CLI__Credential_Store.CLI__Credential_Store._prompt_passphrase',
                            lambda self, confirm=False: 'pass')
        monkeypatch.setattr('sgit_ai.cli.CLI__Credential_Store.CLI__Credential_Store.get_vault_key',
                            lambda self, pp, alias: None)
        cli = _make_cli()
        cli.cmd_vault_show(_Args(alias='ghost'))
        assert 'No vault found' in capsys.readouterr().out


# ---------------------------------------------------------------------------
# cmd_fsck
# ---------------------------------------------------------------------------

class Test_CLI__Vault__Fsck(_VaultTest):

    def test_fsck_ok(self, monkeypatch, capsys):
        monkeypatch.setattr(Vault__Sync, 'fsck',
                            lambda self, d, repair=False, on_progress=None: dict(
                                ok=True, missing=[], corrupt=[], errors=[], repaired=[]))
        cli = _make_cli(self.snap)
        cli.cmd_fsck(_Args(directory=self.vault, token=None, base_url=None, repair=False))
        assert 'Vault OK' in capsys.readouterr().out

    def test_fsck_with_missing_objects(self, monkeypatch, capsys):
        monkeypatch.setattr(Vault__Sync, 'fsck',
                            lambda self, d, repair=False, on_progress=None: dict(
                                ok=False, missing=['obj-1', 'obj-2'], corrupt=[], errors=[],
                                repaired=[]))
        cli = _make_cli(self.snap)
        cli.cmd_fsck(_Args(directory=self.vault, token=None, base_url=None, repair=False))
        out = capsys.readouterr().out
        assert 'Missing' in out
        assert 'Vault has problems' in out

    def test_fsck_with_corrupt_objects(self, monkeypatch, capsys):
        monkeypatch.setattr(Vault__Sync, 'fsck',
                            lambda self, d, repair=False, on_progress=None: dict(
                                ok=False, missing=[], corrupt=['obj-bad'], errors=[],
                                repaired=[]))
        cli = _make_cli(self.snap)
        cli.cmd_fsck(_Args(directory=self.vault, token=None, base_url=None, repair=False))
        out = capsys.readouterr().out
        assert 'Corrupt' in out

    def test_fsck_with_errors(self, monkeypatch, capsys):
        monkeypatch.setattr(Vault__Sync, 'fsck',
                            lambda self, d, repair=False, on_progress=None: dict(
                                ok=False, missing=[], corrupt=[], errors=['some error'],
                                repaired=[]))
        cli = _make_cli(self.snap)
        cli.cmd_fsck(_Args(directory=self.vault, token=None, base_url=None, repair=False))
        assert 'Errors' in capsys.readouterr().out

    def test_fsck_repaired(self, monkeypatch, capsys):
        monkeypatch.setattr(Vault__Sync, 'fsck',
                            lambda self, d, repair=False, on_progress=None: dict(
                                ok=True, missing=[], corrupt=[], errors=[],
                                repaired=['obj-1']))
        cli = _make_cli(self.snap)
        cli.cmd_fsck(_Args(directory=self.vault, token=None, base_url=None, repair=True))
        assert 'Repaired' in capsys.readouterr().out


# ---------------------------------------------------------------------------
# Inspector commands
# ---------------------------------------------------------------------------

class Test_CLI__Vault__Inspector(_VaultTest):

    def test_cmd_inspect_object(self, monkeypatch, capsys):
        monkeypatch.setattr(Vault__Inspector, 'format_object_detail',
                            lambda self, d, oid: f'Object detail for {oid}')
        cli = _make_cli()
        cli.cmd_inspect_object(_Args(directory=self.vault, object_id='obj-abc'))
        assert 'obj-abc' in capsys.readouterr().out

    def test_cmd_inspect_tree_with_entries(self, monkeypatch, capsys):
        monkeypatch.setattr(Vault__Inspector, 'inspect_tree',
                            lambda self, d, read_key=None: dict(
                                error=None, entries=[
                                    dict(blob_id='b1', size=100, path='f.txt')
                                ], commit_id='cid-abc', tree_id='tid-xyz',
                                file_count=1, total_size=100))
        cli = _make_cli()
        cli.cmd_inspect_tree(_Args(directory=self.vault, vault_key=None))
        out = capsys.readouterr().out
        assert 'f.txt' in out

    def test_cmd_inspect_tree_error(self, monkeypatch, capsys):
        monkeypatch.setattr(Vault__Inspector, 'inspect_tree',
                            lambda self, d, read_key=None: dict(error='no commits found'))
        cli = _make_cli()
        cli.cmd_inspect_tree(_Args(directory=self.vault, vault_key=None))
        assert 'Error' in capsys.readouterr().out

    def test_cmd_inspect_tree_no_entries(self, monkeypatch, capsys):
        monkeypatch.setattr(Vault__Inspector, 'inspect_tree',
                            lambda self, d, read_key=None: dict(
                                error=None, entries=[], commit_id='cid', tree_id='tid',
                                file_count=0, total_size=0))
        cli = _make_cli()
        cli.cmd_inspect_tree(_Args(directory=self.vault, vault_key=None))
        assert 'no tree entries' in capsys.readouterr().out

    def test_cmd_cat_object_no_read_key(self, capsys, tmp_path):
        """cmd_cat_object with no vault_key → prints error, sys.exit(1)."""
        cli = _make_cli()
        # tmp_path has no .sg_vault/local/vault_key → resolve_read_key returns None
        with pytest.raises(SystemExit) as exc:
            cli.cmd_cat_object(_Args(directory=str(tmp_path), object_id='obj-abc',
                                     vault_key=None))
        assert exc.value.code == 1

    def test_cmd_derive_keys_prints_vault_id(self, capsys):
        cli = _make_cli()
        vault_key = self.snap.vault_key
        cli.cmd_derive_keys(_Args(vault_key=vault_key))
        out = capsys.readouterr().out
        assert 'vault_id' in out
        assert 'read_key' in out

    def test_cmd_cat_object_success(self, monkeypatch, capsys):
        """cmd_cat_object with valid read_key calls format_cat_object."""
        monkeypatch.setattr(Vault__Inspector, 'format_cat_object',
                            lambda self, d, oid, rk: f'Content of {oid}')
        cli = _make_cli()
        cli.cmd_cat_object(_Args(directory=self.vault, object_id='obj-abc',
                                  vault_key=self.snap.vault_key))
        assert 'obj-abc' in capsys.readouterr().out


# ---------------------------------------------------------------------------
# cmd_status — else branch (line 249)
# ---------------------------------------------------------------------------

class Test_CLI__Vault__StatusElse(_VaultTest):

    def test_status_unknown_push_status_prints_unknown(self, monkeypatch, capsys):
        """push_status not matching any known value → 'status unknown'."""
        monkeypatch.setattr(Vault__Sync, 'status', lambda self, d: dict(
            clone_branch_id='clone-x', named_branch_id='named-y',
            push_status='some_unexpected_status', ahead=0, behind=0,
            remote_configured=True, never_pushed=False, clean=True,
            added=[], modified=[], deleted=[]))
        cli = _make_cli()
        cli.cmd_status(_Args(directory=self.vault, explain=False))
        assert 'unknown' in capsys.readouterr().out.lower()


# ---------------------------------------------------------------------------
# cmd_fsck hint line (line 683)
# ---------------------------------------------------------------------------

class Test_CLI__Vault__FsckHint(_VaultTest):

    def test_fsck_problems_no_repair_shows_hint(self, monkeypatch, capsys):
        """When vault has problems and repair=False, hint is shown."""
        monkeypatch.setattr(Vault__Sync, 'fsck',
                            lambda self, d, repair=False, on_progress=None: dict(
                                ok=False, missing=[], corrupt=[], errors=['some issue'],
                                repaired=[]))
        cli = _make_cli(self.snap)
        cli.cmd_fsck(_Args(directory=self.vault, token=None, base_url=None, repair=False))
        out = capsys.readouterr().out
        assert '--repair' in out


# ---------------------------------------------------------------------------
# cmd_push — _prompt_remote_setup (lines 393-429) — non-TTY path
# ---------------------------------------------------------------------------

class Test_CLI__Vault__PushNoToken(_VaultTest):

    def test_push_no_token_non_tty_exits(self, monkeypatch, capsys):
        """When no token and stdin is not a TTY, _prompt_remote_setup exits."""
        # No saved token → create_sync is called, then push, but _prompt_remote_setup
        # is triggered first when token is None
        # We need token_store to return no token
        cli = _make_cli(self.snap)   # snap has API but no saved token
        # Remove any saved token
        monkeypatch.setattr(CLI__Token_Store, 'resolve_token', lambda self, t, d: '')
        monkeypatch.setattr(CLI__Token_Store, 'resolve_base_url', lambda self, b, d: '')
        # stdin is not a TTY in tests → _prompt_remote_setup exits immediately
        with pytest.raises(SystemExit) as exc:
            cli.cmd_push(_Args(directory=self.vault, token=None, base_url=None, branch_only=False))
        assert exc.value.code == 1
        assert 'access token' in capsys.readouterr().err.lower()


# ---------------------------------------------------------------------------
# CLI__Vault cmd_share (simple_token vault) — lines 439-488
# ---------------------------------------------------------------------------

class Test_CLI__Vault__ShareSimpleToken(_VaultTest):

    def _make_config(self, directory, mode='simple_token', share_token=None):
        import json, os
        local_dir = os.path.join(directory, '.sg_vault', 'local')
        os.makedirs(local_dir, exist_ok=True)
        cfg = dict(mode=mode, my_branch_id='branch-x')
        if share_token:
            cfg['share_token'] = share_token
        with open(os.path.join(local_dir, 'config.json'), 'w') as f:
            json.dump(cfg, f)

    def test_cmd_share_not_vault_dir_exits(self, capsys, tmp_path):
        """Directory without config.json → exits with error."""
        cli = _make_cli()
        with pytest.raises(SystemExit) as exc:
            cli.cmd_share(_Args(directory=str(tmp_path), rotate=False,
                                 token=None, base_url=None))
        assert exc.value.code == 1

    def test_cmd_share_non_simple_token_exits(self, capsys):
        """Vault with mode='normal' → exits with error."""
        self._make_config(self.vault, mode='normal')
        cli = _make_cli()
        with pytest.raises(SystemExit) as exc:
            cli.cmd_share(_Args(directory=self.vault, rotate=False,
                                 token=None, base_url=None))
        assert exc.value.code == 1
        assert 'simple_token' in capsys.readouterr().err

    def test_cmd_share_simple_token_vault(self, monkeypatch, capsys):
        """Simple_token vault publishes successfully."""
        from sgit_ai.transfer.Vault__Transfer import Vault__Transfer
        self._make_config(self.vault, mode='simple_token')
        monkeypatch.setattr(CLI__Vault, 'create_transfer_api',
                            lambda self, base_url=None: None)
        monkeypatch.setattr(Vault__Transfer, '__init__', lambda self, api=None, crypto=None: None)
        monkeypatch.setattr(Vault__Transfer, 'share',
                            lambda self, d, token_str=None: dict(
                                transfer_id='xfer-001', file_count=2, total_bytes=1024))
        cli = _make_cli()
        cli.cmd_share(_Args(directory=self.vault, rotate=False, token='cold-idle-1234',
                             base_url=None))
        out = capsys.readouterr().out
        assert 'Published' in out
        assert 'cold-idle-1234' in out

    def test_cmd_share_with_existing_share_token(self, monkeypatch, capsys):
        """When share_token already in config and rotate=False, uses existing token."""
        from sgit_ai.transfer.Vault__Transfer import Vault__Transfer
        self._make_config(self.vault, mode='simple_token', share_token='existing-token')
        monkeypatch.setattr(CLI__Vault, 'create_transfer_api',
                            lambda self, base_url=None: None)
        monkeypatch.setattr(Vault__Transfer, '__init__', lambda self, api=None, crypto=None: None)
        monkeypatch.setattr(Vault__Transfer, 'share',
                            lambda self, d, token_str=None: dict(
                                transfer_id='xfer-002', file_count=1, total_bytes=512))
        cli = _make_cli()
        cli.cmd_share(_Args(directory=self.vault, rotate=False, token=None, base_url=None))
        out = capsys.readouterr().out
        assert 'existing-token' in out


# ---------------------------------------------------------------------------
# CLI__Vault create_transfer_api (lines 432-435)
# ---------------------------------------------------------------------------

class Test_CLI__Vault__CreateTransferApi(_VaultTest):

    def test_create_transfer_api_returns_api(self):
        from sgit_ai.api.API__Transfer import API__Transfer
        cli = _make_cli()
        # Monkeypatch api.setup() to avoid network call
        orig_setup = API__Transfer.setup
        API__Transfer.setup = lambda self: self
        try:
            api = cli.create_transfer_api()
            assert api is not None
        finally:
            API__Transfer.setup = orig_setup


# ---------------------------------------------------------------------------
# cmd_init — simple_token mode, restore mode, existing directory
# ---------------------------------------------------------------------------

class Test_CLI__Vault__Init:

    def test_cmd_init_simple_token_directory(self, monkeypatch, capsys, tmp_path):
        """When directory is a simple token, cmd_init uses it as vault_key."""
        token = 'coral-equal-1234'
        monkeypatch.setattr(Vault__Sync, 'init',
                            lambda self, d, vault_key=None, allow_nonempty=False, token=None: dict(
                                vault_id=token, vault_key=None, directory=str(tmp_path / token),
                                branch_id='branch-xyz'))
        # Ensure the directory doesn't already exist with files
        cli = _make_cli()
        cli.cmd_init(_Args(directory=token, vault_key=None, restore=False, existing=False,
                           token=None))
        out = capsys.readouterr().out
        assert 'Edit token' in out or 'Vault created' in out

    def test_cmd_init_restore_no_backup_exits(self, capsys, tmp_path):
        """--restore with no .vault__*.zip → exits with error."""
        cli = _make_cli()
        with pytest.raises(SystemExit) as exc:
            cli.cmd_init(_Args(directory=str(tmp_path), vault_key=None, restore=True,
                                existing=False, token=None))
        assert exc.value.code == 1
        assert 'no vault backup' in capsys.readouterr().err

    def test_cmd_init_restore_cancelled(self, monkeypatch, capsys, tmp_path):
        """--restore with zip found but user says N → prints 'Restore cancelled'."""
        import zipfile
        # Create a fake .vault__test__123.zip
        zip_path = tmp_path / '.vault__test__123.zip'
        with zipfile.ZipFile(str(zip_path), 'w') as z:
            z.writestr('placeholder', 'data')
        monkeypatch.setattr('sgit_ai.cli.CLI__Input.CLI__Input.prompt', lambda self, msg: None)
        cli = _make_cli()
        cli.cmd_init(_Args(directory=str(tmp_path), vault_key=None, restore=True,
                            existing=False, token=None))
        assert 'cancelled' in capsys.readouterr().out.lower()

    def test_cmd_init_restore_succeeds(self, monkeypatch, capsys, tmp_path):
        """--restore with zip found and user confirms → calls restore_from_backup."""
        import zipfile
        zip_path = tmp_path / '.vault__test__456.zip'
        with zipfile.ZipFile(str(zip_path), 'w') as z:
            z.writestr('placeholder', 'data')
        monkeypatch.setattr('sgit_ai.cli.CLI__Input.CLI__Input.prompt', lambda self, msg: 'y')
        monkeypatch.setattr(Vault__Sync, 'restore_from_backup',
                            lambda self, zp, sd: dict(vault_id='vid-abc', branch_id='br-xyz'))
        cli = _make_cli()
        cli.cmd_init(_Args(directory=str(tmp_path), vault_key=None, restore=True,
                            existing=False, token=None))
        out = capsys.readouterr().out
        assert 'Vault restored' in out

    def test_cmd_init_auto_generate_simple_token(self, monkeypatch, capsys, tmp_path):
        """Bare `sgit init` with empty directory auto-generates a simple token."""
        generated_token = 'auto-gen-1234'
        from sgit_ai.transfer.Simple_Token__Wordlist import Simple_Token__Wordlist
        monkeypatch.setattr(Simple_Token__Wordlist, 'generate',
                            lambda self: generated_token)
        monkeypatch.setattr(Vault__Sync, 'init',
                            lambda self, d, vault_key=None, allow_nonempty=False, token=None: dict(
                                vault_id=generated_token, vault_key=None,
                                directory=d, branch_id='br-abc'))
        cli = _make_cli()
        # Use directory='' to trigger the auto-generate path without non-empty check
        cli.cmd_init(_Args(directory='', vault_key=None, restore=False,
                            existing=False, token=None))
        out = capsys.readouterr().out
        assert 'Vault created' in out

    def test_cmd_init_existing_non_empty_prompt_proceeds(self, monkeypatch, capsys, tmp_path):
        """Non-empty directory with prompt 'y' → existing=True, proceeds."""
        # Create a file in the directory
        (tmp_path / 'readme.txt').write_text('hello')
        # Two prompts: (1) "init anyway?" → 'y'; (2) "commit now?" → 'n'
        responses = iter(['y', 'n'])
        monkeypatch.setattr('sgit_ai.cli.CLI__Input.CLI__Input.prompt',
                            lambda self, msg: next(responses))
        monkeypatch.setattr(Vault__Sync, 'init',
                            lambda self, d, vault_key=None, allow_nonempty=False, token=None: dict(
                                vault_id='vid-xyz', vault_key='key:vid-xyz',
                                directory=str(tmp_path), branch_id='br-def'))
        cli = _make_cli()
        cli.cmd_init(_Args(directory=str(tmp_path), vault_key=None, restore=False,
                            existing=False, token=None))
        out = capsys.readouterr().out
        assert 'Vault created' in out

    def test_cmd_init_existing_prompt_cancelled(self, monkeypatch, capsys, tmp_path):
        """Non-empty directory with prompt None → prints 'Init cancelled'."""
        (tmp_path / 'readme.txt').write_text('hello')
        monkeypatch.setattr('sgit_ai.cli.CLI__Input.CLI__Input.prompt', lambda self, msg: None)
        cli = _make_cli()
        cli.cmd_init(_Args(directory=str(tmp_path), vault_key=None, restore=False,
                            existing=False, token=None))
        assert 'cancelled' in capsys.readouterr().out.lower()

    def test_cmd_init_vault_key_is_simple_token(self, monkeypatch, capsys, tmp_path):
        """When vault_key is a simple token, uses it as init_token."""
        token = 'word-word-1234'
        target_dir = str(tmp_path / token)
        monkeypatch.setattr(Vault__Sync, 'init',
                            lambda self, d, vault_key=None, allow_nonempty=False, token=None: dict(
                                vault_id=token, vault_key=None, directory=target_dir,
                                branch_id='br-ghi'))
        cli = _make_cli()
        cli.cmd_init(_Args(directory=target_dir, vault_key=token, restore=False,
                            existing=False, token=None))
        out = capsys.readouterr().out
        assert 'Vault created' in out

    def test_cmd_init_existing_commit_proceeds(self, monkeypatch, capsys, tmp_path):
        """Lines 177-178: commit prompt returns 'y' → sync.commit is called."""
        (tmp_path / 'readme.txt').write_text('hello')
        # Two prompts: (1) "init anyway?" → 'y'; (2) "commit now?" → 'y'
        responses = iter(['y', 'y'])
        monkeypatch.setattr('sgit_ai.cli.CLI__Input.CLI__Input.prompt',
                            lambda self, msg: next(responses))
        monkeypatch.setattr(Vault__Sync, 'init',
                            lambda self, d, vault_key=None, allow_nonempty=False, token=None: dict(
                                vault_id='vid-commit', vault_key='key:vid-commit',
                                directory=str(tmp_path), branch_id='br-commit'))
        monkeypatch.setattr(Vault__Sync, 'commit',
                            lambda self, d, message='': dict(files_changed=3))
        cli = _make_cli()
        cli.cmd_init(_Args(directory=str(tmp_path), vault_key=None, restore=False,
                            existing=False, token=None))
        out = capsys.readouterr().out
        assert 'Committed' in out


# ---------------------------------------------------------------------------
# CLI__Vault cmd_share — non-simple-token exits (line 469)
# ---------------------------------------------------------------------------

class Test_CLI__Vault__ShareAutoToken(_VaultTest):

    def _make_config(self, directory, mode='simple_token', **extra):
        import json, os
        local_dir = os.path.join(directory, '.sg_vault', 'local')
        os.makedirs(local_dir, exist_ok=True)
        with open(os.path.join(local_dir, 'config.json'), 'w') as f:
            json.dump(dict(mode=mode, **extra), f)

    def test_cmd_share_auto_generates_token(self, monkeypatch, capsys):
        """Line 469: no token_str and no share_token → auto-generates token."""
        from sgit_ai.transfer.Vault__Transfer import Vault__Transfer
        self._make_config(self.vault, mode='simple_token')  # no share_token
        monkeypatch.setattr(CLI__Vault, 'create_transfer_api',
                            lambda self, base_url=None: None)
        monkeypatch.setattr(Vault__Transfer, '__init__', lambda self, api=None, crypto=None: None)
        monkeypatch.setattr(Vault__Transfer, 'share',
                            lambda self, d, token_str=None: dict(
                                transfer_id='xfer-003', file_count=1, total_bytes=256))
        cli = _make_cli()
        # token=None, rotate=False, no share_token in config → auto-generate
        cli.cmd_share(_Args(directory=self.vault, rotate=False, token=None, base_url=None))
        out = capsys.readouterr().out
        assert 'Published' in out


# ---------------------------------------------------------------------------
# CLI__Vault cmd_fsck — >10 missing objects (line 683)
# ---------------------------------------------------------------------------

class Test_CLI__Vault__FsckManyMissing(_VaultTest):

    def test_fsck_more_than_10_missing(self, monkeypatch, capsys):
        """Line 683: >10 missing objects → prints '... and N more'."""
        missing = [f'obj{i:03d}' for i in range(15)]
        monkeypatch.setattr(Vault__Sync, 'fsck',
                            lambda self, d, repair=False, on_progress=None: dict(
                                ok=False, missing=missing, corrupt=[], errors=[],
                                repaired=[]))
        cli = _make_cli(self.snap)
        cli.cmd_fsck(_Args(directory=self.vault, token=None, base_url=None, repair=False))
        out = capsys.readouterr().out
        assert 'and' in out and 'more' in out


# ---------------------------------------------------------------------------
# cmd_clone — lines 37, 47, 49
# ---------------------------------------------------------------------------

class Test_CLI__Vault__CloneCoverage:

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

    def test_cmd_clone_simple_token_auto_directory(self, monkeypatch, capsys, tmp_path):
        """Line 37: vault_key is a simple token and directory is empty → directory = token_str."""
        import types as _types
        from sgit_ai.sync.Vault__Sync import Vault__Sync
        token_str = 'word-word-1234'
        target = str(tmp_path / token_str)
        clone_result = dict(directory=target, vault_id='vid-abc',
                            share_token=None, branch_id='br-x', commit_id='c-abc')
        monkeypatch.setattr(Vault__Sync, 'clone',
                            lambda self, vk, d, on_progress=None: clone_result)
        cli = _make_cli(self.snap)
        args = _Args(vault_key=token_str, directory='', token=None, base_url=None)
        cli.cmd_clone(args)
        out = capsys.readouterr().out
        assert 'Cloned into' in out

    def test_cmd_clone_saves_token_when_provided(self, monkeypatch, capsys, tmp_path):
        """Line 47: token is provided → token_store.save_token is called."""
        import types as _types
        from sgit_ai.sync.Vault__Sync import Vault__Sync
        target = str(tmp_path / 'cloned')
        clone_result = dict(directory=target, vault_id='vid-abc',
                            share_token=None, branch_id='br-x', commit_id='c-abc')
        monkeypatch.setattr(Vault__Sync, 'clone',
                            lambda self, vk, d, on_progress=None: clone_result)
        saved = {}
        monkeypatch.setattr(CLI__Token_Store, 'save_token',
                            lambda self, t, d: saved.update({'token': t, 'dir': d}))
        monkeypatch.setattr(CLI__Token_Store, 'save_base_url', lambda self, u, d: None)
        cli = _make_cli(self.snap)
        args = _Args(vault_key=self.snap.vault_key, directory=target,
                     token='my-token', base_url=None)
        cli.cmd_clone(args)
        assert saved.get('token') == 'my-token'

    def test_cmd_clone_saves_base_url_when_effective(self, monkeypatch, capsys, tmp_path):
        """Line 49: effective_base_url is non-empty → token_store.save_base_url is called."""
        import types as _types
        from sgit_ai.sync.Vault__Sync import Vault__Sync
        from sgit_ai.api.Vault__API import Vault__API, DEFAULT_BASE_URL
        target = str(tmp_path / 'cloned2')
        clone_result = dict(directory=target, vault_id='vid-abc',
                            share_token=None, branch_id='br-x', commit_id='c-abc')
        # Patch clone to also set api.base_url on the sync object
        def _fake_clone(self_sync, vk, d, on_progress=None):
            self_sync.api.base_url = DEFAULT_BASE_URL
            return clone_result
        monkeypatch.setattr(Vault__Sync, 'clone', _fake_clone)
        saved = {}
        monkeypatch.setattr(CLI__Token_Store, 'save_token', lambda self, t, d: None)
        monkeypatch.setattr(CLI__Token_Store, 'save_base_url',
                            lambda self, u, d: saved.update({'url': u, 'dir': d}))
        cli = _make_cli(self.snap)
        args = _Args(vault_key=self.snap.vault_key, directory=target,
                     token=None, base_url=None)
        cli.cmd_clone(args)
        assert 'url' in saved


# ---------------------------------------------------------------------------
# _prompt_remote_setup — TTY path (lines 393-429)
# ---------------------------------------------------------------------------

class Test_CLI__Vault__PromptRemoteSetup(_VaultTest):

    def _tty_setup(self, monkeypatch):
        """Patch stdin.isatty() to simulate a TTY environment."""
        import sys
        monkeypatch.setattr(sys.stdin, 'isatty', lambda: True)

    def test_prompt_url_cancelled_exits(self, monkeypatch, capsys):
        """Lines 398-400: URL prompt returns None → sys.exit(1)."""
        self._tty_setup(monkeypatch)
        monkeypatch.setattr('sgit_ai.cli.CLI__Input.CLI__Input.prompt', lambda self, msg: None)
        cli = _make_cli()
        with pytest.raises(SystemExit) as exc:
            cli._prompt_remote_setup(self.vault, base_url=None)
        assert exc.value.code == 1
        assert 'cancelled' in capsys.readouterr().err

    def test_prompt_token_cancelled_exits(self, monkeypatch, capsys):
        """Lines 404-406: token prompt returns None → sys.exit(1)."""
        self._tty_setup(monkeypatch)
        responses = iter(['https://example.com', None])
        monkeypatch.setattr('sgit_ai.cli.CLI__Input.CLI__Input.prompt',
                            lambda self, msg: next(responses))
        cli = _make_cli()
        with pytest.raises(SystemExit) as exc:
            cli._prompt_remote_setup(self.vault, base_url=None)
        assert exc.value.code == 1
        assert 'cancelled' in capsys.readouterr().err

    def test_prompt_empty_token_exits(self, monkeypatch, capsys):
        """Lines 408-410: token is empty string → sys.exit(1)."""
        self._tty_setup(monkeypatch)
        responses = iter(['https://example.com', '   '])
        monkeypatch.setattr('sgit_ai.cli.CLI__Input.CLI__Input.prompt',
                            lambda self, msg: next(responses))
        cli = _make_cli()
        with pytest.raises(SystemExit) as exc:
            cli._prompt_remote_setup(self.vault, base_url=None)
        assert exc.value.code == 1
        assert 'required' in capsys.readouterr().err

    def test_prompt_success_returns_token_and_url(self, monkeypatch, capsys):
        """Lines 425-429: successful setup returns (token, base_url)."""
        self._tty_setup(monkeypatch)
        responses = iter(['https://sgit.example.com', 'my-access-token'])
        monkeypatch.setattr('sgit_ai.cli.CLI__Input.CLI__Input.prompt',
                            lambda self, msg: next(responses))
        from sgit_ai.api.Vault__API import Vault__API
        monkeypatch.setattr(Vault__API, 'setup', lambda self: None)
        monkeypatch.setattr(Vault__API, 'list_files', lambda self, vid: [])
        monkeypatch.setattr(CLI__Token_Store, 'save_token', lambda self, t, d: None)
        monkeypatch.setattr(CLI__Token_Store, 'save_base_url', lambda self, u, d: None)
        cli = _make_cli()
        token, url = cli._prompt_remote_setup(self.vault, base_url=None)
        assert token == 'my-access-token'
        assert url == 'https://sgit.example.com'
        assert 'Remote:' in capsys.readouterr().out

    def test_prompt_token_verify_exception_silenced(self, monkeypatch, capsys):
        """Lines 422-423: api.list_files raises → warning printed, export continues."""
        self._tty_setup(monkeypatch)
        responses = iter(['https://sgit.example.com', 'bad-token'])
        monkeypatch.setattr('sgit_ai.cli.CLI__Input.CLI__Input.prompt',
                            lambda self, msg: next(responses))
        from sgit_ai.api.Vault__API import Vault__API
        monkeypatch.setattr(Vault__API, 'setup', lambda self: None)
        monkeypatch.setattr(Vault__API, 'list_files',
                            lambda self, vid: (_ for _ in ()).throw(RuntimeError('auth failed')))
        monkeypatch.setattr(CLI__Token_Store, 'save_token', lambda self, t, d: None)
        monkeypatch.setattr(CLI__Token_Store, 'save_base_url', lambda self, u, d: None)
        cli = _make_cli()
        token, url = cli._prompt_remote_setup(self.vault, base_url=None)
        assert token == 'bad-token'
        err = capsys.readouterr().err
        assert 'Warning' in err

    def test_prompt_with_base_url_skips_url_prompt(self, monkeypatch, capsys):
        """Line 396: base_url already provided → URL prompt is skipped."""
        self._tty_setup(monkeypatch)
        responses = iter(['my-access-token'])
        monkeypatch.setattr('sgit_ai.cli.CLI__Input.CLI__Input.prompt',
                            lambda self, msg: next(responses))
        from sgit_ai.api.Vault__API import Vault__API
        monkeypatch.setattr(Vault__API, 'setup', lambda self: None)
        monkeypatch.setattr(Vault__API, 'list_files', lambda self, vid: [])
        monkeypatch.setattr(CLI__Token_Store, 'save_token', lambda self, t, d: None)
        monkeypatch.setattr(CLI__Token_Store, 'save_base_url', lambda self, u, d: None)
        cli = _make_cli()
        token, url = cli._prompt_remote_setup(self.vault, base_url='https://provided.example.com')
        assert token == 'my-access-token'
        assert url == 'https://provided.example.com'

    def test_prompt_empty_url_uses_default(self, monkeypatch, capsys):
        """Line 401: user presses Enter for URL → uses DEFAULT_BASE_URL."""
        self._tty_setup(monkeypatch)
        from sgit_ai.api.Vault__API import DEFAULT_BASE_URL
        responses = iter(['', 'my-token'])
        monkeypatch.setattr('sgit_ai.cli.CLI__Input.CLI__Input.prompt',
                            lambda self, msg: next(responses))
        from sgit_ai.api.Vault__API import Vault__API
        monkeypatch.setattr(Vault__API, 'setup', lambda self: None)
        monkeypatch.setattr(Vault__API, 'list_files', lambda self, vid: [])
        monkeypatch.setattr(CLI__Token_Store, 'save_token', lambda self, t, d: None)
        monkeypatch.setattr(CLI__Token_Store, 'save_base_url', lambda self, u, d: None)
        cli = _make_cli()
        token, url = cli._prompt_remote_setup(self.vault, base_url=None)
        assert url == DEFAULT_BASE_URL
