"""Coverage tests for CLI__Vault — batch 3.

Targets uncovered lines:
  279:        cmd_commit — RuntimeError that is NOT 'nothing to commit' → re-raised
  306-312:    cmd_status — sparse=True result → sparse lines printed
  444:        cmd_push   — force=True → 'Force-pushing...' print
  801-815:    cmd_info   — read-only clone path
  965:        cmd_delete_on_remote — read-only vault → raises
  967-972:    cmd_delete_on_remote — interactive confirm block (no --yes)
  1023-1040:  cmd_rekey  — interactive questions (no --yes)
  1103-1108:  cmd_rekey_wipe — interactive (no --yes) → abort
  1200:       cmd_inspect_log — graph=True → inspect_commit_dag
  1309-1310:  cmd_cat — path not found with --id → error + exit
  1322-1326:  cmd_cat — plain (no --id/--json) → sparse_cat + write to stdout
  1333-1381:  cmd_write — full body (stdin path, file path, as_json, do_push)
  49-50:      cmd_clone  — force=True with existing dir → rmtree
  60:         cmd_clone  — read-only + base_url → save_base_url
  78:         cmd_clone  — full clone + base_url → save_base_url
  89-90:      cmd_clone  — effective_base_url → save_base_url after full clone
  115-118:    cmd_clone  — sparse clone result → sparse next-steps printed
"""
import io
import json
import os
import sys
import shutil
import tempfile
import types as _types
import unittest.mock

import pytest

from sgit_ai.cli.CLI__Vault             import CLI__Vault
from sgit_ai.cli.CLI__Token_Store       import CLI__Token_Store
from sgit_ai.cli.CLI__Credential_Store  import CLI__Credential_Store
from sgit_ai.core.Vault__Sync           import Vault__Sync
from sgit_ai.crypto.Vault__Crypto       import Vault__Crypto
from sgit_ai.api.Vault__API__In_Memory  import Vault__API__In_Memory
from tests._helpers.vault_test_env      import Vault__Test_Env


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_cli(snap=None) -> CLI__Vault:
    cli = CLI__Vault(token_store=CLI__Token_Store(),
                     credential_store=CLI__Credential_Store())
    if snap:
        api, crypto = snap.api, snap.crypto
        def _cs(self, base_url=None, access_token=None):
            return Vault__Sync(crypto=crypto, api=api)
        cli.create_sync = _types.MethodType(_cs, cli)
    return cli


class _Args:
    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)


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
# Line 279: cmd_commit re-raises non-"nothing to commit" RuntimeError
# ---------------------------------------------------------------------------

class Test_CLI__Vault__Commit__ReRaise(_VaultTest):

    def test_commit_runtime_error_reraises_line_279(self, monkeypatch):
        """Line 279: RuntimeError without 'nothing to commit' → re-raised."""
        monkeypatch.setattr(Vault__Sync, 'commit',
                            lambda self, d, message='': (_ for _ in ()).throw(
                                RuntimeError('vault is corrupt')))
        monkeypatch.setattr(self.cli.token_store, 'load_clone_mode', lambda d: {})
        with pytest.raises(RuntimeError, match='vault is corrupt'):
            self.cli.cmd_commit(_Args(directory=self.vault, message=''))


# ---------------------------------------------------------------------------
# Lines 306-312: cmd_status — sparse=True
# ---------------------------------------------------------------------------

