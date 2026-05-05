"""Unit tests for CLI__Share.cmd_receive and cmd_send.

Strategy: monkeypatch Vault__Transfer.receive / send_raw to return canned
results so no real HTTP calls are made.
"""
import io
import os
import sys
import types as _types

import pytest

from sgit_ai.cli.CLI__Share           import CLI__Share
from sgit_ai.cli.CLI__Token_Store     import CLI__Token_Store
from sgit_ai.network.transfer.Vault__Transfer import Vault__Transfer


# ---------------------------------------------------------------------------
# Canned responses (module-level so lambdas can capture them without 'self')
# ---------------------------------------------------------------------------

FAKE_RECEIVE_ZIP = dict(
    payload_type = 'zip',
    transfer_id  = 'abc123def456',
    files        = {
        'hello.txt':    b'Hello, world!',
        'sub/notes.md': b'# Notes',
        '__share__ff/_manifest.json': b'{}',   # should be skipped
    },
    file_count   = 3,
    text         = None,
    raw_bytes    = None,
    filename     = 'vault-snapshot.zip',
)

FAKE_RECEIVE_TEXT = dict(
    payload_type = 'text',
    transfer_id  = 'deadbeef0000',
    files        = {},
    file_count   = 0,
    text         = 'my secret message\nline 2',
    raw_bytes    = None,
    filename     = None,
)

FAKE_RECEIVE_BIN = dict(
    payload_type = 'binary',
    transfer_id  = 'bbbbb0000000',
    files        = {},
    file_count   = 0,
    text         = None,
    raw_bytes    = b'\x00\x01\x02\x03binary',
    filename     = 'data.bin',
)

