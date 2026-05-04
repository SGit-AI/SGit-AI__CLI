"""Tests for Dev__Server__Objects — sgit dev server-objects."""
import json
import os
import shutil
import tempfile

from sgit_ai.api.Vault__API__In_Memory          import Vault__API__In_Memory
from sgit_ai.cli.dev.Dev__Server__Objects       import Dev__Server__Objects, _classify
from sgit_ai.cli.dev.Schema__Server__Objects    import Schema__Server__Objects, Schema__Server__Objects__TypeCount
from sgit_ai.crypto.Vault__Crypto               import Vault__Crypto
from sgit_ai.sync.Vault__Sync                   import Vault__Sync


def _make_env():
    crypto = Vault__Crypto()
    api    = Vault__API__In_Memory()
    api.setup()
    sync   = Vault__Sync(crypto=crypto, api=api)

    snap  = tempfile.mkdtemp()
    vdir  = os.path.join(snap, 'vault')
    vk    = sync.init(vdir)['vault_key']

    for rel, content in [('a.txt', 'aaa'), ('sub/b.txt', 'bbb')]:
        full = os.path.join(vdir, rel)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, 'w') as f:
            f.write(content)
    sync.commit(vdir, 'c1')
    # second commit for history-only test
    with open(os.path.join(vdir, 'a.txt'), 'w') as f:
        f.write('changed')
    sync.commit(vdir, 'c2')
    sync.push(vdir)
    return vk, api, crypto, snap


class Test_Dev__Server__Objects__Schema:

    def test_schema_round_trip(self):
        t = Schema__Server__Objects__TypeCount(obj_type='data', count=10)
        out = Schema__Server__Objects(
            vault_id='vid', total_objects=12,
            by_type=[t], head_reachable=5, history_only=2, hot_tree_ids=['obj-cas-imm-aabb11223344'],
        )
        assert Schema__Server__Objects.from_json(out.json()).json() == out.json()

    def test_schema_defaults(self):
        out = Schema__Server__Objects()
        assert out.total_objects == 0
        assert out.by_type       == []

    def test_classify_helper(self):
        assert _classify('bare/data/obj-cas-imm-abc') == 'data'
        assert _classify('bare/refs/someid')          == 'ref'
        assert _classify('bare/indexes/idx')          == 'index'
        assert _classify('unknown/path')              == 'other'


class Test_Dev__Server__Objects__Happy:

    _vk = _api = _crypto = _snap = None

    @classmethod
    def setup_class(cls):
        cls._vk, cls._api, cls._crypto, cls._snap = _make_env()

    @classmethod
    def teardown_class(cls):
        if cls._snap:
            shutil.rmtree(cls._snap, ignore_errors=True)

    def _make_tool(self):
        return Dev__Server__Objects(crypto=self._crypto, api=self._api,
                                    sync=Vault__Sync(crypto=self._crypto, api=self._api))

    def test_analyse_returns_schema(self):
        out = self._make_tool().analyse(self._vk)
        assert isinstance(out, Schema__Server__Objects)
        assert out.vault_id != ''

    def test_analyse_total_objects_positive(self):
        out = self._make_tool().analyse(self._vk)
        assert out.total_objects >= 1

    def test_analyse_has_data_type(self):
        out = self._make_tool().analyse(self._vk)
        types = [str(t.obj_type) for t in out.by_type]
        assert 'data' in types

    def test_analyse_json_round_trip(self):
        out  = self._make_tool().analyse(self._vk)
        data = out.json()
        out2 = Schema__Server__Objects.from_json(data)
        assert out2.json() == data

    def test_analyse_head_reachable_leq_total(self):
        out = self._make_tool().analyse(self._vk)
        assert out.head_reachable <= out.total_objects


class Test_Dev__Server__Objects__CLI:

    _vk = _api = _crypto = _snap = None

    @classmethod
    def setup_class(cls):
        cls._vk, cls._api, cls._crypto, cls._snap = _make_env()

    @classmethod
    def teardown_class(cls):
        if cls._snap:
            shutil.rmtree(cls._snap, ignore_errors=True)

    def _make_tool(self):
        return Dev__Server__Objects(crypto=self._crypto, api=self._api,
                                    sync=Vault__Sync(crypto=self._crypto, api=self._api))

    def test_cmd_json_output(self, capsys):
        class _Args:
            vault_key = self._vk
            json      = True
            output    = None
        self._make_tool().cmd_server_objects(_Args())
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert 'vault_id' in data
        assert 'total_objects' in data

    def test_cmd_text_output(self, capsys):
        class _Args:
            vault_key = self._vk
            json      = False
            output    = None
        self._make_tool().cmd_server_objects(_Args())
        captured = capsys.readouterr()
        assert 'Server objects' in captured.out
        assert 'Total' in captured.out

    def test_cmd_json_to_file(self, tmp_path):
        out_file = str(tmp_path / 'objects.json')

        class _Args:
            vault_key = self._vk
            json      = True
            output    = out_file
        self._make_tool().cmd_server_objects(_Args())
        assert os.path.isfile(out_file)
        with open(out_file) as f:
            data = json.load(f)
        assert 'vault_id' in data
