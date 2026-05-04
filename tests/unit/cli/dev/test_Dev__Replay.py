"""Tests for Dev__Replay — sgit dev replay."""
import json
import os
import shutil
import tempfile

from sgit_ai.api.Vault__API__In_Memory          import Vault__API__In_Memory
from sgit_ai.cli.dev.Dev__Profile__Clone        import Dev__Profile__Clone
from sgit_ai.cli.dev.Dev__Replay                import Dev__Replay
from sgit_ai.cli.dev.Schema__Replay             import Schema__Replay, Schema__Replay__Phase__Diff
from sgit_ai.crypto.Vault__Crypto               import Vault__Crypto
from sgit_ai.sync.Vault__Sync                   import Vault__Sync


def _write_trace(tmp_dir, vk, api, crypto) -> str:
    """Run profile clone and save --json output; return path to trace file."""
    sync   = Vault__Sync(crypto=crypto, api=api)
    profiler = Dev__Profile__Clone(crypto=crypto, api=api, sync=sync)
    clone_dir = os.path.join(tmp_dir, 'clone')
    os.makedirs(clone_dir, exist_ok=True)
    shutil.rmtree(clone_dir)
    out  = profiler.profile(vk, clone_dir)
    path = os.path.join(tmp_dir, 'trace.json')
    with open(path, 'w') as f:
        json.dump(out.json(), f)
    return path


def _make_env():
    crypto = Vault__Crypto()
    api    = Vault__API__In_Memory()
    api.setup()
    sync   = Vault__Sync(crypto=crypto, api=api)

    snap = tempfile.mkdtemp()
    vdir = os.path.join(snap, 'vault')
    vk   = sync.init(vdir)['vault_key']
    with open(os.path.join(vdir, 'f.txt'), 'w') as f:
        f.write('hello')
    sync.commit(vdir, 'c1')
    sync.push(vdir)
    return vk, api, crypto, snap


class Test_Dev__Replay__Schema:

    def test_schema_round_trip(self):
        diff = Schema__Replay__Phase__Diff(phase='trees', a_ms=100, b_ms=80,
                                           delta_ms='-20 ms', pct_change='-20%')
        out  = Schema__Replay(trace_file='/tmp/t.json', vault_id='vid',
                              n_commits=3, n_trees=10, n_blobs=5,
                              total_ms=500, t_commits_ms=10, t_trees_ms=200,
                              t_blobs_ms=50, t_checkout_ms=20, diff_phases=[diff])
        assert Schema__Replay.from_json(out.json()).json() == out.json()

    def test_schema_defaults(self):
        out = Schema__Replay()
        assert out.total_ms    == 0
        assert out.diff_phases == []

    def test_phase_diff_fields(self):
        d = Schema__Replay__Phase__Diff(phase='blobs', a_ms=50, b_ms=30,
                                        delta_ms='-20 ms', pct_change='-40%')
        assert d.a_ms == 50
        assert d.b_ms == 30
        assert str(d.delta_ms)   == '-20 ms'
        assert str(d.pct_change) == '-40%'


class Test_Dev__Replay__Happy:

    _vk = _api = _crypto = _snap = _trace = None

    @classmethod
    def setup_class(cls):
        cls._vk, cls._api, cls._crypto, cls._snap = _make_env()
        cls._trace = _write_trace(cls._snap, cls._vk, cls._api, cls._crypto)

    @classmethod
    def teardown_class(cls):
        if cls._snap:
            shutil.rmtree(cls._snap, ignore_errors=True)

    def test_replay_returns_schema(self):
        out = Dev__Replay().replay(self._trace)
        assert isinstance(out, Schema__Replay)
        assert out.vault_id != ''

    def test_replay_timing_fields(self):
        out = Dev__Replay().replay(self._trace)
        assert out.total_ms >= 0
        assert out.n_commits >= 1

    def test_replay_json_round_trip(self):
        out  = Dev__Replay().replay(self._trace)
        data = out.json()
        out2 = Schema__Replay.from_json(data)
        assert out2.json() == data

    def test_replay_diff_same_trace(self):
        """Diff of a trace against itself → all deltas are 0."""
        out = Dev__Replay().replay_diff(self._trace, self._trace)
        for d in out.diff_phases:
            assert d.a_ms == d.b_ms

    def test_replay_diff_has_four_phases(self):
        out = Dev__Replay().replay_diff(self._trace, self._trace)
        names = [str(d.phase) for d in out.diff_phases]
        assert 'commits'  in names
        assert 'trees'    in names
        assert 'blobs'    in names
        assert 'checkout' in names


class Test_Dev__Replay__CLI:

    _vk = _api = _crypto = _snap = _trace = None

    @classmethod
    def setup_class(cls):
        cls._vk, cls._api, cls._crypto, cls._snap = _make_env()
        cls._trace = _write_trace(cls._snap, cls._vk, cls._api, cls._crypto)

    @classmethod
    def teardown_class(cls):
        if cls._snap:
            shutil.rmtree(cls._snap, ignore_errors=True)

    def test_cmd_json_output(self, capsys):
        class _Args:
            trace = self._trace
            diff  = None
            json  = True
        Dev__Replay().cmd_replay(_Args())
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert 'vault_id' in data
        assert 'total_ms' in data

    def test_cmd_text_output(self, capsys):
        class _Args:
            trace = self._trace
            diff  = None
            json  = False
        Dev__Replay().cmd_replay(_Args())
        captured = capsys.readouterr()
        assert 'Replay' in captured.out
        assert 'Total' in captured.out

    def test_cmd_diff_text_output(self, capsys):
        class _Args:
            trace = self._trace
            diff  = self._trace   # diff against itself
            json  = False
        Dev__Replay().cmd_replay(_Args())
        captured = capsys.readouterr()
        assert 'Phase diff' in captured.out
        assert 'trees' in captured.out

    def test_cmd_missing_trace_raises(self):
        class _Args:
            trace = '/nonexistent/trace.json'
            diff  = None
            json  = False
        raised = False
        try:
            Dev__Replay().cmd_replay(_Args())
        except (FileNotFoundError, Exception):
            raised = True
        assert raised
