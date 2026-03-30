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
