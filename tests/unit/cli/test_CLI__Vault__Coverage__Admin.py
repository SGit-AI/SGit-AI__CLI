"""Coverage tests for CLI__Vault admin commands not covered by existing tests.

Covers: cmd_probe, cmd_uninit, cmd_delete_on_remote, cmd_commit (nothing-to-commit),
        cmd_reset, cmd_rekey, cmd_rekey_check, cmd_rekey_wipe, cmd_rekey_init,
        cmd_rekey_commit, cmd_derive_keys (simple token), cmd_ls, cmd_fetch,
        cmd_clone (read-only path).
"""
import os
import sys
import types as _types

import pytest

from sgit_ai.cli.CLI__Vault            import CLI__Vault
from sgit_ai.cli.CLI__Token_Store      import CLI__Token_Store
from sgit_ai.cli.CLI__Credential_Store import CLI__Credential_Store
from sgit_ai.core.Vault__Sync          import Vault__Sync
from sgit_ai.crypto.Vault__Crypto      import Vault__Crypto
from sgit_ai.api.Vault__API__In_Memory import Vault__API__In_Memory
from tests._helpers.vault_test_env     import Vault__Test_Env


def _make_cli(snap=None, api=None, crypto=None) -> CLI__Vault:
    cli = CLI__Vault(token_store=CLI__Token_Store(), credential_store=CLI__Credential_Store())
    if snap:
        _api, _crypto = snap.api, snap.crypto
    elif api and crypto:
        _api, _crypto = api, crypto
    else:
        return cli

    def _create_sync(self, base_url=None, access_token=None):
        return Vault__Sync(crypto=_crypto, api=_api)
    cli.create_sync = _types.MethodType(_create_sync, cli)
    return cli


class _Args:
    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)


# ---------------------------------------------------------------------------
# Shared vault snapshot
# ---------------------------------------------------------------------------

class _VaultTest:
    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_single_vault(files={'hello.txt': 'hello', 'data.txt': 'data'})

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


# ---------------------------------------------------------------------------
# cmd_probe
# ---------------------------------------------------------------------------

class Test_CLI__Vault__Probe(_VaultTest):

    def test_probe_vault_type(self, monkeypatch, capsys):
        monkeypatch.setattr(Vault__Sync, 'probe_token', lambda self, t:
                            dict(type='vault', token=t, vault_id='vaultabc123'))
        self.cli.cmd_probe(_Args(token='apple-orange-1234', token_flag=None, base_url=None, json=False))
        out = capsys.readouterr().out
        assert 'vault' in out
        assert 'vaultabc123' in out

    def test_probe_share_type(self, monkeypatch, capsys):
        monkeypatch.setattr(Vault__Sync, 'probe_token', lambda self, t:
                            dict(type='share', token=t, transfer_id='shareXYZ'))
        self.cli.cmd_probe(_Args(token='apple-orange-1234', token_flag=None, base_url=None, json=False))
        out = capsys.readouterr().out
        assert 'share' in out
        assert 'shareXYZ' in out

    def test_probe_json_output(self, monkeypatch, capsys):
        monkeypatch.setattr(Vault__Sync, 'probe_token', lambda self, t:
                            dict(type='vault', token=t, vault_id='vid001'))
        self.cli.cmd_probe(_Args(token='apple-orange-1234', token_flag=None, base_url=None, json=True))
        out = capsys.readouterr().out
        import json as _json
        data = _json.loads(out)
        assert data['type'] == 'vault'


# ---------------------------------------------------------------------------
# cmd_uninit
# ---------------------------------------------------------------------------

class Test_CLI__Vault__Uninit(_VaultTest):

    def test_uninit_prints_backup_info(self, monkeypatch, capsys):
        monkeypatch.setattr(Vault__Sync, 'uninit', lambda self, d:
                            dict(backup_path='/tmp/vault-backup.zip', backup_size=1024 * 512,
                                 working_files=3))
        from sgit_ai.api.Vault__API import Vault__API
        def _create_uninit_sync(self_, b=None, t=None):
            return Vault__Sync(crypto=Vault__Crypto(), api=Vault__API__In_Memory().setup())
        self.cli.create_sync = _types.MethodType(_create_uninit_sync, self.cli)
        self.cli.cmd_uninit(_Args(directory=self.vault))
        out = capsys.readouterr().out
        assert 'Backup' in out
        assert '.sg_vault' in out or 'Removing' in out


