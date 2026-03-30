"""Unit tests for CLI__Share.cmd_share.

Strategy: monkeypatch Vault__Transfer.share to return a canned result dict,
and CLI__Token_Store.load_token to return a pre-saved token. This avoids
any real HTTP calls while exercising all the cmd_share output/history logic.
"""
import io
import json
import os
import sys
import types as _types

import pytest

from sgit_ai.cli.CLI__Share       import CLI__Share, SHARE_HISTORY_FILE
from sgit_ai.cli.CLI__Token_Store import CLI__Token_Store
from sgit_ai.transfer.Vault__Transfer import Vault__Transfer
from tests.unit.sync.vault_test_env   import Vault__Test_Env

FAKE_SHARE_RESULT = dict(
    token           = 'cold-idle-7311',
    transfer_id     = 'abc123def456',
    derived_xfer_id = 'abc123def456',
    commit_id       = 'obj-cas-imm-aabbcc',
    folder_hash     = 'deadbeef',
    aes_key_hex     = 'a' * 64,
    file_count      = 3,
    total_bytes     = 4096,
)


class _FakeArgs:
    def __init__(self, directory='.', base_url=None):
        self.directory = directory
        self.base_url  = base_url


def _make_share(vault_dir: str, monkeypatch) -> CLI__Share:
    """Build a CLI__Share with a pre-saved token and patched Vault__Transfer.share."""
    token_store = CLI__Token_Store()
    token_store.save_token('test-access-token', vault_dir)

    monkeypatch.setattr(Vault__Transfer, 'setup',  lambda self: self)
    monkeypatch.setattr(Vault__Transfer, 'share',  lambda self, d, token_str=None: FAKE_SHARE_RESULT)

    return CLI__Share(token_store=token_store)


class Test_CLI__Share:

    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_single_vault(files={'hello.txt': 'hi'})

    @classmethod
    def teardown_class(cls):
        if cls._env:
            cls._env.cleanup_snapshot()

    def setup_method(self):
        self.snap  = self._env.restore()
        self.vault = self.snap.vault_dir

    def teardown_method(self):
        self.snap.cleanup()

    def test_cmd_share_prints_token(self, monkeypatch, capsys):
        cli = _make_share(self.vault, monkeypatch)
        monkeypatch.setattr('sgit_ai.cli.CLI__Input.CLI__Input.prompt', lambda self, msg: None)
        cli.cmd_share(_FakeArgs(directory=self.vault))
        out = capsys.readouterr().out
        assert 'cold-idle-7311' in out

    def test_cmd_share_prints_transfer_id(self, monkeypatch, capsys):
        cli = _make_share(self.vault, monkeypatch)
        monkeypatch.setattr('sgit_ai.cli.CLI__Input.CLI__Input.prompt', lambda self, msg: None)
        cli.cmd_share(_FakeArgs(directory=self.vault))
        out = capsys.readouterr().out
        assert 'abc123def456' in out

    def test_cmd_share_prints_file_count(self, monkeypatch, capsys):
        cli = _make_share(self.vault, monkeypatch)
        monkeypatch.setattr('sgit_ai.cli.CLI__Input.CLI__Input.prompt', lambda self, msg: None)
        cli.cmd_share(_FakeArgs(directory=self.vault))
        out = capsys.readouterr().out
        assert '3 file(s)' in out

    def test_cmd_share_prints_upload_complete(self, monkeypatch, capsys):
        cli = _make_share(self.vault, monkeypatch)
        monkeypatch.setattr('sgit_ai.cli.CLI__Input.CLI__Input.prompt', lambda self, msg: None)
        cli.cmd_share(_FakeArgs(directory=self.vault))
        out = capsys.readouterr().out
        assert 'Upload complete' in out

    def test_cmd_share_writes_history_file(self, monkeypatch, capsys):
        cli = _make_share(self.vault, monkeypatch)
        monkeypatch.setattr('sgit_ai.cli.CLI__Input.CLI__Input.prompt', lambda self, msg: None)
        cli.cmd_share(_FakeArgs(directory=self.vault))
        history_path = os.path.join(self.vault, '.sg_vault', 'local', SHARE_HISTORY_FILE)
        assert os.path.isfile(history_path)

    def test_cmd_share_history_has_token(self, monkeypatch, capsys):
        cli = _make_share(self.vault, monkeypatch)
        monkeypatch.setattr('sgit_ai.cli.CLI__Input.CLI__Input.prompt', lambda self, msg: None)
        cli.cmd_share(_FakeArgs(directory=self.vault))
        history_path = os.path.join(self.vault, '.sg_vault', 'local', SHARE_HISTORY_FILE)
        with open(history_path) as f:
            history = json.load(f)
        assert history[0]['token'] == 'cold-idle-7311'

    def test_cmd_share_history_appends_on_second_call(self, monkeypatch, capsys):
        cli = _make_share(self.vault, monkeypatch)
        monkeypatch.setattr('sgit_ai.cli.CLI__Input.CLI__Input.prompt', lambda self, msg: None)
        cli.cmd_share(_FakeArgs(directory=self.vault))
        cli.cmd_share(_FakeArgs(directory=self.vault))
        history_path = os.path.join(self.vault, '.sg_vault', 'local', SHARE_HISTORY_FILE)
        with open(history_path) as f:
            history = json.load(f)
        assert len(history) == 2

    def test_cmd_share_no_token_exits(self, monkeypatch):
        """If no saved token and CLI__Input returns None, sys.exit(1) is called."""
        token_store = CLI__Token_Store()  # no token saved
        cli = CLI__Share(token_store=token_store)
        monkeypatch.setattr('sgit_ai.cli.CLI__Input.CLI__Input.prompt', lambda self, msg: None)
        with pytest.raises(SystemExit) as exc_info:
            cli.cmd_share(_FakeArgs(directory=self.vault))
        assert exc_info.value.code == 1

    def test_cmd_share_error_from_transfer_exits(self, monkeypatch, capsys):
        """RuntimeError from Vault__Transfer.share prints error and exits."""
        token_store = CLI__Token_Store()
        token_store.save_token('test-token', self.vault)
        monkeypatch.setattr(Vault__Transfer, 'setup', lambda self: self)
        monkeypatch.setattr(Vault__Transfer, 'share',
                            lambda self, d, token_str=None: (_ for _ in ()).throw(
                                RuntimeError('no vault key')))
        monkeypatch.setattr('sgit_ai.cli.CLI__Input.CLI__Input.prompt', lambda self, msg: None)
        cli = CLI__Share(token_store=token_store)
        with pytest.raises(SystemExit) as exc_info:
            cli.cmd_share(_FakeArgs(directory=self.vault))
        assert exc_info.value.code == 1
        assert 'no vault key' in capsys.readouterr().err


