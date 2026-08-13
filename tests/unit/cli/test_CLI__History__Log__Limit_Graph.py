"""Tests for F2: `-n/--limit` threading + `--graph` precedence in `history log`.

Architect F2: `history log --files -n 5` used to silently return the FULL history
because `cmd_log_range` ignored `limit`; `--graph --files` silently dropped the
graph. Both must now be honoured.
"""
import os
import shutil
import tempfile
import types

from sgit_ai.cli.CLI__Diff                              import CLI__Diff
from sgit_ai.core.Vault__Sync                           import Vault__Sync
from sgit_ai.crypto.Vault__Crypto                       import Vault__Crypto
from sgit_ai.network.api.Vault__API__In_Memory          import Vault__API__In_Memory
from sgit_ai.plugins.history.CLI__History               import CLI__History


def _args(**kw):
    defaults = dict(directory='.', range_spec='', oneline=False, files=False,
                    patch=False, json_out=False, graph=False, limit=None,
                    file_path=None, vault_key=None)
    defaults.update(kw)
    return types.SimpleNamespace(**defaults)


class Test_CLI__History__Log__Limit_And_Graph:

    @classmethod
    def setup_class(cls):
        crypto = Vault__Crypto()
        api    = Vault__API__In_Memory(); api.setup()
        cls.sync = Vault__Sync(crypto=crypto, api=api)
        cls.tmp = tempfile.mkdtemp(prefix='log_limit_')
        cls.vault = os.path.join(cls.tmp, 'vault')
        cls.sync.init(cls.vault)

        def write(rel, content):
            with open(os.path.join(cls.vault, rel), 'w') as f:
                f.write(content)

        for letter in 'abcdef':                                # 6 explicit commits
            write(f'{letter}.txt', letter)
            cls.sync.commit(cls.vault, message=f'commit {letter}')

    @classmethod
    def teardown_class(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_limit_threads_through_files_mode(self, capsys):
        # Verbose mode (oneline=False) renders per-commit file lists.
        args = _args(directory=self.vault, files=True, limit=3, oneline=False)
        CLI__Diff().cmd_log_range(args)
        out = capsys.readouterr().out
        # last 3 commits (d, e, f) — earlier ones must NOT appear in the file list
        assert 'f.txt' in out and 'e.txt' in out and 'd.txt' in out
        assert 'a.txt' not in out and 'b.txt' not in out

    def test_limit_threads_through_json_mode(self, capsys):
        import json as _json
        args = _args(directory=self.vault, files=True, json_out=True, limit=2)
        CLI__Diff().cmd_log_range(args)
        parsed = _json.loads(capsys.readouterr().out.strip())
        assert int(parsed['commit_count']) == 2                # exactly the cap

    def test_limit_zero_or_none_returns_full_history(self, capsys):
        import json as _json
        args = _args(directory=self.vault, files=True, json_out=True, limit=None)
        CLI__Diff().cmd_log_range(args)
        parsed = _json.loads(capsys.readouterr().out.strip())
        assert int(parsed['commit_count']) >= 6                # init + a..f, no truncation

    def test_graph_beats_details_routing(self):
        # --graph --files: graph wins, goes to vault.cmd_log (which can render graphs)
        calls = []
        hist  = CLI__History(diff=CLI__Diff())
        hist.vault = type('V', (), {'cmd_log': lambda _s, a: calls.append('vault')})()
        hist._dispatch_log(_args(directory=self.vault, files=True, graph=True))
        assert calls == ['vault']
