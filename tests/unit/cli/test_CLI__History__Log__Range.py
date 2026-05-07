"""Tests for `history log <range>` — Brief 13."""
import os
import shutil
import types

import pytest

from sgit_ai.cli.CLI__Diff                             import CLI__Diff
from sgit_ai.crypto.Vault__Crypto                       import Vault__Crypto
from sgit_ai.schemas.history.Schema__History_Log_Result import Schema__History_Log_Result
from tests._helpers.vault_test_env                      import Vault__Test_Env


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _MultiCommitEnv:
    """Provides a vault with commits A→B→C→D for range tests (class-level)."""

    _env      = None
    _commit_a = None
    _commit_b = None
    _commit_c = None
    _commit_d = None

    @classmethod
    def build(cls):
        if cls._env is not None:
            return
        from sgit_ai.core.Vault__Sync                  import Vault__Sync
        from sgit_ai.network.api.Vault__API__In_Memory  import Vault__API__In_Memory
        import copy, tempfile

        crypto = Vault__Crypto()
        api    = Vault__API__In_Memory()
        api.setup()
        sync   = Vault__Sync(crypto=crypto, api=api)

        import tempfile as _t
        snap_dir  = _t.mkdtemp()
        vault_dir = os.path.join(snap_dir, 'vault')
        sync.init(vault_dir)

        def _write(rel, content):
            full = os.path.join(vault_dir, rel)
            with open(full, 'w') as f:
                f.write(content)

        _write('a.txt', 'A')
        cls._commit_a = sync.commit(vault_dir, message='commit A')['commit_id']
        _write('b.txt', 'B')
        cls._commit_b = sync.commit(vault_dir, message='commit B')['commit_id']
        _write('c.txt', 'C')
        cls._commit_c = sync.commit(vault_dir, message='commit C')['commit_id']
        _write('d.txt', 'D')
        cls._commit_d = sync.commit(vault_dir, message='commit D')['commit_id']

        class _Snap:
            vault_dir_ = vault_dir
            api_       = api
            sync_      = sync

        cls._env = _Snap

    @classmethod
    def teardown(cls):
        if cls._env and os.path.isdir(os.path.dirname(cls._env.vault_dir_)):
            shutil.rmtree(os.path.dirname(cls._env.vault_dir_), ignore_errors=True)
        cls._env = None


def _args(**kw):
    defaults = dict(directory='.', range_spec='', oneline=False, files=False,
                    patch=False, json_out=False, graph=False, limit=None,
                    file_path=None, vault_key=None)
    defaults.update(kw)
    return types.SimpleNamespace(**defaults)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class Test_CLI__History__Log__Range:

    @classmethod
    def setup_class(cls):
        _MultiCommitEnv.build()
        cls.vault  = _MultiCommitEnv._env.vault_dir_
        cls.A      = _MultiCommitEnv._commit_a
        cls.B      = _MultiCommitEnv._commit_b
        cls.C      = _MultiCommitEnv._commit_c
        cls.D      = _MultiCommitEnv._commit_d
        cls.cli    = CLI__Diff()

    @classmethod
    def teardown_class(cls):
        _MultiCommitEnv.teardown()

    def test_log_with_range_oneline(self, capsys):
        """Range log with --oneline produces oldest-first one-liners."""
        args = _args(directory=self.vault, range_spec=f'{self.A}..{self.D}', oneline=True)
        self.cli.cmd_log_range(args)
        out = capsys.readouterr().out.strip().splitlines()
        # Commits B, C, D in that order (A is exclusive)
        assert len(out) == 3
        # Use 20 chars to get past the common 'obj-cas-imm-' prefix (12 chars)
        assert self.B[:20] in out[0]
        assert self.C[:20] in out[1]
        assert self.D[:20] in out[2]

    def test_log_with_range_files_includes_per_commit_files(self, capsys):
        """--files mode lists added files per commit."""
        args = _args(directory=self.vault, range_spec=f'{self.B}..{self.D}',
                     files=True, oneline=False)
        self.cli.cmd_log_range(args)
        out = capsys.readouterr().out
        assert 'c.txt' in out
        assert 'd.txt' in out

    def test_log_with_range_patch_includes_full_diff(self, capsys):
        """--patch mode shows per-commit file changes (files list + any available diff)."""
        args = _args(directory=self.vault, range_spec=f'{self.B}..{self.C}',
                     patch=True, files=True, oneline=False)
        self.cli.cmd_log_range(args)
        out = capsys.readouterr().out
        # c.txt was added in commit C — should appear in the output
        assert 'c.txt' in out
        # Files section should list it as added
        assert '+ c.txt' in out

    def test_log_with_range_json_round_trips(self, capsys):
        """--json output round-trips through Schema__History_Log_Result.from_json."""
        import json as _json
        args = _args(directory=self.vault, range_spec=f'{self.A}..{self.D}',
                     json_out=True, files=True)
        self.cli.cmd_log_range(args)
        raw = capsys.readouterr().out.strip()
        parsed = _json.loads(raw)
        result = Schema__History_Log_Result.from_json(parsed)
        assert result.json() == parsed
        assert int(result.commit_count) == 3
        assert str(result.schema) == 'history_log_v1'

    def test_log_open_ended_range_to_head(self, capsys):
        """<from>.. walks from from_commit (exclusive) to HEAD."""
        args = _args(directory=self.vault, range_spec=f'{self.B}..', oneline=True)
        self.cli.cmd_log_range(args)
        out = capsys.readouterr().out.strip()
        # C and D must appear; B must not (use 20 chars to go past common prefix)
        assert self.C[:20] in out
        assert self.D[:20] in out
        assert self.B[:20] not in out

    def test_log_open_ended_range_from_root(self, capsys):
        """..<to> walks from root to to_commit inclusive."""
        args = _args(directory=self.vault, range_spec=f'..{self.B}', oneline=True)
        self.cli.cmd_log_range(args)
        out = capsys.readouterr().out.strip()
        # A and B must appear; C and D must not (use 20 chars to go past common prefix)
        assert self.A[:20] in out
        assert self.B[:20] in out
        assert self.C[:20] not in out
        assert self.D[:20] not in out