class Test_CLI__Vault__Status__Sparse(_VaultTest):

    def test_status_sparse_with_unfetched_prints_sparse_lines(self, monkeypatch, capsys):
        """Lines 306-312: sparse=True + unfetched files → sparse-mode output."""
        monkeypatch.setattr(Vault__Sync, 'status', lambda self, d: dict(
            sparse=True, files_fetched=2, files_total=5,
            clone_branch_id='clone-abc', named_branch_id='named-xyz',
            push_status='up_to_date', ahead=0, behind=0,
            remote_configured=True, never_pushed=False, clean=True,
            added=[], modified=[], deleted=[],
        ))
        self.cli.cmd_status(_Args(directory=self.vault, token=None, base_url=None,
                                  explain=False))
        out = capsys.readouterr().out
        assert 'Sparse mode' in out
        assert '2/5' in out
        assert 'fetch' in out

    def test_status_sparse_all_fetched_no_unfetched_line(self, monkeypatch, capsys):
        """Lines 306-309: sparse=True, all files fetched → no unfetched line."""
        monkeypatch.setattr(Vault__Sync, 'status', lambda self, d: dict(
            sparse=True, files_fetched=3, files_total=3,
            clone_branch_id='', named_branch_id='',
            push_status='unknown', ahead=0, behind=0,
            remote_configured=False, never_pushed=True, clean=True,
            added=[], modified=[], deleted=[],
        ))
        self.cli.cmd_status(_Args(directory=self.vault, token=None, base_url=None,
                                  explain=False))
        out = capsys.readouterr().out
        assert 'Sparse mode' in out
        assert '3/3' in out


# ---------------------------------------------------------------------------
# Line 444: cmd_push — force=True
# ---------------------------------------------------------------------------

class Test_CLI__Vault__Push__Force(_VaultTest):

    def test_push_with_force_prints_force_pushing_line_444(self, monkeypatch, capsys):
        """Line 444: force=True → 'Force-pushing...' printed."""
        monkeypatch.setattr(Vault__Sync, 'push',
                            lambda self, d, branch_only=False, force=False, on_progress=None:
                            dict(status='ok', commits_pushed=1, objects_uploaded=3))
        self.cli.cmd_push(_Args(directory=self.vault, token='tok', base_url=None,
                                branch_only=False, force=True))
        out = capsys.readouterr().out
        assert 'Force-pushing' in out


# ---------------------------------------------------------------------------
# Lines 801-815: cmd_info — read-only clone
# ---------------------------------------------------------------------------

class Test_CLI__Vault__Info__ReadOnly(_VaultTest):

    def test_info_read_only_prints_vault_details_lines_801_815(self, capsys):
        """Lines 801-815: clone_mode='read-only' → read-only info block printed."""
        self.cli.token_store.load_clone_mode = lambda d: {
            'mode': 'read-only', 'vault_id': 'ronly-vault-1', 'read_key': 'aaaa'
        }
        self.cli.token_store.resolve_base_url = lambda flag, d: 'https://sg.example.com'
        self.cli.cmd_info(_Args(directory=self.vault, base_url=None))
        out = capsys.readouterr().out
        assert 'read-only' in out
        assert 'ronly-vault-1' in out
        assert 'aaaa' in out
        assert 'sg.example.com' in out


# ---------------------------------------------------------------------------
# Lines 965, 967-972: cmd_delete_on_remote
# ---------------------------------------------------------------------------

class Test_CLI__Vault__DeleteOnRemote__Extra(_VaultTest):

    def test_delete_on_remote_read_only_raises_line_965(self, monkeypatch):
        """Line 965: write_key empty → raises RuntimeError."""
        import types as _t
        fake_c = _t.SimpleNamespace(write_key='', vault_id='v123')
        monkeypatch.setattr(Vault__Sync, '_init_components', lambda self, d: fake_c)
        with pytest.raises(RuntimeError, match='read-only clone'):
            self.cli.cmd_delete_on_remote(_Args(directory=self.vault, yes=True, json=False))

    def test_delete_on_remote_wrong_confirm_raises_line_972(self, monkeypatch):
        """Lines 967-972: yes=False, user types wrong vault ID → raises."""
        import types as _t
        fake_c = _t.SimpleNamespace(write_key='somekey', vault_id='exact-vault-id')
        monkeypatch.setattr(Vault__Sync, '_init_components', lambda self, d: fake_c)
        with unittest.mock.patch('sys.stdin', io.StringIO('wrong-id\n')):
            with pytest.raises(RuntimeError, match='Vault ID did not match'):
                self.cli.cmd_delete_on_remote(_Args(directory=self.vault, yes=False, json=False))

    def test_delete_on_remote_correct_confirm_proceeds(self, monkeypatch, capsys):
        """Lines 967-972: yes=False, user types correct vault ID → proceeds."""
        import types as _t
        fake_c = _t.SimpleNamespace(write_key='somekey', vault_id='exact-vault-id')
        monkeypatch.setattr(Vault__Sync, '_init_components', lambda self, d: fake_c)
        monkeypatch.setattr(Vault__Sync, 'delete_on_remote', lambda self, d: dict(files_deleted=7))
        with unittest.mock.patch('sys.stdin', io.StringIO('exact-vault-id\n')):
            self.cli.cmd_delete_on_remote(_Args(directory=self.vault, yes=False, json=False))
        out = capsys.readouterr().out
        assert '7' in out or 'Deleted' in out


