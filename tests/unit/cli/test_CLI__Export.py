"""Unit tests for CLI__Export.cmd_export.

Also verifies the bug fix: collect_head_files returns (files, commit_id) tuple;
CLI__Export must unpack it correctly (previously assigned full tuple to files).

Strategy: monkeypatch Vault__Transfer.collect_head_files to return a canned
dict + commit_id tuple. The rest of the command (archive build, file write)
runs against real in-memory data — no HTTP calls needed.
"""
import io
import os
import sys
import zipfile

import pytest

from sgit_ai.cli.CLI__Export          import CLI__Export
from sgit_ai.transfer.Vault__Transfer import Vault__Transfer
from tests.unit.sync.vault_test_env   import Vault__Test_Env

FAKE_FILES = {'hello.txt': b'hello world', 'sub/data.bin': b'\x01\x02\x03'}


class _FakeArgs:
    def __init__(self, directory='.', output=None, token=None, no_inner_encrypt=False):
        self.directory       = directory
        self.output          = output
        self.token           = token
        self.no_inner_encrypt = no_inner_encrypt


def _make_export(monkeypatch) -> CLI__Export:
    monkeypatch.setattr(Vault__Transfer, 'collect_head_files',
                        lambda self, d: (FAKE_FILES, 'commit-abc123'))
    return CLI__Export()


class Test_CLI__Export:

    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_single_vault(files={'init.txt': 'init'})

    @classmethod
    def teardown_class(cls):
        if cls._env:
            cls._env.cleanup_snapshot()

    def setup_method(self):
        self.snap  = self._env.restore()
        self.vault = self.snap.vault_dir

    def teardown_method(self):
        self.snap.cleanup()

    def test_cmd_export_prints_export_complete(self, monkeypatch, capsys, tmp_path):
        cli     = _make_export(monkeypatch)
        outfile = str(tmp_path / 'out.zip')
        cli.cmd_export(_FakeArgs(directory=self.vault, output=outfile))
        assert 'Export complete' in capsys.readouterr().out

    def test_cmd_export_writes_output_file(self, monkeypatch, tmp_path):
        cli     = _make_export(monkeypatch)
        outfile = str(tmp_path / 'archive.zip')
        cli.cmd_export(_FakeArgs(directory=self.vault, output=outfile))
        assert os.path.isfile(outfile)
        assert os.path.getsize(outfile) > 0

    def test_cmd_export_output_is_nonempty_binary(self, monkeypatch, tmp_path):
        """Output is an encrypted archive blob (not a raw zip, despite the extension)."""
        cli     = _make_export(monkeypatch)
        outfile = str(tmp_path / 'archive.zip')
        cli.cmd_export(_FakeArgs(directory=self.vault, output=outfile))
        size = os.path.getsize(outfile)
        assert size > 100  # encrypted archive should be well over 100 bytes

    def test_cmd_export_prints_file_count(self, monkeypatch, capsys, tmp_path):
        cli     = _make_export(monkeypatch)
        outfile = str(tmp_path / 'out.zip')
        cli.cmd_export(_FakeArgs(directory=self.vault, output=outfile))
        assert '2 file(s)' in capsys.readouterr().out

    def test_cmd_export_auto_generates_output_path(self, monkeypatch, capsys):
        """When output=None, a timestamped filename is created in cwd."""
        import os
        cli = _make_export(monkeypatch)
        orig_cwd = os.getcwd()
        try:
            os.chdir(self.vault)
            cli.cmd_export(_FakeArgs(directory=self.vault, output=None))
            out = capsys.readouterr().out
            # The generated path includes '.vault__' prefix
            assert '.vault__' in out
            # Clean up any generated file
            for f in os.listdir('.'):
                if f.startswith('.vault__') and f.endswith('.zip'):
                    os.remove(f)
        finally:
            os.chdir(orig_cwd)

    def test_cmd_export_with_explicit_token(self, monkeypatch, capsys, tmp_path):
        cli     = _make_export(monkeypatch)
        outfile = str(tmp_path / 'out.zip')
        cli.cmd_export(_FakeArgs(directory=self.vault, output=outfile, token='cold-idle-7311'))
        assert 'cold-idle-7311' in capsys.readouterr().out

    def test_cmd_export_no_inner_encrypt(self, monkeypatch, capsys, tmp_path):
        cli     = _make_export(monkeypatch)
        outfile = str(tmp_path / 'out.zip')
        cli.cmd_export(_FakeArgs(directory=self.vault, output=outfile, no_inner_encrypt=True))
        assert 'plain zip' in capsys.readouterr().out

    def test_cmd_export_with_inner_encrypt(self, monkeypatch, capsys, tmp_path):
        cli     = _make_export(monkeypatch)
        outfile = str(tmp_path / 'out.zip')
        cli.cmd_export(_FakeArgs(directory=self.vault, output=outfile, no_inner_encrypt=False))
        assert 'vault key' in capsys.readouterr().out

    def test_cmd_export_collect_error_exits(self, monkeypatch, capsys):
        """RuntimeError from collect_head_files → prints error, sys.exit(1)."""
        monkeypatch.setattr(Vault__Transfer, 'collect_head_files',
                            lambda self, d: (_ for _ in ()).throw(RuntimeError('not a vault')))
        cli = CLI__Export()
        with pytest.raises(SystemExit) as exc_info:
            cli.cmd_export(_FakeArgs(directory=self.vault))
        assert exc_info.value.code == 1
        assert 'not a vault' in capsys.readouterr().err

    def test_cmd_export_tuple_unpacking_bug_is_fixed(self, monkeypatch, tmp_path):
        """Regression: previously files = collect_head_files() got a tuple,
        then files.values() raised AttributeError. Verify it no longer does."""
        cli     = _make_export(monkeypatch)
        outfile = str(tmp_path / 'reg.zip')
        # This would have raised AttributeError before the fix
        cli.cmd_export(_FakeArgs(directory=self.vault, output=outfile))
        assert os.path.isfile(outfile)

    def test_cmd_export_vault_key_read_exception_silenced(self, monkeypatch, tmp_path, capsys):
        """Lines 48-49: vault_key read fails → except silenced, export continues."""
        from sgit_ai.sync.Vault__Storage import Vault__Storage
        # Write garbage to vault_key so derive_keys raises
        vault_key_path = Vault__Storage().vault_key_path(self.vault)
        with open(vault_key_path, 'w') as f:
            f.write('INVALID-NOT-A-VAULT-KEY')
        cli     = _make_export(monkeypatch)
        outfile = str(tmp_path / 'out.zip')
        cli.cmd_export(_FakeArgs(directory=self.vault, output=outfile,
                                 no_inner_encrypt=False))
        # Should succeed (exception silenced) with plain zip output
        out = capsys.readouterr().out
        assert 'plain zip' in out
