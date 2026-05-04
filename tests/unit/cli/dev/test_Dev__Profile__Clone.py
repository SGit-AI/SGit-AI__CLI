"""Tests for Dev__Profile__Clone — sgit dev profile clone."""
import json
import os
import shutil
import tempfile

from sgit_ai.api.Vault__API__In_Memory          import Vault__API__In_Memory
from sgit_ai.cli.dev.Dev__Profile__Clone        import Dev__Profile__Clone
from sgit_ai.cli.dev.Schema__Profile__Clone     import Schema__Profile__Clone, Schema__Profile__Clone__Phase
from sgit_ai.crypto.Vault__Crypto               import Vault__Crypto
from sgit_ai.sync.Vault__Sync                   import Vault__Sync


def _make_env(files=None):
    """Return (vault_key, api, tmp_dir) with a seeded vault."""
    crypto = Vault__Crypto()
    api    = Vault__API__In_Memory()
    api.setup()
    sync   = Vault__Sync(crypto=crypto, api=api)

    snap_dir  = tempfile.mkdtemp()
    vault_dir = os.path.join(snap_dir, 'vault')
    result    = sync.init(vault_dir)
    vk        = result['vault_key']

    seed = files or {'hello.txt': 'world', 'docs/readme.md': '# hello'}
    for rel, content in seed.items():
        full   = os.path.join(vault_dir, rel)
        parent = os.path.dirname(full)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(full, 'w') as f:
            f.write(content)
    sync.commit(vault_dir, message='initial')
    sync.push(vault_dir)

    return vk, api, crypto, snap_dir


class Test_Dev__Profile__Clone__Schema:

    def test_schema_round_trip(self):
        phase = Schema__Profile__Clone__Phase(name='commits', duration_ms=42, count=3)
        out   = Schema__Profile__Clone(
            vault_id = 'abc123', directory = '/tmp/x', sparse = 0,
            total_ms = 500, n_commits = 3, n_trees = 7, n_blobs = 2,
            t_commits_ms = 10, t_trees_ms = 20, t_blobs_ms = 30,
            t_checkout_ms = 15, phases = [phase],
        )
        assert Schema__Profile__Clone.from_json(out.json()).json() == out.json()

    def test_schema_phase_fields(self):
        phase = Schema__Profile__Clone__Phase(name='trees', duration_ms=100, count=50)
        assert phase.name        == 'trees'
        assert phase.duration_ms == 100
        assert phase.count       == 50

    def test_schema_defaults(self):
        out = Schema__Profile__Clone()
        assert out.n_commits == 0
        assert out.total_ms  == 0
        assert out.phases    == []


class Test_Dev__Profile__Clone__Happy:

    _vk  = None
    _api = None
    _crypto = None
    _snap = None

    @classmethod
    def setup_class(cls):
        cls._vk, cls._api, cls._crypto, cls._snap = _make_env()

    @classmethod
    def teardown_class(cls):
        if cls._snap:
            shutil.rmtree(cls._snap, ignore_errors=True)

    def _make_tool(self):
        return Dev__Profile__Clone(crypto=self._crypto, api=self._api,
                                   sync=Vault__Sync(crypto=self._crypto, api=self._api))

    def test_profile_returns_schema(self):
        tool    = self._make_tool()
        tmp_dir = tempfile.mkdtemp()
        try:
            out = tool.profile(self._vk, tmp_dir)
            assert isinstance(out, Schema__Profile__Clone)
            assert out.vault_id  != ''
            assert str(out.directory) == tmp_dir
            assert out.total_ms  >= 0
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_profile_counts_commits_and_trees(self):
        tool    = self._make_tool()
        tmp_dir = tempfile.mkdtemp()
        try:
            out = tool.profile(self._vk, tmp_dir)
            assert out.n_commits >= 1
            assert out.n_trees   >= 1
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_profile_sparse_flag(self):
        tool    = self._make_tool()
        tmp_dir = tempfile.mkdtemp()
        try:
            out = tool.profile(self._vk, tmp_dir, sparse=True)
            assert out.sparse   == 1
            assert out.n_blobs  == 0   # sparse → no blobs downloaded
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_profile_full_clone_has_blobs(self):
        tool    = self._make_tool()
        tmp_dir = tempfile.mkdtemp()
        try:
            out = tool.profile(self._vk, tmp_dir, sparse=False)
            assert out.sparse  == 0
            assert out.n_blobs >= 1
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_profile_json_round_trip(self):
        tool    = self._make_tool()
        tmp_dir = tempfile.mkdtemp()
        try:
            out  = tool.profile(self._vk, tmp_dir)
            data = out.json()
            out2 = Schema__Profile__Clone.from_json(data)
            assert out2.json() == data
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)


class Test_Dev__Profile__Clone__CLI:

    _vk  = None
    _api = None
    _crypto = None
    _snap = None

    @classmethod
    def setup_class(cls):
        cls._vk, cls._api, cls._crypto, cls._snap = _make_env()

    @classmethod
    def teardown_class(cls):
        if cls._snap:
            shutil.rmtree(cls._snap, ignore_errors=True)

    def _make_tool(self):
        return Dev__Profile__Clone(crypto=self._crypto, api=self._api,
                                   sync=Vault__Sync(crypto=self._crypto, api=self._api))

    def test_cmd_json_output(self, capsys):
        tool    = self._make_tool()
        tmp_dir = tempfile.mkdtemp()
        try:
            class _Args:
                vault_key = self._vk
                directory = tmp_dir
                sparse    = False
                json      = True
                output    = None
            tool.cmd_profile_clone(_Args())
            captured = capsys.readouterr()
            data     = json.loads(captured.out)
            assert 'vault_id' in data
            assert 'total_ms' in data
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_cmd_text_output(self, capsys):
        tool    = self._make_tool()
        tmp_dir = tempfile.mkdtemp()
        try:
            class _Args:
                vault_key = self._vk
                directory = tmp_dir
                sparse    = False
                json      = False
                output    = None
            tool.cmd_profile_clone(_Args())
            captured = capsys.readouterr()
            assert 'Clone profile' in captured.out
            assert 'Total' in captured.out
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_cmd_json_to_file(self, tmp_path):
        tool     = self._make_tool()
        clone_dir = str(tmp_path / 'clone')
        out_file  = str(tmp_path / 'profile.json')
        os.makedirs(clone_dir, exist_ok=True)
        shutil.rmtree(clone_dir)   # profile needs empty dir

        class _Args:
            vault_key = self._vk
            directory = clone_dir
            sparse    = False
            json      = True
            output    = out_file

        tool.cmd_profile_clone(_Args())
        assert os.path.isfile(out_file)
        with open(out_file) as f:
            data = json.load(f)
        assert 'vault_id' in data

    def test_cmd_invalid_vault_key_raises(self):
        tool    = self._make_tool()
        tmp_dir = tempfile.mkdtemp()
        shutil.rmtree(tmp_dir)
        try:
            class _Args:
                vault_key = 'bad-passphrase:nonexistent'
                directory = tmp_dir
                sparse    = False
                json      = False
                output    = None
            raised = False
            try:
                tool.cmd_profile_clone(_Args())
            except Exception:
                raised = True
            assert raised, 'Expected exception for invalid vault key'
        finally:
            if os.path.isdir(tmp_dir):
                shutil.rmtree(tmp_dir, ignore_errors=True)