# ---------------------------------------------------------------------------
# Lines 1023-1040: cmd_rekey — interactive (no --yes)
# ---------------------------------------------------------------------------

class Test_CLI__Vault__Rekey__Interactive(_VaultTest):

    def _mock_rekey_check(self, monkeypatch):
        monkeypatch.setattr(Vault__Sync, 'rekey_check', lambda self, d:
                            dict(vault_id='old-v1', file_count=2, obj_count=10, clean=True))

    def test_rekey_interactive_first_question_abort_line_1030(self, monkeypatch):
        """Lines 1023-1030: first [y/N] answered 'n' → RuntimeError 'Aborted'."""
        self._mock_rekey_check(monkeypatch)
        with unittest.mock.patch('sys.stdin', io.StringIO('n\n')):
            with pytest.raises(RuntimeError, match='Aborted'):
                self.cli.cmd_rekey(_Args(directory=self.vault, new_key=None,
                                         json=False, yes=False))

    def test_rekey_interactive_second_question_abort_line_1036(self, monkeypatch):
        """Lines 1032-1036: first question yes, second 'n' → RuntimeError."""
        self._mock_rekey_check(monkeypatch)
        with unittest.mock.patch('sys.stdin', io.StringIO('y\nn\n')):
            with pytest.raises(RuntimeError, match='Aborted'):
                self.cli.cmd_rekey(_Args(directory=self.vault, new_key=None,
                                         json=False, yes=False))

    def test_rekey_interactive_final_confirmation_abort_line_1040(self, monkeypatch):
        """Lines 1038-1040: both y/N answered yes, final 'YES' not typed → abort."""
        self._mock_rekey_check(monkeypatch)
        with unittest.mock.patch('sys.stdin', io.StringIO('y\ny\nNO\n')):
            with pytest.raises(RuntimeError, match='Aborted'):
                self.cli.cmd_rekey(_Args(directory=self.vault, new_key=None,
                                         json=False, yes=False))


# ---------------------------------------------------------------------------
# Lines 1103-1108: cmd_rekey_wipe — interactive (no --yes)
# ---------------------------------------------------------------------------

class Test_CLI__Vault__RekeyWipe__Interactive(_VaultTest):

    def test_rekey_wipe_interactive_abort_lines_1103_1108(self, monkeypatch):
        """Lines 1103-1108: yes=False, user does not type YES → RuntimeError."""
        monkeypatch.setattr(Vault__Sync, 'rekey_check', lambda self, d:
                            dict(vault_id='v1', obj_count=5))
        with unittest.mock.patch('sys.stdin', io.StringIO('no\n')):
            with pytest.raises(RuntimeError, match='Aborted'):
                self.cli.cmd_rekey_wipe(_Args(directory=self.vault, yes=False))

    def test_rekey_wipe_interactive_confirmed_lines_1103_1112(self, monkeypatch, capsys):
        """Lines 1103-1112: yes=False, user types YES → wipe proceeds."""
        monkeypatch.setattr(Vault__Sync, 'rekey_check', lambda self, d:
                            dict(vault_id='v1', obj_count=5))
        monkeypatch.setattr(Vault__Sync, 'rekey_wipe', lambda self, d:
                            dict(objects_removed=5))
        with unittest.mock.patch('sys.stdin', io.StringIO('YES\n')):
            self.cli.cmd_rekey_wipe(_Args(directory=self.vault, yes=False))
        out = capsys.readouterr().out
        assert '5' in out or 'Wiped' in out


# ---------------------------------------------------------------------------
# Line 1200: cmd_inspect_log — graph=True → inspect_commit_dag
# ---------------------------------------------------------------------------

