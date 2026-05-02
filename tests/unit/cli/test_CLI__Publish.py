"""Unit tests for CLI__Publish.cmd_publish.

Strategy: monkeypatch Vault__Transfer.collect_head_files and Vault__Transfer.upload
to avoid real HTTP calls; pre-save an access token via CLI__Token_Store.
"""
import os
import sys

import pytest

from sgit_ai.cli.CLI__Publish     import CLI__Publish
from sgit_ai.cli.CLI__Token_Store import CLI__Token_Store
from sgit_ai.transfer.Vault__Transfer import Vault__Transfer
from tests.unit.sync.vault_test_env   import Vault__Test_Env

FAKE_FILES   = {'readme.txt': b'hello', 'data/file.bin': b'\x01\x02'}
FAKE_XFER_ID = 'deadbeef1234'


class _FakeArgs:
    def __init__(self, directory='.', token=None, no_inner_encrypt=False, base_url=None):
        self.directory      = directory
        self.token          = token
        self.no_inner_encrypt = no_inner_encrypt
        self.base_url       = base_url


def _make_publish(vault_dir: str, monkeypatch) -> CLI__Publish:
    """Build a CLI__Publish with a pre-saved token and patched transfer methods."""
    token_store = CLI__Token_Store()
    token_store.save_token('test-access-token', vault_dir)

    monkeypatch.setattr(Vault__Transfer, 'collect_head_files',
                        lambda self, d: (FAKE_FILES, 'commit-abc'))
    monkeypatch.setattr(Vault__Transfer, 'upload',
                        lambda self, blob, transfer_id=None, content_type='application/octet-stream': FAKE_XFER_ID)

    return CLI__Publish(token_store=token_store)