# ---------------------------------------------------------------------------
# cmd_commit — nothing-to-commit path
# ---------------------------------------------------------------------------

class Test_CLI__Vault__Commit__NothingToCommit(_VaultTest):

    def test_commit_nothing_to_commit(self, monkeypatch, capsys):
        def _raise_nothing(self, d, message=''):
            raise RuntimeError('nothing to commit, working tree is clean')
        monkeypatch.setattr(Vault__Sync, 'commit', _raise_nothing)
        from sgit_ai.api.Vault__API import Vault__API
        def _cs(s, b=None, t=None):
            return Vault__Sync(crypto=Vault__Crypto(), api=Vault__API__In_Memory().setup())
        self.cli.create_sync = _types.MethodType(_cs, self.cli)
        # Bypass the read-only check
        monkeypatch.setattr(self.cli.token_store, 'load_clone_mode', lambda d: {})
        self.cli.cmd_commit(_Args(directory=self.vault, message=''))
        out = capsys.readouterr().out
        assert 'Nothing to commit' in out


# ---------------------------------------------------------------------------
# cmd_reset
# ---------------------------------------------------------------------------

class Test_CLI__Vault__Reset(_VaultTest):

    def test_reset_to_head(self, monkeypatch, capsys):
        monkeypatch.setattr(Vault__Sync, 'reset', lambda self, d, c:
                            dict(commit_id='abc123def456', restored=2, deleted=1))
        from sgit_ai.api.Vault__API import Vault__API
        def _cs(s, b=None, t=None):
            return Vault__Sync(crypto=Vault__Crypto(), api=Vault__API__In_Memory().setup())
        self.cli.create_sync = _types.MethodType(_cs, self.cli)
        self.cli.cmd_reset(_Args(directory=self.vault, commit_id=None))
        out = capsys.readouterr().out
        assert 'restored to HEAD' in out.lower() or 'abc123' in out

    def test_reset_to_specific_commit(self, monkeypatch, capsys):
        monkeypatch.setattr(Vault__Sync, 'reset', lambda self, d, c:
                            dict(commit_id='abc123def456', restored=2, deleted=1))
        from sgit_ai.api.Vault__API import Vault__API
        def _cs(s, b=None, t=None):
            return Vault__Sync(crypto=Vault__Crypto(), api=Vault__API__In_Memory().setup())
        self.cli.create_sync = _types.MethodType(_cs, self.cli)
        self.cli.cmd_reset(_Args(directory=self.vault, commit_id='abc123'))
        out = capsys.readouterr().out
        assert 'abc123' in out or 'HEAD reset' in out


# ---------------------------------------------------------------------------
# cmd_delete_on_remote
# ---------------------------------------------------------------------------

class Test_CLI__Vault__DeleteOnRemote(_VaultTest):

    def test_delete_on_remote_yes_flag(self, monkeypatch, capsys):
        monkeypatch.setattr(Vault__Sync, 'delete_on_remote', lambda self, d:
                            dict(files_deleted=42))
        self.cli.cmd_delete_on_remote(_Args(directory=self.vault, yes=True, json=False))
        out = capsys.readouterr().out
        assert '42' in out or 'Deleted' in out

    def test_delete_on_remote_already_absent(self, monkeypatch, capsys):
        monkeypatch.setattr(Vault__Sync, 'delete_on_remote', lambda self, d:
                            dict(files_deleted=0))
        self.cli.cmd_delete_on_remote(_Args(directory=self.vault, yes=True, json=False))
        out = capsys.readouterr().out
        assert 'absent' in out or 'already' in out.lower()

    def test_delete_on_remote_json(self, monkeypatch, capsys):
        monkeypatch.setattr(Vault__Sync, 'delete_on_remote', lambda self, d:
                            dict(files_deleted=5))
        self.cli.cmd_delete_on_remote(_Args(directory=self.vault, yes=True, json=True))
        out = capsys.readouterr().out
        import json as _json
        data = _json.loads(out)
        assert data['files_deleted'] == 5


# ---------------------------------------------------------------------------
# cmd_rekey_check
# ---------------------------------------------------------------------------