class Test_CLI__Vault__InspectLog__Graph(_VaultTest):

    def test_inspect_log_graph_mode_line_1200(self, monkeypatch, capsys):
        """Line 1200: graph=True → inspector.inspect_commit_dag called."""
        from sgit_ai.objects.Vault__Inspector import Vault__Inspector
        dag_called = []
        monkeypatch.setattr(Vault__Inspector, 'inspect_commit_dag',
                            lambda self, d, read_key=None: dag_called.append(True) or [])
        monkeypatch.setattr(Vault__Inspector, 'format_commit_log',
                            lambda self, chain, oneline=False, graph=False: 'graph output')
        monkeypatch.setattr(self.cli.token_store, 'resolve_read_key', lambda a: b'x' * 32)
        self.cli.cmd_inspect_log(_Args(directory=self.vault, oneline=False, graph=True))
        assert dag_called
        assert 'graph output' in capsys.readouterr().out


# ---------------------------------------------------------------------------
# Lines 1309-1310: cmd_cat — path not found with --id
# ---------------------------------------------------------------------------

class Test_CLI__Vault__Cat__Extra(_VaultTest):

    def test_cat_id_path_not_found_exits_lines_1309_1310(self, monkeypatch, capsys):
        """Lines 1309-1310: --id but path not in vault → error + sys.exit(1)."""
        monkeypatch.setattr(Vault__Sync, 'sparse_ls', lambda self, d, path=None: [])
        with pytest.raises(SystemExit) as exc:
            self.cli.cmd_cat(_Args(directory=self.vault, path='nonexistent.txt',
                                   id=True, json=False, token=None, base_url=None))
        assert exc.value.code == 1
        assert 'not found' in capsys.readouterr().err

    def test_cat_plain_writes_content_to_stdout_lines_1322_1326(self, monkeypatch):
        """Lines 1322-1326: no --id/--json → sparse_cat → write to stdout.buffer."""
        content = b'hello vault file'
        monkeypatch.setattr(Vault__Sync, 'sparse_cat',
                            lambda self, d, path: content)
        buf = io.BytesIO()

        class _FakeStdout:
            buffer = buf
            def write(self, s): pass
            def flush(self): pass

        monkeypatch.setattr(sys, 'stdout', _FakeStdout())
        self.cli.cmd_cat(_Args(directory=self.vault, path='hello.txt',
                               id=False, json=False, token=None, base_url=None))
        assert buf.getvalue() == content


# ---------------------------------------------------------------------------
# Lines 1333-1381: cmd_write — full body
# ---------------------------------------------------------------------------

