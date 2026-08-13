"""Tests for `history diff <range>` — Brief 13."""
import os
import shutil
import types

import pytest

from sgit_ai.cli.CLI__Diff                              import CLI__Diff
from sgit_ai.crypto.Vault__Crypto                        import Vault__Crypto
from sgit_ai.schemas.history.Schema__History_Diff_Result import Schema__History_Diff_Result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_two_commit_vault():
    """Return (vault_dir, commit_a, commit_b) for a two-commit vault."""
    from sgit_ai.core.Vault__Sync                  import Vault__Sync
    from sgit_ai.network.api.Vault__API__In_Memory  import Vault__API__In_Memory
    import tempfile

    crypto = Vault__Crypto()
    api    = Vault__API__In_Memory()
    api.setup()
    sync   = Vault__Sync(crypto=crypto, api=api)
    tmp    = tempfile.mkdtemp()
    sync.init(tmp)

    with open(os.path.join(tmp, 'base.txt'), 'w') as f:
        f.write('base content')
    cid_a = sync.commit(tmp, message='base')['commit_id']

    with open(os.path.join(tmp, 'new.txt'), 'w') as f:
        f.write('new file')
    cid_b = sync.commit(tmp, message='add new.txt')['commit_id']

    return tmp, cid_a, cid_b


def _args(**kw):
    defaults = dict(directory='.', range_spec='', commit=None, commit2=None,
                    remote=False, files_only=False, json_out=False)
    defaults.update(kw)
    return types.SimpleNamespace(**defaults)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class Test_CLI__History__Diff__Range:

    def test_diff_accepts_range_syntax(self, capsys):
        """`history diff A..B` is equivalent to `--commit A --commit2 B`."""
        tmp, cid_a, cid_b = _make_two_commit_vault()
        try:
            cli  = CLI__Diff()
            args = _args(directory=tmp, range_spec=f'{cid_a}..{cid_b}')
            cli.cmd_diff(args)
            out = capsys.readouterr().out
            # new.txt should appear as added
            assert 'new.txt' in out
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_diff_json_round_trips(self, capsys):
        """`history diff A..B --json` round-trips through Schema__History_Diff_Result."""
        import json as _json
        tmp, cid_a, cid_b = _make_two_commit_vault()
        try:
            cli  = CLI__Diff()
            args = _args(directory=tmp, range_spec=f'{cid_a}..{cid_b}', json_out=True)
            cli.cmd_diff(args)
            raw = capsys.readouterr().out.strip()
            parsed = _json.loads(raw)
            result = Schema__History_Diff_Result.from_json(parsed)
            assert result.json() == parsed
            assert str(result.schema) == 'history_diff_v1'
            assert 'new.txt' in [str(s) for s in result.files_added]
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
