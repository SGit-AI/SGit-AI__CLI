"""Tests for Dev__Tree__Graph — sgit dev tree-graph."""
import json
import os
import shutil
import tempfile

from sgit_ai.network.api.Vault__API__In_Memory      import Vault__API__In_Memory
from sgit_ai.cli.dev.Dev__Tree__Graph       import Dev__Tree__Graph
from sgit_ai.cli.dev.Schema__Tree__Graph    import Schema__Tree__Graph, Schema__Tree__Graph__Commit
from sgit_ai.crypto.Vault__Crypto           import Vault__Crypto
from sgit_ai.core.Vault__Sync               import Vault__Sync


def _make_env_multi_commit(files_v1=None, files_v2=None):
    """Return (vault_key, api, crypto) with two commits for dedup testing."""
    crypto = Vault__Crypto()
    api    = Vault__API__In_Memory()
    api.setup()
    sync   = Vault__Sync(crypto=crypto, api=api)

    snap_dir  = tempfile.mkdtemp()
    vault_dir = os.path.join(snap_dir, 'vault')
    result    = sync.init(vault_dir)
    vk        = result['vault_key']

    v1 = files_v1 or {'hello.txt': 'world', 'docs/readme.md': '# hello'}
    for rel, content in v1.items():
        full = os.path.join(vault_dir, rel)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, 'w') as f:
            f.write(content)
    sync.commit(vault_dir, message='commit 1')

    v2 = files_v2 or {'hello.txt': 'changed', 'new.txt': 'new'}
    for rel, content in v2.items():
        full = os.path.join(vault_dir, rel)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, 'w') as f:
            f.write(content)
    sync.commit(vault_dir, message='commit 2')
    sync.push(vault_dir)

    return vk, api, crypto, snap_dir


class Test_Dev__Tree__Graph__Schema:

    def test_schema_round_trip(self):
        commit = Schema__Tree__Graph__Commit(
            commit_id='abc', root_tree_id='xyz',
            total_trees=5, unique_new=3, dedup_ratio='1.7x',
        )
        out = Schema__Tree__Graph(
            vault_id='vid', n_commits=2, total_trees=10,
            unique_trees=6, head_only_trees=3,
            commits=[commit], depth_histogram=[],
        )
        assert Schema__Tree__Graph.from_json(out.json()).json() == out.json()

    def test_schema_defaults(self):
        out = Schema__Tree__Graph()
        assert out.n_commits    == 0
        assert out.unique_trees == 0
        assert out.commits      == []

    def test_commit_schema_fields(self):
        c = Schema__Tree__Graph__Commit(
            commit_id='cid', root_tree_id='tid',
            total_trees=3, unique_new=2, dedup_ratio='1.5x',
        )
        assert c.commit_id   == 'cid'
        assert c.total_trees == 3
        assert str(c.dedup_ratio) == '1.5x'


class Test_Dev__Tree__Graph__Happy:

    _vk = _api = _crypto = _snap = None

    @classmethod
    def setup_class(cls):
        cls._vk, cls._api, cls._crypto, cls._snap = _make_env_multi_commit()

    @classmethod
    def teardown_class(cls):
        if cls._snap:
            shutil.rmtree(cls._snap, ignore_errors=True)

    def _make_tool(self):
        return Dev__Tree__Graph(crypto=self._crypto, api=self._api,
                                sync=Vault__Sync(crypto=self._crypto, api=self._api))

    def test_analyse_returns_schema(self):
        out = self._make_tool().analyse(self._vk)
        assert isinstance(out, Schema__Tree__Graph)
        assert out.vault_id != ''

    def test_analyse_counts_commits(self):
        out = self._make_tool().analyse(self._vk)
        assert out.n_commits >= 2

    def test_analyse_unique_trees_positive(self):
        out = self._make_tool().analyse(self._vk)
        assert out.unique_trees >= 1

    def test_analyse_head_only_trees_leq_total(self):
        out = self._make_tool().analyse(self._vk)
        assert out.head_only_trees <= out.unique_trees

    def test_analyse_json_round_trip(self):
        out  = self._make_tool().analyse(self._vk)
        data = out.json()
        out2 = Schema__Tree__Graph.from_json(data)
        assert out2.json() == data

    def test_analyse_temp_dir_cleaned_up(self):
        """No temp dirs leak after analyse()."""
        import glob
        before = set(glob.glob('/tmp/tmp*'))
        self._make_tool().analyse(self._vk)
        after = set(glob.glob('/tmp/tmp*'))
        leaked = after - before
        # any new dirs should be gone (analyse cleans up)
        # allow for dirs created by other concurrent tests
        for d in leaked:
            assert not os.path.isdir(os.path.join(d, '.sg_vault')), \
                f'Leaked temp vault dir: {d}'

    def test_analyse_depth_histogram_has_entries(self):
        out = self._make_tool().analyse(self._vk)
        # vault with subdirs must have depth > 0 entries
        assert len(out.depth_histogram) >= 1


class Test_Dev__Tree__Graph__CLI:

    _vk = _api = _crypto = _snap = None

    @classmethod
    def setup_class(cls):
        cls._vk, cls._api, cls._crypto, cls._snap = _make_env_multi_commit()

    @classmethod
    def teardown_class(cls):
        if cls._snap:
            shutil.rmtree(cls._snap, ignore_errors=True)

    def _make_tool(self):
        return Dev__Tree__Graph(crypto=self._crypto, api=self._api,
                                sync=Vault__Sync(crypto=self._crypto, api=self._api))

    def test_cmd_json_output(self, capsys):
        class _Args:
            vault_key = self._vk
            json      = True
            output    = None
            dot       = None
        self._make_tool().cmd_tree_graph(_Args())
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert 'vault_id' in data
        assert 'n_commits' in data

    def test_cmd_text_output(self, capsys):
        class _Args:
            vault_key = self._vk
            json      = False
            output    = None
            dot       = None
        self._make_tool().cmd_tree_graph(_Args())
        captured = capsys.readouterr()
        assert 'Tree DAG' in captured.out
        assert 'Commits' in captured.out

    def test_cmd_dot_output(self, tmp_path):
        dot_file = str(tmp_path / 'tree.dot')

        class _Args:
            vault_key = self._vk
            json      = False
            output    = None
            dot       = dot_file
        self._make_tool().cmd_tree_graph(_Args())
        assert os.path.isfile(dot_file)
        content = open(dot_file).read()
        assert 'digraph' in content