class Test_CLI__Vault__Write__Body(_VaultTest):

    def _fake_stdin(self, monkeypatch, data: bytes):
        """Replace sys.stdin with an object whose .buffer is a BytesIO."""
        class _FakeStdin:
            def __init__(self):
                self.buffer = io.BytesIO(data)
            def readline(self):
                return self.buffer.readline().decode()
        monkeypatch.setattr(sys, 'stdin', _FakeStdin())

    def test_cmd_write_stdin_path_prints_blob_id(self, monkeypatch, capsys):
        """Lines 1333-1381: no file= → reads stdin, writes file, prints blob_id."""
        monkeypatch.setattr(self.cli.token_store, 'load_clone_mode', lambda d: {})
        monkeypatch.setattr(Vault__Sync, 'write_file',
                            lambda self, d, path, content, message='', also=None:
                            dict(blob_id='obj-cas-imm-aabbccdd1234', commit_id='cmt001',
                                 message='', unchanged=False, paths={}))
        self._fake_stdin(monkeypatch, b'file content from stdin')
        self.cli.cmd_write(_Args(directory=self.vault, path='new.txt',
                                 message='', push=False, file=None, also=[],
                                 json=False, token=None, base_url=None))
        out = capsys.readouterr().out
        assert 'obj-cas-imm-aabbccdd1234' in out

    def test_cmd_write_from_file_path(self, monkeypatch, capsys, tmp_path):
        """Lines 1342-1345: file= set → reads from that file."""
        monkeypatch.setattr(self.cli.token_store, 'load_clone_mode', lambda d: {})
        src = tmp_path / 'input.txt'
        src.write_bytes(b'from file')
        monkeypatch.setattr(Vault__Sync, 'write_file',
                            lambda self, d, path, content, message='', also=None:
                            dict(blob_id='obj-cas-imm-filefile5678', commit_id='cmt002',
                                 message='', unchanged=False, paths={}))
        self._fake_stdin(monkeypatch, b'')
        self.cli.cmd_write(_Args(directory=self.vault, path='src.txt',
                                  message='', push=False, file=str(src), also=[],
                                  json=False, token=None, base_url=None))
        out = capsys.readouterr().out
        assert 'obj-cas-imm-filefile5678' in out

    def test_cmd_write_as_json_output(self, monkeypatch, capsys):
        """Lines 1373-1378: as_json=True → JSON output with blob_id etc."""
        monkeypatch.setattr(self.cli.token_store, 'load_clone_mode', lambda d: {})
        monkeypatch.setattr(Vault__Sync, 'write_file',
                            lambda self, d, path, content, message='', also=None:
                            dict(blob_id='obj-cas-imm-json9999aaaa', commit_id='cmt003',
                                 message='test msg', unchanged=False, paths={}))
        self._fake_stdin(monkeypatch, b'data')
        self.cli.cmd_write(_Args(directory=self.vault, path='out.txt',
                                 message='test msg', push=False, file=None, also=[],
                                 json=True, token=None, base_url=None))
        out = capsys.readouterr().out
        data = json.loads(out)
        assert data['blob_id'] == 'obj-cas-imm-json9999aaaa'
        assert data['commit_id'] == 'cmt003'

    def test_cmd_write_also_bad_format_exits(self, monkeypatch, capsys):
        """Lines 1350-1353: --also item without ':' → error + exit."""
        monkeypatch.setattr(self.cli.token_store, 'load_clone_mode', lambda d: {})
        self._fake_stdin(monkeypatch, b'data')
        with pytest.raises(SystemExit) as exc:
            self.cli.cmd_write(_Args(directory=self.vault, path='out.txt',
                                     message='', push=False, file=None,
                                     also=['bad-format'], json=False,
                                     token=None, base_url=None))
        assert exc.value.code == 1
        assert '--also' in capsys.readouterr().err


# ---------------------------------------------------------------------------
# Lines 49-50: cmd_clone — force=True with existing dir
# ---------------------------------------------------------------------------

class Test_CLI__Vault__Clone__Force(_VaultTest):

    def test_clone_force_removes_existing_dir_lines_49_50(self, monkeypatch, capsys, tmp_path):
        """Lines 49-50: force=True + existing dir → rmtree called, clone proceeds."""
        target = tmp_path / 'existing_vault'
        target.mkdir()
        (target / 'leftover.txt').write_text('old')

        monkeypatch.setattr(Vault__Sync, 'clone',
                            lambda self, vk, d, on_progress=None, sparse=False:
                            dict(directory=str(target), vault_id='v001',
                                 commit_id='cmt001', branch_id='branch-clone-abc',
                                 share_token=None, sparse=False,
                                 file_count=2))
        monkeypatch.setattr(self.cli.token_store, 'save_token', lambda t, d: None)

        # Patch Vault__Crypto.derive_keys_from_vault_key to avoid key parse
        monkeypatch.setattr(Vault__Crypto, 'derive_keys_from_vault_key',
                            lambda self, k: {'read_key': 'rk123', 'vault_id': 'v001'})

        self.cli.cmd_clone(_Args(
            vault_key='passphrase:vlt1',
            directory=str(target),
            read_key=None,
            token=None,
            base_url=None,
            sparse=False,
            force=True,
        ))
        out = capsys.readouterr().out
        assert 'force' in out.lower() or 'Removing' in out or 'Cloned' in out


# ---------------------------------------------------------------------------
# Line 60: cmd_clone — read-only + base_url → save_base_url
# ---------------------------------------------------------------------------

