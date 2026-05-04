"""Tests for `sgit create` — one-shot init + commit + push."""
import os
import sys
import tempfile
import shutil

import pytest

from sgit_ai.cli.CLI__Main              import CLI__Main
from sgit_ai.api.Vault__API__In_Memory  import Vault__API__In_Memory
from sgit_ai.crypto.Vault__Crypto       import Vault__Crypto
from sgit_ai.sync.Vault__Sync           import Vault__Sync
from sgit_ai.cli.CLI__Create            import CLI__Create


def _parser():
    return CLI__Main().build_parser()


# ---------------------------------------------------------------------------
# Parser tests
# ---------------------------------------------------------------------------

class Test_CLI__Create_Parser:

    def test_create_parser_exists(self):
        args = _parser().parse_args(['create', 'my-project'])
        assert args.vault_name == 'my-project'
        assert args.no_push is False
        assert args.vault_key is None

    def test_no_push_flag(self):
        args = _parser().parse_args(['create', 'my-project', '--no-push'])
        assert args.no_push is True

    def test_vault_key_flag(self):
        args = _parser().parse_args(['create', 'my-project', '--vault-key', 'pass:vlt01'])
        assert args.vault_key == 'pass:vlt01'

    def test_vault_name_required(self):
        with pytest.raises(SystemExit):
            _parser().parse_args(['create'])


# ---------------------------------------------------------------------------
# CLI__Create unit tests
# ---------------------------------------------------------------------------

class Test_CLI__Create_Unit:

    def test_vault_ref_defaults_none(self):
        c = CLI__Create()
        assert c.vault_ref is None

    def test_token_store_defaults_none(self):
        c = CLI__Create()
        assert c.token_store is None

    def test_cmd_create_missing_name_exits(self, capsys):
        c = CLI__Create()

        class FakeArgs:
            vault_name = None
            directory  = None
            vault_key  = None
            token      = None
            base_url   = None
            no_push    = False

        with pytest.raises(SystemExit) as exc_info:
            c.cmd_create(FakeArgs())
        assert exc_info.value.code == 1


# ---------------------------------------------------------------------------
# Functional tests using in-memory API
# ---------------------------------------------------------------------------

class Test_CLI__Create_Functional:
    """End-to-end create using the in-memory server."""

    def setup_method(self):
        self.tmp = tempfile.mkdtemp()
        self.api = Vault__API__In_Memory()
        self.api.setup()

    def teardown_method(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run_create(self, vault_name, push=False, extra_files=None):
        """Helper: run cmd_create against in-memory API."""
        from sgit_ai.cli.CLI__Create import CLI__Create

        vault_dir = os.path.join(self.tmp, vault_name)
        if extra_files:
            os.makedirs(vault_dir, exist_ok=True)
            for name, content in extra_files.items():
                path = os.path.join(vault_dir, name)
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, 'w') as f:
                    f.write(content)

        c = CLI__Create()

        class FakeArgs:
            pass
        a            = FakeArgs()
        a.vault_name = vault_name
        a.directory  = vault_dir
        a.vault_key  = None
        a.token      = None
        a.base_url   = None
        a.no_push    = not push

        # Inject in-memory sync
        sync = Vault__Sync(crypto=Vault__Crypto(), api=self.api)
        original_init    = sync.init
        original_commit  = sync.commit
        original_push    = sync.push

        results = {}

        def patched_init(directory, **kw):
            r = original_init(directory, **kw)
            results['init'] = r
            return r

        def patched_commit(directory, **kw):
            r = original_commit(directory, **kw)
            results['commit'] = r
            return r

        def patched_push(directory, **kw):
            r = original_push(directory, **kw)
            results['push'] = r
            return r

        sync.init   = patched_init
        sync.commit = patched_commit
        sync.push   = patched_push

        # Monkeypatch Vault__Sync construction inside CLI__Create
        import sgit_ai.cli.CLI__Create as _mod
        original_vault_sync = _mod.Vault__Sync

        class FakeVaultSync(Vault__Sync):
            def __init__(self, **kw):
                super().__init__(**kw)
                # Replace api with in-memory api
                self.api = c._test_api if hasattr(c, '_test_api') else self.api

        c._test_api = self.api

        # Directly invoke create with patched sync
        _mod.Vault__Sync = lambda **kw: sync
        try:
            c.cmd_create(a)
        finally:
            _mod.Vault__Sync = original_vault_sync

        return results

    def test_create_initialises_vault(self, capsys):
        results = self._run_create('new-vault-01')
        assert 'init' in results
        assert results['init']['vault_id']
        out = capsys.readouterr().out
        assert 'Vault ready' in out or 'Initialising vault' in out

    def test_create_no_push_skips_push(self, capsys):
        results = self._run_create('new-vault-02', push=False)
        assert 'push' not in results

    def test_create_with_files_commits_them(self, capsys):
        results = self._run_create('new-vault-03',
                                   extra_files={'README.md': 'hello world'})
        assert 'commit' in results

    def test_create_output_mentions_vault_ready(self, capsys):
        self._run_create('new-vault-04')
        out = capsys.readouterr().out
        assert 'Vault ready' in out or 'Initialising vault' in out


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class Test_CLI__Create_EdgeCases:

    def test_create_in_no_walk_up(self):
        from sgit_ai.cli.CLI__Main import CLI__Main
        assert 'create' in CLI__Main._NO_WALK_UP

    def test_create_func_is_wired(self):
        from sgit_ai.cli.CLI__Create import CLI__Create
        cli = CLI__Main()
        p   = cli.build_parser()
        args = p.parse_args(['create', 'test-vault'])
        assert callable(args.func)
        assert args.func == cli.create.cmd_create