class Test_CLI__Vault__RekeyCheck(_VaultTest):

    def test_rekey_check_prints_info(self, monkeypatch, capsys):
        monkeypatch.setattr(Vault__Sync, 'rekey_check', lambda self, d:
                            dict(vault_id='vault123', file_count=5, obj_count=20, clean=True))
        self.cli.cmd_rekey_check(_Args(directory=self.vault, json=False))
        out = capsys.readouterr().out
        assert 'vault123' in out
        assert 'Files' in out

    def test_rekey_check_unclean(self, monkeypatch, capsys):
        monkeypatch.setattr(Vault__Sync, 'rekey_check', lambda self, d:
                            dict(vault_id='vault123', file_count=5, obj_count=20, clean=False))
        self.cli.cmd_rekey_check(_Args(directory=self.vault, json=False))
        out = capsys.readouterr().out
        assert 'uncommitted' in out

    def test_rekey_check_json(self, monkeypatch, capsys):
        info = dict(vault_id='vault123', file_count=5, obj_count=20, clean=True)
        monkeypatch.setattr(Vault__Sync, 'rekey_check', lambda self, d: info)
        self.cli.cmd_rekey_check(_Args(directory=self.vault, json=True))
        out = capsys.readouterr().out
        import json as _json
        assert _json.loads(out)['vault_id'] == 'vault123'


# ---------------------------------------------------------------------------
# cmd_rekey_wipe
# ---------------------------------------------------------------------------

class Test_CLI__Vault__RekeyWipe(_VaultTest):

    def test_rekey_wipe_yes_flag(self, monkeypatch, capsys):
        monkeypatch.setattr(Vault__Sync, 'rekey_wipe', lambda self, d:
                            dict(objects_removed=15))
        self.cli.cmd_rekey_wipe(_Args(directory=self.vault, yes=True))
        out = capsys.readouterr().out
        assert '15' in out or 'Wiped' in out


# ---------------------------------------------------------------------------
# cmd_rekey_init
# ---------------------------------------------------------------------------

class Test_CLI__Vault__RekeyInit(_VaultTest):

    def test_rekey_init_prints_new_key(self, monkeypatch, capsys):
        monkeypatch.setattr(Vault__Sync, 'rekey_init', lambda self, d, new_vault_key=None:
                            dict(vault_id='newvaultid', vault_key='newkey:newvlt1'))
        self.cli.cmd_rekey_init(_Args(directory=self.vault, new_key=None))
        out = capsys.readouterr().out
        assert 'newvaultid' in out
        assert 'newkey:newvlt1' in out


# ---------------------------------------------------------------------------
# cmd_rekey_commit
# ---------------------------------------------------------------------------

class Test_CLI__Vault__RekeyCommit(_VaultTest):

    def test_rekey_commit_prints_result(self, monkeypatch, capsys):
        monkeypatch.setattr(Vault__Sync, 'rekey_commit', lambda self, d:
                            dict(file_count=3, commit_id='cmt123'))
        self.cli.cmd_rekey_commit(_Args(directory=self.vault))
        out = capsys.readouterr().out
        assert '3' in out
        assert 'cmt123' in out

    def test_rekey_commit_no_commit_id(self, monkeypatch, capsys):
        monkeypatch.setattr(Vault__Sync, 'rekey_commit', lambda self, d:
                            dict(file_count=0, commit_id=None))
        self.cli.cmd_rekey_commit(_Args(directory=self.vault))
        out = capsys.readouterr().out
        assert 'done' in out or '0' in out


# ---------------------------------------------------------------------------
# cmd_rekey (wizard)
# ---------------------------------------------------------------------------

