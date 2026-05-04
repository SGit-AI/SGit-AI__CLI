"""Coverage tests for CLI__Vault — batch 4.

Targets uncovered lines:
  60:        cmd_clone — read-only + token → save_token called
  805:       cmd_info  — read-only + resolve_base_url returns '' → DEFAULT_BASE_URL used
  1040:      cmd_rekey — interactive YES typed → print() executed before rekey steps
  1354-1356: cmd_write — --also success path (file read)
  1363-1371: cmd_write — do_push=True path
"""
import io
import os
import sys
import tempfile
import types as _types
import unittest.mock

import pytest

from sgit_ai.cli.CLI__Vault            import CLI__Vault
from sgit_ai.cli.CLI__Token_Store      import CLI__Token_Store
from sgit_ai.cli.CLI__Credential_Store import CLI__Credential_Store
from sgit_ai.network.api.Vault__API__In_Memory import Vault__API__In_Memory
from sgit_ai.core.Vault__Sync          import Vault__Sync
from sgit_ai.crypto.Vault__Crypto      import Vault__Crypto
from tests._helpers.vault_test_env     import Vault__Test_Env


class _Args:
    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)


class _VaultTest:
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
        api, crypto = self.snap.api, self.snap.crypto

        def _cs(self_, base_url=None, access_token=None):
            return Vault__Sync(crypto=crypto, api=api)

        self.cli.create_sync = _types.MethodType(_cs, self.cli)

    def teardown_method(self):
        self.snap.cleanup()


# ---------------------------------------------------------------------------
# Line 60: cmd_clone read-only + token → save_token called
# ---------------------------------------------------------------------------

class Test_CLI__Vault__Clone__ReadOnly__Token(_VaultTest):

    def test_clone_read_only_with_token_saves_token_line_60(self, monkeypatch, capsys, tmp_path):
        """Line 60: read-only clone + token set → save_token called."""
        target = tmp_path / 'ro_clone_tok'
        target.mkdir()
        saved_tokens = []

        monkeypatch.setattr(Vault__Sync, 'clone_read_only',
                            lambda self, vid, rk, d, on_progress=None, sparse=False:
                            dict(directory=str(target), vault_id='vid99', commit_id='cmt99'))
        monkeypatch.setattr(self.cli.token_store, 'save_token',
                            lambda t, d: saved_tokens.append(t))
        monkeypatch.setattr(self.cli.token_store, 'save_base_url', lambda u, d: None)

        self.cli.cmd_clone(_Args(
            vault_key='vid99',
            directory=str(target),
            read_key='readkeyabc',
            token='my-access-token',
            base_url=None,
            sparse=False,
            force=False,
        ))
        assert 'my-access-token' in saved_tokens


# ---------------------------------------------------------------------------
# Line 805: cmd_info read-only with no base_url → DEFAULT_BASE_URL used
# ---------------------------------------------------------------------------

class Test_CLI__Vault__Info__ReadOnly__DefaultUrl(_VaultTest):

    def test_info_read_only_no_base_url_uses_default_line_805(self, monkeypatch, capsys):
        """Line 805: resolve_base_url returns '' → base_url = DEFAULT_BASE_URL."""
        from sgit_ai.network.api.Vault__API import DEFAULT_BASE_URL

        monkeypatch.setattr(self.cli.token_store, 'load_clone_mode',
                            lambda d: {'mode': 'read-only', 'vault_id': 'v99', 'read_key': 'rk99'})
        monkeypatch.setattr(self.cli.token_store, 'resolve_base_url',
                            lambda base_url, d: '')

        self.cli.cmd_info(_Args(directory=self.vault, base_url=None))
        out = capsys.readouterr().out
        assert DEFAULT_BASE_URL in out


# ---------------------------------------------------------------------------
# Line 1040: cmd_rekey interactive — all YES answers → print() line hit
# ---------------------------------------------------------------------------

class Test_CLI__Vault__Rekey__Interactive__Full(_VaultTest):

    def test_rekey_interactive_yes_hits_print_line_1040(self, monkeypatch, capsys):
        """Line 1040: user types y, y, YES → print() after YES executed."""
        monkeypatch.setattr(Vault__Sync, 'rekey_check',
                            lambda self, d: dict(vault_id='oldvault1', file_count=1,
                                                  obj_count=3, clean=True))
        monkeypatch.setattr(Vault__Sync, 'rekey_wipe',
                            lambda self, d: dict(objects_removed=3))
        monkeypatch.setattr(Vault__Sync, 'rekey_init',
                            lambda self, d, new_vault_key=None: dict(vault_id='newvault1',
                                                                      vault_key='newvault1:some-key-hex'))
        monkeypatch.setattr(Vault__Sync, 'rekey_commit',
                            lambda self, d: dict(file_count=1, commit_id='newcmt1'))

        with unittest.mock.patch('sys.stdin', io.StringIO('y\ny\nYES\n')):
            self.cli.cmd_rekey(_Args(directory=self.vault, new_key=None,
                                     json=False, yes=False))
        out = capsys.readouterr().out
        assert '1/3' in out or 'Wiping' in out