class Test_CLI__Vault__Clone__ReadOnly__BaseUrl(_VaultTest):

    def test_clone_read_only_with_base_url_saves_it_line_60(self, monkeypatch, capsys, tmp_path):
        """Line 60: read-only clone + base_url set → save_base_url called."""
        target = tmp_path / 'ro_clone'
        target.mkdir()
        saved_urls = []
        monkeypatch.setattr(Vault__Sync, 'clone_read_only',
                            lambda self, vid, rk, d, on_progress=None, sparse=False:
                            dict(directory=str(target), vault_id='vid001', commit_id='cmt001'))
        monkeypatch.setattr(self.cli.token_store, 'save_token', lambda t, d: None)
        monkeypatch.setattr(self.cli.token_store, 'save_base_url',
                            lambda u, d: saved_urls.append(u))

        self.cli.cmd_clone(_Args(
            vault_key='vid001',
            directory=str(target),
            read_key='readkeyhex',
            token=None,
            base_url='https://myserver.example.com',
            sparse=False,
            force=False,
        ))
        assert any('myserver' in u for u in saved_urls)


# ---------------------------------------------------------------------------
# Lines 89-90, 78: cmd_clone full + base_url / effective_base_url
# ---------------------------------------------------------------------------

class Test_CLI__Vault__Clone__Full__BaseUrl(_VaultTest):

    def test_clone_full_effective_base_url_saves_lines_89_95(self, monkeypatch, capsys, tmp_path):
        """Lines 89-90, 94-95: full clone + api has base_url → effective_base_url → save_base_url."""
        target = tmp_path / 'full_clone'
        target.mkdir()
        saved_urls = []
        crypto  = self.snap.crypto
        api     = self.snap.api
        # Give the in-memory API a base_url so effective_base_url is truthy
        api.base_url = 'https://effective.example.com'

        def _cs_with_url(self_, base_url=None, access_token=None):
            return Vault__Sync(crypto=crypto, api=api)

        self.cli.create_sync = _types.MethodType(_cs_with_url, self.cli)

        monkeypatch.setattr(Vault__Sync, 'clone',
                            lambda self, vk, d, on_progress=None, sparse=False:
                            dict(directory=str(target), vault_id='v002',
                                 commit_id='cmt002', branch_id='branch-clone-def',
                                 share_token=None, sparse=False, file_count=3))
        monkeypatch.setattr(self.cli.token_store, 'save_token', lambda t, d: None)
        monkeypatch.setattr(self.cli.token_store, 'save_base_url',
                            lambda u, d: saved_urls.append(str(u)))
        # Use bad key so derive_keys raises → covers lines 89-90
        self.cli.cmd_clone(_Args(
            vault_key='not-a-valid-key-format-!',
            directory=str(target),
            read_key=None,
            token='tok123',
            base_url=None,
            sparse=False,
            force=False,
        ))
        assert any('effective.example.com' in u for u in saved_urls)


# ---------------------------------------------------------------------------
# Lines 115-118: cmd_clone — sparse result → sparse next-steps printed
# ---------------------------------------------------------------------------

class Test_CLI__Vault__Clone__Sparse(_VaultTest):

    def test_clone_sparse_result_prints_sparse_nextsteps_lines_115_118(self, monkeypatch, capsys, tmp_path):
        """Lines 115-118: result.get('sparse') True → sparse next-steps printed."""
        target = tmp_path / 'sparse_clone'
        target.mkdir()
        monkeypatch.setattr(Vault__Sync, 'clone',
                            lambda self, vk, d, on_progress=None, sparse=False:
                            dict(directory=str(target), vault_id='v003',
                                 commit_id='cmt003', branch_id='branch-clone-ghi',
                                 share_token=None, sparse=True, file_count=5))
        monkeypatch.setattr(self.cli.token_store, 'save_token', lambda t, d: None)
        monkeypatch.setattr(Vault__Crypto, 'derive_keys_from_vault_key',
                            lambda self, k: {'read_key': 'rk789', 'vault_id': 'v003'})

        self.cli.cmd_clone(_Args(
            vault_key='passphrase:vlt3',
            directory=str(target),
            read_key=None,
            token=None,
            base_url=None,
            sparse=True,
            force=False,
        ))
        out = capsys.readouterr().out
        assert 'sgit fetch' in out or 'sparse' in out.lower()