class Test_CLI__Vault__Rekey(_VaultTest):

    def test_rekey_wizard_yes_flag(self, monkeypatch, capsys):
        monkeypatch.setattr(Vault__Sync, 'rekey_check', lambda self, d:
                            dict(vault_id='old123', file_count=2, obj_count=10, clean=True))
        monkeypatch.setattr(Vault__Sync, 'rekey_wipe', lambda self, d:
                            dict(objects_removed=10))
        monkeypatch.setattr(Vault__Sync, 'rekey_init', lambda self, d, new_vault_key=None:
                            dict(vault_id='new456', vault_key='newk:newvl1'))
        monkeypatch.setattr(Vault__Sync, 'rekey_commit', lambda self, d:
                            dict(file_count=2, commit_id='cmt789'))
        self.cli.cmd_rekey(_Args(directory=self.vault, new_key=None, json=False, yes=True))
        out = capsys.readouterr().out
        assert 'new456' in out or 'Rekey' in out

    def test_rekey_wizard_json_output(self, monkeypatch, capsys):
        monkeypatch.setattr(Vault__Sync, 'rekey_check', lambda self, d:
                            dict(vault_id='old123', file_count=2, obj_count=10, clean=True))
        monkeypatch.setattr(Vault__Sync, 'rekey_wipe', lambda self, d:
                            dict(objects_removed=10))
        monkeypatch.setattr(Vault__Sync, 'rekey_init', lambda self, d, new_vault_key=None:
                            dict(vault_id='new456', vault_key='newk:newvl1'))
        monkeypatch.setattr(Vault__Sync, 'rekey_commit', lambda self, d:
                            dict(file_count=2, commit_id='cmt789'))
        self.cli.cmd_rekey(_Args(directory=self.vault, new_key=None, json=True, yes=True))
        out = capsys.readouterr().out
        import json as _json
        # cmd_rekey prints wizard text then the JSON line — find the JSON line
        json_line = next((l for l in out.splitlines() if l.strip().startswith('{')), None)
        assert json_line is not None, f'No JSON line found in output:\n{out}'
        data = _json.loads(json_line)
        assert data['vault_id'] == 'new456'
        assert data['vault_key'] == 'newk:newvl1'


# ---------------------------------------------------------------------------
# cmd_derive_keys — simple token branch
# ---------------------------------------------------------------------------

class Test_CLI__Vault__DeriveKeys:

    def test_derive_keys_simple_token_extra_output(self, capsys):
        """Lines 1163-1167: simple token → extra SG/Send section printed."""
        cli = CLI__Vault(token_store=CLI__Token_Store(), credential_store=CLI__Credential_Store())
        # Use a real simple token format: word-word-NNNN
        cli.cmd_derive_keys(_Args(vault_key='apple-orange-9876'))
        out = capsys.readouterr().out
        assert 'SG/Send' in out or 'transfer_id' in out

    def test_derive_keys_regular_vault_key(self, capsys):
        cli = CLI__Vault(token_store=CLI__Token_Store(), credential_store=CLI__Credential_Store())
        cli.cmd_derive_keys(_Args(vault_key='testpassphrase12345678:testvlt1'))
        out = capsys.readouterr().out
        assert 'vault_id' in out
        assert 'read_key' in out


# ---------------------------------------------------------------------------
# cmd_ls
# ---------------------------------------------------------------------------

class Test_CLI__Vault__Ls(_VaultTest):

    def test_ls_with_entries(self, monkeypatch, capsys):
        entries = [
            dict(path='a.txt',    size=1024, blob_id='blob001', fetched=True,  large=False),
            dict(path='b.txt',    size=512,  blob_id='blob002', fetched=False, large=False),
        ]
        monkeypatch.setattr(Vault__Sync, 'sparse_ls', lambda self, d, path=None: entries)
        self.cli.cmd_ls(_Args(directory=self.vault, path=None, json=False, ids=False))
        out = capsys.readouterr().out
        assert 'a.txt' in out
        assert 'b.txt' in out
        assert '2/2' in out or '1/2' in out

    def test_ls_empty_vault(self, monkeypatch, capsys):
        monkeypatch.setattr(Vault__Sync, 'sparse_ls', lambda self, d, path=None: [])
        self.cli.cmd_ls(_Args(directory=self.vault, path=None, json=False, ids=False))
        out = capsys.readouterr().out
        assert 'empty' in out or 'not found' in out

    def test_ls_json(self, monkeypatch, capsys):
        entries = [dict(path='x.txt', size=10, blob_id='bbb', fetched=True, large=False)]
        monkeypatch.setattr(Vault__Sync, 'sparse_ls', lambda self, d, path=None: entries)
        self.cli.cmd_ls(_Args(directory=self.vault, path=None, json=True, ids=False))
        out = capsys.readouterr().out
        import json as _json
        data = _json.loads(out)
        assert len(data) == 1
        assert data[0]['path'] == 'x.txt'

    def test_ls_with_ids_flag(self, monkeypatch, capsys):
        entries = [dict(path='x.txt', size=10, blob_id='blobxyz', fetched=True, large=False)]
        monkeypatch.setattr(Vault__Sync, 'sparse_ls', lambda self, d, path=None: entries)
        self.cli.cmd_ls(_Args(directory=self.vault, path=None, json=False, ids=True))
        out = capsys.readouterr().out
        assert 'blobxyz' in out

    def test_ls_some_remote_only(self, monkeypatch, capsys):
        entries = [
            dict(path='local.txt',  size=100, blob_id='bl1', fetched=True,  large=False),
            dict(path='remote.txt', size=200, blob_id='bl2', fetched=False, large=False),
        ]
        monkeypatch.setattr(Vault__Sync, 'sparse_ls', lambda self, d, path=None: entries)
        self.cli.cmd_ls(_Args(directory=self.vault, path=None, json=False, ids=False))
        out = capsys.readouterr().out
        assert 'remote only' in out or 'fetch' in out