class Test_CLI__Share__History:
    """Tests for _history_path and _append_share_history."""

    def setup_method(self):
        import tempfile, shutil
        self.tmp   = tempfile.mkdtemp()
        # minimal .sg_vault/local structure
        local_dir = os.path.join(self.tmp, '.sg_vault', 'local')
        os.makedirs(local_dir)
        self.share = CLI__Share(token_store=CLI__Token_Store())

    def teardown_method(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_history_path_inside_sg_vault_local(self):
        path = self.share._history_path(self.tmp)
        assert path == os.path.join(self.tmp, '.sg_vault', 'local', SHARE_HISTORY_FILE)

    def test_append_creates_file(self):
        self.share._append_share_history(self.tmp, {'token': 'abc'})
        path = self.share._history_path(self.tmp)
        assert os.path.isfile(path)

    def test_append_content_correct(self):
        self.share._append_share_history(self.tmp, {'token': 'abc', 'count': 1})
        with open(self.share._history_path(self.tmp)) as f:
            data = json.load(f)
        assert data[0]['token'] == 'abc'

    def test_append_multiple_entries(self):
        self.share._append_share_history(self.tmp, {'n': 1})
        self.share._append_share_history(self.tmp, {'n': 2})
        with open(self.share._history_path(self.tmp)) as f:
            data = json.load(f)
        assert len(data) == 2
        assert data[1]['n'] == 2

    def test_append_corrupt_history_file_resets(self):
        """When history file exists but has invalid JSON, it is reset to []."""
        path = self.share._history_path(self.tmp)
        with open(path, 'w') as f:
            f.write('not valid json {{{')
        self.share._append_share_history(self.tmp, {'token': 'abc'})
        with open(path) as f:
            data = json.load(f)
        assert len(data) == 1
        assert data[0]['token'] == 'abc'


class Test_CLI__Share__PromptPaths:
    """Tests for lines 47-48 (prompt supplies token) and 106-107 (browser open)."""

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

    def test_prompt_supplies_access_token(self, monkeypatch, capsys):
        """When load_token returns '' and prompt returns a token, it is used."""
        token_store = CLI__Token_Store()   # no pre-saved token
        monkeypatch.setattr(Vault__Transfer, 'setup', lambda self: self)
        monkeypatch.setattr(Vault__Transfer, 'share',
                            lambda self, d, token_str=None: FAKE_SHARE_RESULT)
        # First prompt (for access token) returns a value; second (browser) returns None
        responses = iter(['my-typed-token', None])
        monkeypatch.setattr('sgit_ai.cli.CLI__Input.CLI__Input.prompt',
                            lambda self, msg: next(responses))
        cli = CLI__Share(token_store=token_store)
        cli.cmd_share(_FakeArgs(directory=self.vault))
        out = capsys.readouterr().out
        assert 'cold-idle-7311' in out   # share succeeded

    def test_browser_opened_when_prompt_returns_y(self, monkeypatch, capsys):
        """When browser prompt returns 'y', webbrowser.open is called."""
        cli = _make_share(self.vault, monkeypatch)
        opened_urls = []
        import webbrowser
        monkeypatch.setattr(webbrowser, 'open', lambda url: opened_urls.append(url))
        # First call is for browser prompt — return 'y'
        monkeypatch.setattr('sgit_ai.cli.CLI__Input.CLI__Input.prompt',
                            lambda self, msg: 'y')
        cli.cmd_share(_FakeArgs(directory=self.vault))
        capsys.readouterr()
        assert len(opened_urls) == 1
        assert 'cold-idle-7311' in opened_urls[0]