FAKE_SEND_RESULT = dict(
    token           = 'warm-echo-5555',
    transfer_id     = 'eeee55550000',
    derived_xfer_id = 'eeee55550000',
    aes_key_hex     = 'b' * 64,
    total_bytes     = 64,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _args(**kwargs):
    ns = _types.SimpleNamespace(token=None, output_dir=None, base_url=None,
                                text=None, file=None)
    for k, v in kwargs.items():
        setattr(ns, k, v)
    return ns


def _make_cli(monkeypatch) -> CLI__Share:
    """CLI__Share with token pre-loaded and Vault__Transfer.setup patched."""
    token_store = CLI__Token_Store()
    monkeypatch.setattr(Vault__Transfer, 'setup', lambda self: self)
    monkeypatch.setattr(CLI__Token_Store, 'load_token', lambda self, d: 'test-token')
    return CLI__Share(token_store=token_store)


# ---------------------------------------------------------------------------
# cmd_receive — zip payload (vault snapshot)
# ---------------------------------------------------------------------------

class Test_cmd_receive__zip:

    def test_receive_zip_extracts_files(self, monkeypatch, tmp_path):
        monkeypatch.setattr(Vault__Transfer, 'receive', lambda self, tok: FAKE_RECEIVE_ZIP)
        dest = str(tmp_path / 'out')
        _make_cli(monkeypatch).cmd_receive(_args(token='word-word-1234', output_dir=dest))
        assert os.path.isfile(os.path.join(dest, 'hello.txt'))
        assert os.path.isfile(os.path.join(dest, 'sub', 'notes.md'))

    def test_receive_zip_skips_manifest(self, monkeypatch, tmp_path):
        monkeypatch.setattr(Vault__Transfer, 'receive', lambda self, tok: FAKE_RECEIVE_ZIP)
        dest = str(tmp_path / 'out')
        _make_cli(monkeypatch).cmd_receive(_args(token='word-word-1234', output_dir=dest))
        assert not os.path.exists(os.path.join(dest, '__share__ff', '_manifest.json'))

    def test_receive_zip_prints_file_list(self, monkeypatch, capsys, tmp_path):
        monkeypatch.setattr(Vault__Transfer, 'receive', lambda self, tok: FAKE_RECEIVE_ZIP)
        _make_cli(monkeypatch).cmd_receive(_args(token='word-word-1234', output_dir=str(tmp_path)))
        out = capsys.readouterr().out
        assert 'hello.txt' in out
        assert 'sub/notes.md' in out

    def test_receive_zip_prints_transfer_id(self, monkeypatch, capsys, tmp_path):
        monkeypatch.setattr(Vault__Transfer, 'receive', lambda self, tok: FAKE_RECEIVE_ZIP)
        _make_cli(monkeypatch).cmd_receive(_args(token='word-word-1234', output_dir=str(tmp_path)))
        assert 'abc123def456' in capsys.readouterr().out

    def test_receive_zip_file_contents_correct(self, monkeypatch, tmp_path):
        monkeypatch.setattr(Vault__Transfer, 'receive', lambda self, tok: FAKE_RECEIVE_ZIP)
        dest = str(tmp_path / 'out')
        _make_cli(monkeypatch).cmd_receive(_args(token='word-word-1234', output_dir=dest))
        assert open(os.path.join(dest, 'hello.txt'), 'rb').read() == b'Hello, world!'


# ---------------------------------------------------------------------------
# cmd_receive — text payload (SG/Send text secret)
# ---------------------------------------------------------------------------

class Test_cmd_receive__text:

    def test_receive_text_prints_content(self, monkeypatch, capsys):
        monkeypatch.setattr(Vault__Transfer, 'receive', lambda self, tok: FAKE_RECEIVE_TEXT)
        _make_cli(monkeypatch).cmd_receive(_args(token='word-word-0001'))
        out = capsys.readouterr().out
        assert 'my secret message' in out
        assert 'line 2' in out

    def test_receive_text_prints_transfer_id(self, monkeypatch, capsys):
        monkeypatch.setattr(Vault__Transfer, 'receive', lambda self, tok: FAKE_RECEIVE_TEXT)
        _make_cli(monkeypatch).cmd_receive(_args(token='word-word-0001'))
        assert 'deadbeef0000' in capsys.readouterr().out

    def test_receive_text_with_filename_prints_header_lines_168_170(self, monkeypatch, capsys):
        """Lines 168-170: text payload with filename → prints Filename and Type lines."""
        fake = dict(FAKE_RECEIVE_TEXT, filename='secret.txt')
        monkeypatch.setattr(Vault__Transfer, 'receive', lambda self, tok: fake)
        _make_cli(monkeypatch).cmd_receive(_args(token='word-word-0001'))
        out = capsys.readouterr().out
        assert 'Filename:' in out
        assert 'secret.txt' in out
        assert 'Type:' in out


# ---------------------------------------------------------------------------
# cmd_receive — binary payload
# ---------------------------------------------------------------------------

class Test_cmd_receive__binary:

    def test_receive_binary_saves_file(self, monkeypatch, tmp_path):
        monkeypatch.setattr(Vault__Transfer, 'receive', lambda self, tok: FAKE_RECEIVE_BIN)
        dest = str(tmp_path / 'output.bin')
        _make_cli(monkeypatch).cmd_receive(_args(token='word-word-0002', output_dir=dest))
        assert open(dest, 'rb').read() == b'\x00\x01\x02\x03binary'

    def test_receive_binary_uses_envelope_filename_as_default(self, monkeypatch, tmp_path):
        monkeypatch.setattr(Vault__Transfer, 'receive', lambda self, tok: FAKE_RECEIVE_BIN)
        orig_cwd = os.getcwd()
        os.chdir(str(tmp_path))
        try:
            _make_cli(monkeypatch).cmd_receive(_args(token='word-word-0002'))
        finally:
            os.chdir(orig_cwd)
        assert os.path.isfile(str(tmp_path / 'data.bin'))


# ---------------------------------------------------------------------------
# cmd_receive — error handling
# ---------------------------------------------------------------------------

class Test_cmd_receive__errors:

    def test_runtime_error_exits(self, monkeypatch, capsys):
        monkeypatch.setattr(Vault__Transfer, 'receive',
                            lambda self, tok: (_ for _ in ()).throw(
                                RuntimeError('not found')))
        cli = _make_cli(monkeypatch)
        with pytest.raises(SystemExit) as exc:
            cli.cmd_receive(_args(token='bad-token-0000'))
        assert exc.value.code == 1
        assert 'not found' in capsys.readouterr().err


# ---------------------------------------------------------------------------
# cmd_send
# ---------------------------------------------------------------------------

class Test_cmd_send:

    def setup_method(self):
        import tempfile
        self.tmp = tempfile.mkdtemp()

    def teardown_method(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _cli(self, monkeypatch) -> CLI__Share:
        monkeypatch.setattr(Vault__Transfer, 'setup',    lambda self: self)
        monkeypatch.setattr(Vault__Transfer, 'send_raw', lambda self, c, filename=None: FAKE_SEND_RESULT)
        monkeypatch.setattr(CLI__Token_Store, 'load_token', lambda self, d: 'test-token')
        monkeypatch.setattr('sgit_ai.cli.CLI__Input.CLI__Input.prompt', lambda self, msg: None)
        return CLI__Share(token_store=CLI__Token_Store())

    def test_send_text_prints_token(self, monkeypatch, capsys):
        self._cli(monkeypatch).cmd_send(_args(text='hello secret'))
        assert 'warm-echo-5555' in capsys.readouterr().out

    def test_send_text_prints_transfer_id(self, monkeypatch, capsys):
        self._cli(monkeypatch).cmd_send(_args(text='hello secret'))
        assert 'eeee55550000' in capsys.readouterr().out

    def test_send_text_prints_receive_hint(self, monkeypatch, capsys):
        self._cli(monkeypatch).cmd_send(_args(text='hello secret'))
        assert 'sgit receive' in capsys.readouterr().out

    def test_send_file(self, monkeypatch, capsys):
        file_path = os.path.join(self.tmp, 'secret.txt')
        open(file_path, 'w').write('file contents')
        self._cli(monkeypatch).cmd_send(_args(file=file_path))
        assert 'warm-echo-5555' in capsys.readouterr().out

    def test_send_missing_file_exits(self, monkeypatch, capsys):
        monkeypatch.setattr(Vault__Transfer, 'setup', lambda self: self)
        monkeypatch.setattr(CLI__Token_Store, 'load_token', lambda self, d: 'tok')
        cli = CLI__Share(token_store=CLI__Token_Store())
        with pytest.raises(SystemExit) as exc:
            cli.cmd_send(_args(file='/nonexistent/path.txt'))
        assert exc.value.code == 1

    def test_send_runtime_error_exits(self, monkeypatch, capsys):
        monkeypatch.setattr(Vault__Transfer, 'setup', lambda self: self)
        monkeypatch.setattr(Vault__Transfer, 'send_raw',
                            lambda self, c, filename=None: (_ for _ in ()).throw(
                                RuntimeError('upload failed')))
        monkeypatch.setattr(CLI__Token_Store, 'load_token', lambda self, d: 'tok')
        monkeypatch.setattr('sgit_ai.cli.CLI__Input.CLI__Input.prompt', lambda self, msg: None)
        cli = CLI__Share(token_store=CLI__Token_Store())
        with pytest.raises(SystemExit) as exc:
            cli.cmd_send(_args(text='oops'))
        assert exc.value.code == 1
        assert 'upload failed' in capsys.readouterr().err

    def test_send_opens_browser_when_answered_y_lines_251_252(self, monkeypatch, capsys):
        """Lines 251-252: prompt returns 'y' → webbrowser.open called."""
        import webbrowser
        opened = []
        # Build CLI first, then override prompt AFTER _cli patches it to None
        cli = self._cli(monkeypatch)
        monkeypatch.setattr(webbrowser, 'open', lambda url: opened.append(url))
        monkeypatch.setattr('sgit_ai.cli.CLI__Input.CLI__Input.prompt', lambda self, msg: 'y')
        cli.cmd_send(_args(text='hello'))
        capsys.readouterr()
        assert len(opened) == 1
        assert 'warm-echo-5555' in opened[0]

    def test_send_no_text_no_file_reads_stdin_lines_203_208(self, monkeypatch, capsys, tmp_path):
        """Lines 203-208: no --text and no --file → reads from stdin."""
        import io, sys
        monkeypatch.setattr(sys, 'stdin', io.TextIOWrapper(io.BytesIO(b'stdin content')))
        monkeypatch.setattr('sgit_ai.cli.CLI__Input.CLI__Input.prompt', lambda self, msg: None)
        self._cli(monkeypatch).cmd_send(_args())
        assert 'warm-echo-5555' in capsys.readouterr().out

    def test_send_no_text_no_file_empty_stdin_exits(self, monkeypatch, capsys):
        """Lines 204-206: stdin is empty → sys.exit(1)."""
        import io, sys
        monkeypatch.setattr(sys, 'stdin', io.TextIOWrapper(io.BytesIO(b'')))
        monkeypatch.setattr(Vault__Transfer, 'setup', lambda self: self)
        monkeypatch.setattr(CLI__Token_Store, 'load_token', lambda self, d: 'tok')
        cli = CLI__Share(token_store=CLI__Token_Store())
        with pytest.raises(SystemExit) as exc:
            cli.cmd_send(_args())
        assert exc.value.code == 1


# ---------------------------------------------------------------------------
# Vault__Transfer.receive — auto-detection (unit, no HTTP)
# ---------------------------------------------------------------------------

class Test_Vault__Transfer__receive_format:

    def _make_transfer(self, monkeypatch, encrypted_bytes):
        from sgit_ai.network.api.API__Transfer        import API__Transfer
        from sgit_ai.crypto.Vault__Crypto     import Vault__Crypto
        from sgit_ai.network.transfer.Vault__Transfer import Vault__Transfer

        crypto = Vault__Crypto()
        api    = object.__new__(API__Transfer)
        monkeypatch.setattr(api, 'download_file', lambda tid: encrypted_bytes)
        monkeypatch.setattr(api, 'info', lambda tid: {'file_size_bytes': len(encrypted_bytes)})
        return Vault__Transfer(api=api, crypto=crypto), crypto

    def _encrypt(self, crypto, content: bytes) -> bytes:
        from sgit_ai.network.transfer.Simple_Token     import Simple_Token
        from sgit_ai.safe_types.Safe_Str__Simple_Token import Safe_Str__Simple_Token
        key = Simple_Token(token=Safe_Str__Simple_Token('cold-idle-7311')).aes_key()
        return crypto.encrypt(key, content)

    def test_zip_detected(self, monkeypatch):
        import zipfile
        from sgit_ai.crypto.Vault__Crypto import Vault__Crypto
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w') as zf:
            zf.writestr('file.txt', b'hello')
        crypto = Vault__Crypto()
        enc    = crypto.encrypt(Simple_Token_key('cold-idle-7311'), buf.getvalue())
        transfer, _ = self._make_transfer(monkeypatch, enc)
        result = transfer.receive('cold-idle-7311')
        assert result['payload_type'] == 'zip'
        assert 'file.txt' in result['files']

    def test_text_detected(self, monkeypatch):
        from sgit_ai.crypto.Vault__Crypto import Vault__Crypto
        crypto = Vault__Crypto()
        enc    = crypto.encrypt(Simple_Token_key('cold-idle-7311'), b'hello plain text')
        transfer, _ = self._make_transfer(monkeypatch, enc)
        result = transfer.receive('cold-idle-7311')
        assert result['payload_type'] == 'text'
        assert result['text'] == 'hello plain text'


def Simple_Token_key(token_str: str) -> bytes:
    from sgit_ai.network.transfer.Simple_Token             import Simple_Token
    from sgit_ai.safe_types.Safe_Str__Simple_Token import Safe_Str__Simple_Token
    return Simple_Token(token=Safe_Str__Simple_Token(token_str)).aes_key()