# ---------------------------------------------------------------------------
# cmd_fetch
# ---------------------------------------------------------------------------

class Test_CLI__Vault__Fetch(_VaultTest):

    def test_fetch_downloads_files(self, monkeypatch, capsys):
        monkeypatch.setattr(Vault__Sync, 'sparse_fetch', lambda self, d, path=None, on_progress=None:
                            dict(fetched=2, already_local=1, written=['a.txt', 'b.txt']))
        self.cli.cmd_fetch(_Args(directory=self.vault, path=None, all=False,
                                  token=None, base_url=None))
        out = capsys.readouterr().out
        assert 'a.txt' in out or '2' in out

    def test_fetch_already_up_to_date(self, monkeypatch, capsys):
        monkeypatch.setattr(Vault__Sync, 'sparse_fetch', lambda self, d, path=None, on_progress=None:
                            dict(fetched=0, already_local=3, written=[]))
        self.cli.cmd_fetch(_Args(directory=self.vault, path=None, all=False,
                                  token=None, base_url=None))
        out = capsys.readouterr().out
        assert 'already' in out.lower() or 'up to date' in out.lower()

    def test_fetch_no_matches(self, monkeypatch, capsys):
        monkeypatch.setattr(Vault__Sync, 'sparse_fetch', lambda self, d, path=None, on_progress=None:
                            dict(fetched=0, already_local=0, written=[]))
        self.cli.cmd_fetch(_Args(directory=self.vault, path='nonexistent', all=False,
                                  token=None, base_url=None))
        out = capsys.readouterr().out
        assert 'No files' in out or 'matched' in out


# ---------------------------------------------------------------------------
# cmd_clone — read-only path (lines 53-75)
# ---------------------------------------------------------------------------

class Test_CLI__Vault__Clone__ReadOnly(_VaultTest):

    def test_clone_read_only_prints_success(self, monkeypatch, capsys):
        monkeypatch.setattr(Vault__Sync, 'clone_read_only',
                            lambda self, vault_id, rk, d, on_progress=None, sparse=False:
                            dict(directory=d, vault_id='vid001', commit_id='cmt001'))
        monkeypatch.setattr(self.cli.token_store, 'save_token', lambda t, d: None)
        monkeypatch.setattr(self.cli.token_store, 'save_base_url', lambda u, d: None)

        import tempfile
        target = tempfile.mkdtemp()
        try:
            self.cli.cmd_clone(_Args(
                vault_key='vid001',
                directory=target,
                read_key='readkeyhex',
                token=None,
                base_url=None,
                sparse=False,
                force=False,
            ))
            out = capsys.readouterr().out
            assert 'read-only' in out.lower() or 'Read-only' in out
        finally:
            import shutil
            shutil.rmtree(target, ignore_errors=True)

    def test_clone_read_only_with_commit_id(self, monkeypatch, capsys):
        monkeypatch.setattr(Vault__Sync, 'clone_read_only',
                            lambda self, vault_id, rk, d, on_progress=None, sparse=False:
                            dict(directory=d, vault_id='vid002', commit_id='cmt99'))
        monkeypatch.setattr(self.cli.token_store, 'save_token', lambda t, d: None)

        import tempfile
        target = tempfile.mkdtemp()
        try:
            self.cli.cmd_clone(_Args(
                vault_key='vid002',
                directory=target,
                read_key='readkeyhex2',
                token=None,
                base_url=None,
                sparse=False,
                force=False,
            ))
            out = capsys.readouterr().out
            assert 'cmt99' in out
        finally:
            import shutil
            shutil.rmtree(target, ignore_errors=True)