class Test_CLI__Publish:

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

    def test_cmd_publish_prints_upload_complete(self, monkeypatch, capsys):
        cli = _make_publish(self.vault, monkeypatch)
        cli.cmd_publish(_FakeArgs(directory=self.vault))
        assert 'Upload complete' in capsys.readouterr().out

    def test_cmd_publish_prints_token(self, monkeypatch, capsys):
        cli = _make_publish(self.vault, monkeypatch)
        cli.cmd_publish(_FakeArgs(directory=self.vault, token='cold-idle-7311'))
        assert 'cold-idle-7311' in capsys.readouterr().out

    def test_cmd_publish_prints_file_count(self, monkeypatch, capsys):
        cli = _make_publish(self.vault, monkeypatch)
        cli.cmd_publish(_FakeArgs(directory=self.vault))
        assert '2 file(s)' in capsys.readouterr().out

    def test_cmd_publish_prints_url(self, monkeypatch, capsys):
        cli = _make_publish(self.vault, monkeypatch)
        cli.cmd_publish(_FakeArgs(directory=self.vault, token='cold-idle-7311'))
        out = capsys.readouterr().out
        assert 'send.sgraph.ai' in out

    def test_cmd_publish_no_inner_encrypt(self, monkeypatch, capsys):
        cli = _make_publish(self.vault, monkeypatch)
        cli.cmd_publish(_FakeArgs(directory=self.vault, no_inner_encrypt=True))
        out = capsys.readouterr().out
        assert 'none (plain zip)' in out

    def test_cmd_publish_with_inner_encrypt(self, monkeypatch, capsys):
        cli = _make_publish(self.vault, monkeypatch)
        cli.cmd_publish(_FakeArgs(directory=self.vault, no_inner_encrypt=False))
        out = capsys.readouterr().out
        assert 'vault key' in out

    def test_cmd_publish_no_token_exits(self, monkeypatch):
        """No saved token + CLI__Input returns None → sys.exit(1)."""
        cli = CLI__Publish(token_store=CLI__Token_Store())  # no token saved
        monkeypatch.setattr('sgit_ai.cli.CLI__Input.CLI__Input.prompt', lambda self, msg: None)
        with pytest.raises(SystemExit) as exc_info:
            cli.cmd_publish(_FakeArgs(directory=self.vault))
        assert exc_info.value.code == 1

    def test_cmd_publish_collect_error_exits(self, monkeypatch, capsys):
        """RuntimeError from collect_head_files → prints error, sys.exit(1)."""
        token_store = CLI__Token_Store()
        token_store.save_token('test-token', self.vault)
        monkeypatch.setattr(Vault__Transfer, 'collect_head_files',
                            lambda self, d: (_ for _ in ()).throw(RuntimeError('not a vault')))
        cli = CLI__Publish(token_store=token_store)
        with pytest.raises(SystemExit) as exc_info:
            cli.cmd_publish(_FakeArgs(directory=self.vault))
        assert exc_info.value.code == 1
        assert 'not a vault' in capsys.readouterr().err

    def test_cmd_publish_upload_error_exits(self, monkeypatch, capsys):
        """Exception from transfer.upload → prints error, sys.exit(1)."""
        token_store = CLI__Token_Store()
        token_store.save_token('test-token', self.vault)
        monkeypatch.setattr(Vault__Transfer, 'collect_head_files',
                            lambda self, d: (FAKE_FILES, 'cid'))
        monkeypatch.setattr(Vault__Transfer, 'upload',
                            lambda self, blob, **kw: (_ for _ in ()).throw(RuntimeError('network down')))
        cli = CLI__Publish(token_store=token_store)
        with pytest.raises(SystemExit) as exc_info:
            cli.cmd_publish(_FakeArgs(directory=self.vault))
        assert exc_info.value.code == 1
        assert 'network down' in capsys.readouterr().err

    def test_cmd_publish_with_explicit_token(self, monkeypatch, capsys):
        """Passing token= on args uses it instead of generating one."""
        cli = _make_publish(self.vault, monkeypatch)
        cli.cmd_publish(_FakeArgs(directory=self.vault, token='warm-sun-1234'))
        out = capsys.readouterr().out
        assert 'warm-sun-1234' in out

    def test_cmd_publish_prompt_supplies_token(self, monkeypatch, capsys):
        """When no saved token and prompt returns a value, it is used (lines 30-31)."""
        # No pre-saved token
        token_store = CLI__Token_Store()
        monkeypatch.setattr(Vault__Transfer, 'collect_head_files',
                            lambda self, d: (FAKE_FILES, 'commit-abc'))
        monkeypatch.setattr(Vault__Transfer, 'upload',
                            lambda self, blob, transfer_id=None, content_type='application/octet-stream': FAKE_XFER_ID)
        monkeypatch.setattr('sgit_ai.cli.CLI__Input.CLI__Input.prompt',
                            lambda self, msg: 'prompted-access-token')
        cli = CLI__Publish(token_store=token_store)
        cli.cmd_publish(_FakeArgs(directory=self.vault))
        out = capsys.readouterr().out
        assert 'Upload complete' in out

    def test_cmd_publish_invalid_vault_key_exception_silenced_lines_64_65(self, monkeypatch, capsys, tmp_path):
        """Lines 64-65: vault_key file exists but derive_keys raises → except catches, vault_id=''."""
        import os
        sg_dir    = tmp_path / '.sg_vault'
        local_dir = sg_dir / 'local'
        local_dir.mkdir(parents=True)
        # Write an invalid vault key so derive_keys_from_vault_key raises
        vault_key_path = sg_dir / 'local' / 'vault_key'
        vault_key_path.write_text('THIS-IS-NOT-A-VALID-VAULT-KEY')
        token_store = CLI__Token_Store()
        token_store.save_token('access-tok', str(tmp_path))
        monkeypatch.setattr(Vault__Transfer, 'collect_head_files',
                            lambda self, d: (FAKE_FILES, 'commit-abc'))
        monkeypatch.setattr(Vault__Transfer, 'upload',
                            lambda self, blob, transfer_id=None, content_type='application/octet-stream': FAKE_XFER_ID)
        cli = CLI__Publish(token_store=token_store)
        cli.cmd_publish(_FakeArgs(directory=str(tmp_path), no_inner_encrypt=False))
        out = capsys.readouterr().out
        assert 'Upload complete' in out   # completes despite the key error

    def test_cmd_publish_no_vault_key_file_uses_empty_vault_id(self, monkeypatch, capsys, tmp_path):
        """When vault_key file is absent and no_inner_encrypt=False, vault_id='' (lines 63-65)."""
        import os
        # Create minimal directory with .sg_vault structure but NO vault_key
        sg_dir    = tmp_path / '.sg_vault'
        local_dir = sg_dir / 'local'
        local_dir.mkdir(parents=True)
        # Save a token so no prompt is needed
        token_store = CLI__Token_Store()
        token_store.save_token('access-tok', str(tmp_path))
        monkeypatch.setattr(Vault__Transfer, 'collect_head_files',
                            lambda self, d: (FAKE_FILES, 'commit-abc'))
        monkeypatch.setattr(Vault__Transfer, 'upload',
                            lambda self, blob, transfer_id=None, content_type='application/octet-stream': FAKE_XFER_ID)
        cli = CLI__Publish(token_store=token_store)
        # no_inner_encrypt=False triggers the vault_key path; file doesn't exist → vault_id=''
        cli.cmd_publish(_FakeArgs(directory=str(tmp_path), no_inner_encrypt=False))
        out = capsys.readouterr().out
        assert 'none (plain zip)' in out   # vault_read_key remained None
