"""Tests for Dev__Step__Clone — sgit dev step-clone."""
import json
import os
import shutil
import tempfile

from sgit_ai.network.api.Vault__API__In_Memory          import Vault__API__In_Memory
from sgit_ai.plugins.dev.Dev__Step__Clone           import Dev__Step__Clone
from sgit_ai.plugins.dev.Schema__Step__Clone        import Schema__Step__Clone, Schema__Step__Clone__Event
from sgit_ai.crypto.Vault__Crypto               import Vault__Crypto
from sgit_ai.core.Vault__Sync                   import Vault__Sync


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


class Test_Dev__Step__Clone__Schema:

    def test_schema_round_trip(self):
        ev  = Schema__Step__Clone__Event(index=0, event='step', label='Downloading', detail='', elapsed_ms=10)
        out = Schema__Step__Clone(vault_id='vid', directory='/tmp/x', commit_id='abc',
                                  total_ms=200, n_steps=1, events=[ev])
        assert Schema__Step__Clone.from_json(out.json()).json() == out.json()

    def test_schema_defaults(self):
        out = Schema__Step__Clone()
        assert out.total_ms == 0
        assert out.events   == []

    def test_event_fields(self):
        ev = Schema__Step__Clone__Event(index=2, event='scan_done', label='Walking trees',
                                        detail='5 trees', elapsed_ms=42)
        assert ev.index      == 2
        assert ev.elapsed_ms == 42
        assert str(ev.detail) == '5 trees'


class Test_Dev__Step__Clone__Happy:

    _vk = _api = _crypto = _snap = None

    @classmethod
    def setup_class(cls):
        cls._vk, cls._api, cls._crypto, cls._snap = _make_env()

    @classmethod
    def teardown_class(cls):
        if cls._snap:
            shutil.rmtree(cls._snap, ignore_errors=True)

    def _make_tool(self):
        return Dev__Step__Clone(crypto=self._crypto, api=self._api,
                                sync=Vault__Sync(crypto=self._crypto, api=self._api))

    def test_step_clone_returns_schema(self):
        tool = self._make_tool()
        tmp  = tempfile.mkdtemp()
        try:
            out = tool.step_clone(self._vk, tmp, no_pause=True)
            assert isinstance(out, Schema__Step__Clone)
            assert out.vault_id != ''
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_step_clone_records_events(self):
        tool = self._make_tool()
        tmp  = tempfile.mkdtemp()
        try:
            out = tool.step_clone(self._vk, tmp, no_pause=True)
            assert out.n_steps >= 1
            assert len(out.events) == out.n_steps
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_step_clone_events_have_elapsed(self):
        tool = self._make_tool()
        tmp  = tempfile.mkdtemp()
        try:
            out = tool.step_clone(self._vk, tmp, no_pause=True)
            for ev in out.events:
                assert ev.elapsed_ms >= 0
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_step_clone_on_pause_callback(self):
        """on_pause callback is called once per event in no-pause=False mode."""
        tool   = self._make_tool()
        tmp    = tempfile.mkdtemp()
        called = []
        try:
            out = tool.step_clone(self._vk, tmp, no_pause=False,
                                  on_pause=lambda ev: called.append(ev))
            assert len(called) == out.n_steps
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_step_clone_json_round_trip(self):
        tool = self._make_tool()
        tmp  = tempfile.mkdtemp()
        try:
            out  = tool.step_clone(self._vk, tmp, no_pause=True)
            data = out.json()
            out2 = Schema__Step__Clone.from_json(data)
            assert out2.json() == data
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class Test_Dev__Step__Clone__CLI:

    _vk = _api = _crypto = _snap = None

    @classmethod
    def setup_class(cls):
        cls._vk, cls._api, cls._crypto, cls._snap = _make_env()

    @classmethod
    def teardown_class(cls):
        if cls._snap:
            shutil.rmtree(cls._snap, ignore_errors=True)

    def _make_tool(self):
        return Dev__Step__Clone(crypto=self._crypto, api=self._api,
                                sync=Vault__Sync(crypto=self._crypto, api=self._api))

    def test_cmd_json_output(self, capsys):
        tool = self._make_tool()
        tmp  = tempfile.mkdtemp()
        shutil.rmtree(tmp)

        class _Args:
            vault_key = self._vk
            directory = tmp
            no_pause  = True
            json      = True
        tool.cmd_step_clone(_Args())
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert 'vault_id' in data
        assert 'events' in data

    def test_cmd_text_output(self, capsys):
        tool = self._make_tool()
        tmp  = tempfile.mkdtemp()
        shutil.rmtree(tmp)

        class _Args:
            vault_key = self._vk
            directory = tmp
            no_pause  = True
            json      = False
        tool.cmd_step_clone(_Args())
        captured = capsys.readouterr()
        assert 'Step-clone' in captured.out
        assert 'ms' in captured.out