# ---------------------------------------------------------------------------
# Lines 1354-1356: cmd_write — --also success path (v_path:local_file read)
# ---------------------------------------------------------------------------

class Test_CLI__Vault__Write__Also(_VaultTest):

    def test_write_also_reads_file_lines_1354_1356(self, monkeypatch, tmp_path, capsys):
        """Lines 1354-1356: --also v_path:local_file → file opened and read."""
        extra_file = tmp_path / 'extra.bin'
        extra_file.write_bytes(b'extra content')

        captured_also = {}

        def fake_write_file(self_, d, path, content, message='', also=None):
            if also:
                captured_also.update(also)
            return dict(blob_id='blob001', commit_id='cmt001',
                        message=message, unchanged=False, paths={})

        monkeypatch.setattr(Vault__Sync, 'write_file', fake_write_file)

        buf = io.BytesIO(b'main content')
        class _FakeStdin:
            buffer = buf
        monkeypatch.setattr(sys, 'stdin', _FakeStdin())

        self.cli.cmd_write(_Args(
            directory=self.vault,
            path='main.txt',
            file=None,
            message='test',
            push=False,
            json=False,
            also=[f'extra/extra.bin:{extra_file}'],
            token=None,
            base_url=None,
        ))
        assert 'extra/extra.bin' in captured_also
        assert captured_also['extra/extra.bin'] == b'extra content'


# ---------------------------------------------------------------------------
# Lines 1363-1371: cmd_write — do_push=True → push path
# ---------------------------------------------------------------------------

class Test_CLI__Vault__Write__DoPush(_VaultTest):

    def test_write_do_push_calls_push_lines_1363_1371(self, monkeypatch, capsys):
        """Lines 1363-1371: do_push=True + stored token → create_sync, push, 'Pushed.'."""
        push_called = []

        monkeypatch.setattr(Vault__Sync, 'write_file',
                            lambda self, d, path, content, message='', also=None:
                            dict(blob_id='blob002', commit_id='cmt002',
                                 message='', unchanged=False, paths={}))
        monkeypatch.setattr(Vault__Sync, 'push',
                            lambda self, d, on_progress=None:
                            push_called.append(True) or dict(status='pushed', objects_uploaded=1))
        monkeypatch.setattr(self.cli.token_store, 'resolve_token',
                            lambda tok, d: 'stored-token')
        monkeypatch.setattr(self.cli.token_store, 'resolve_base_url',
                            lambda url, d: 'https://example.com')

        buf = io.BytesIO(b'push content')
        class _FakeStdin:
            buffer = buf
        monkeypatch.setattr(sys, 'stdin', _FakeStdin())

        self.cli.cmd_write(_Args(
            directory=self.vault,
            path='pushed.txt',
            file=None,
            message='push test',
            push=True,
            json=False,
            also=[],
            token=None,
            base_url=None,
        ))
        assert push_called
        err = capsys.readouterr().err
        assert 'Pushed.' in err

    def test_write_do_push_no_stored_token_prompts_line_1366(self, monkeypatch, capsys):
        """Line 1366: do_push=True + no stored token → _prompt_remote_setup called."""
        push_called = []

        monkeypatch.setattr(Vault__Sync, 'write_file',
                            lambda self, d, path, content, message='', also=None:
                            dict(blob_id='blob003', commit_id='cmt003',
                                 message='', unchanged=False, paths={}))
        monkeypatch.setattr(Vault__Sync, 'push',
                            lambda self, d, on_progress=None:
                            push_called.append(True) or dict(status='pushed', objects_uploaded=0))
        monkeypatch.setattr(self.cli.token_store, 'resolve_token',
                            lambda tok, d: '')
        monkeypatch.setattr(self.cli.token_store, 'resolve_base_url',
                            lambda url, d: '')
        monkeypatch.setattr(self.cli, '_prompt_remote_setup',
                            lambda d, base_url: ('prompted-token', 'https://prompted.example.com'))

        buf = io.BytesIO(b'no-token content')
        class _FakeStdin:
            buffer = buf
        monkeypatch.setattr(sys, 'stdin', _FakeStdin())

        self.cli.cmd_write(_Args(
            directory=self.vault,
            path='notok.txt',
            file=None,
            message='no token',
            push=True,
            json=False,
            also=[],
            token=None,
            base_url=None,
        ))
        assert push_called
        err = capsys.readouterr().err
        assert 'Pushed.' in err
