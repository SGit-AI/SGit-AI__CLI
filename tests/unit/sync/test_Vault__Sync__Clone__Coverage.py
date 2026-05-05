"""Coverage tests for Vault__Sync__Clone — missing lines.

Targets:
  74:        no branch index on remote → RuntimeError
  80:        named branch not found on remote → RuntimeError
  245-247:   clone_read_only dir not empty → RuntimeError
  282:       clone_read_only no branch index → RuntimeError
  288:       clone_read_only named branch not found → RuntimeError
  306-312:   clone_read_only named_commit_id None → early return empty dict
  537:       _clone_download_blobs no total_blobs → early return
  541:       large blob detection threshold → large_blobs.append
"""
import http.server
import json
import os
import threading

import pytest

from sgit_ai.core.actions.clone.Vault__Sync__Clone import Vault__Sync__Clone
from sgit_ai.network.api.Vault__API                import Vault__API
from sgit_ai.schemas.Schema__Branch_Index          import Schema__Branch_Index
from tests._helpers.vault_test_env                 import Vault__Test_Env


# ── fake helpers ─────────────────────────────────────────────────────────────

class _FakeApiEmptyBatch(Vault__API):
    """Returns {} for all batch_read calls — triggers 'No branch index found'."""
    def batch_read(self, vault_id: str, file_ids: list) -> dict:
        return {}


class _FakeApiNoBranches(Vault__API):
    """Returns encrypted empty branch index — triggers 'Named branch not found'."""
    _resp : dict = None

    def setup_responses(self, crypto, read_key_bytes, branch_index_file_id):
        index_fid  = f'bare/indexes/{branch_index_file_id}'
        empty_data = json.dumps(Schema__Branch_Index().json()).encode()
        encrypted  = crypto.encrypt(read_key_bytes, empty_data)
        self._resp = {index_fid: encrypted}
        return self

    def batch_read(self, vault_id: str, file_ids: list) -> dict:
        resp = self._resp or {}
        return {fid: resp[fid] for fid in file_ids if fid in resp}


class _FakeApiNoRefs(Vault__API):
    """Passes index calls to real API but blocks refs/keys → read_ref returns None."""
    _real_api : object = None

    def batch_read(self, vault_id: str, file_ids: list) -> dict:
        filtered = [fid for fid in file_ids
                    if not fid.startswith('bare/refs/') and not fid.startswith('bare/keys/')]
        return self._real_api.batch_read(vault_id, filtered) if filtered else {}


class _FakeApiPresigned(Vault__API):
    """Returns a presigned URL so _clone_download_blobs can fetch large blobs."""
    _presigned_url : object = None

    def batch_read(self, vault_id: str, file_ids: list) -> dict:
        return {}

    def presigned_read_url(self, vault_id: str, fid: str) -> dict:
        return {'url': self._presigned_url}


class _FakeCommit:
    tree_id = 'obj-cas-imm-aabbcc000001'


class _FakeVC:
    def load_commit(self, commit_id, read_key):
        return _FakeCommit()


class _FakeSubTree:
    def __init__(self, flat=None):
        self._flat = flat if flat is not None else {}

    def flatten(self, tree_id, read_key):
        return self._flat


class _BlobServer:
    """One-shot local HTTP server for large-blob presigned-URL tests."""
    def __init__(self, data=b'fake-blob-data'):
        self._data  = data
        self._srv   = None
        self.port   = None

    def start(self):
        data = self._data
        class _H(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.end_headers()
                self.wfile.write(data)
            def log_message(self, *a): pass
        self._srv  = http.server.HTTPServer(('127.0.0.1', 0), _H)
        self.port  = self._srv.server_address[1]
        threading.Thread(target=self._srv.handle_request, daemon=True).start()
        return self

    def url(self):
        return f'http://127.0.0.1:{self.port}/'

    def stop(self):
        if self._srv:
            self._srv.server_close()


class _CloneTest:
    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_single_vault(files={'a.txt': 'hello'})

    @classmethod
    def teardown_class(cls):
        if cls._env:
            cls._env.cleanup_snapshot()

    def setup_method(self):
        self.snap  = self._env.restore()
        self.vault = self.snap.vault_dir
        self.sync  = self.snap.sync
        keys       = self.snap.crypto.derive_keys_from_vault_key(self.snap.vault_key)
        self.vault_id  = keys['vault_id']
        self.read_key  = keys['read_key']

    def teardown_method(self):
        self.snap.cleanup()


# ---------------------------------------------------------------------------
# Line 74: no branch index on remote → RuntimeError
# ---------------------------------------------------------------------------

class Test_Vault__Sync__Clone__NoBranchIndex(_CloneTest):

    def test_clone_no_branch_index_raises_line_74(self, tmp_path):
        """batch_read returns {} (no index) → RuntimeError via Step__Clone__Download_Index."""
        clone = Vault__Sync__Clone(crypto=self.snap.crypto, api=_FakeApiEmptyBatch())
        with pytest.raises(RuntimeError, match='No branch index found'):
            clone.clone(self.snap.vault_key, str(tmp_path / 'out'))


# ---------------------------------------------------------------------------
# Line 80: named branch not found → RuntimeError
# ---------------------------------------------------------------------------

class Test_Vault__Sync__Clone__NoNamedBranch(_CloneTest):

    def test_clone_named_branch_not_found_raises_line_80(self, tmp_path):
        """Encrypted empty branch index → get_branch_by_name returns None → RuntimeError."""
        keys     = self.snap.crypto.derive_keys_from_vault_key(self.snap.vault_key)
        fake_api = _FakeApiNoBranches().setup_responses(
            self.snap.crypto, keys['read_key_bytes'], keys['branch_index_file_id'])
        clone = Vault__Sync__Clone(crypto=self.snap.crypto, api=fake_api)
        with pytest.raises(RuntimeError, match='Named branch'):
            clone.clone(self.snap.vault_key, str(tmp_path / 'out'))


# ---------------------------------------------------------------------------
# Lines 245-247: clone_read_only non-empty dir → RuntimeError
# ---------------------------------------------------------------------------

class Test_Vault__Sync__Clone__ReadOnly__NonEmpty(_CloneTest):

    def test_clone_read_only_nonempty_dir_raises_lines_245_247(self, tmp_path):
        """Lines 245-247: directory exists and is non-empty → RuntimeError."""
        non_empty = tmp_path / 'nonempty'
        non_empty.mkdir()
        (non_empty / 'existing.txt').write_text('already here')
        with pytest.raises(RuntimeError, match='not empty'):
            self.sync.clone_read_only(self.vault_id, self.read_key, str(non_empty))


# ---------------------------------------------------------------------------
# Lines 282, 288: clone_read_only guard checks
# ---------------------------------------------------------------------------

class Test_Vault__Sync__Clone__ReadOnly__Guards(_CloneTest):

    def test_clone_read_only_no_branch_index_raises_line_282(self, tmp_path):
        """batch_read returns {} → RuntimeError via Step__Clone__Download_Index."""
        clone = Vault__Sync__Clone(crypto=self.snap.crypto, api=_FakeApiEmptyBatch())
        with pytest.raises(RuntimeError, match='No branch index found'):
            clone.clone_read_only(self.vault_id, self.read_key, str(tmp_path / 'out'))

    def test_clone_read_only_no_named_branch_raises_line_288(self, tmp_path):
        """Encrypted empty index → get_branch_by_name returns None → RuntimeError."""
        keys     = self.snap.crypto.import_read_key(self.read_key, self.vault_id)
        fake_api = _FakeApiNoBranches().setup_responses(
            self.snap.crypto, keys['read_key_bytes'], keys['branch_index_file_id'])
        clone = Vault__Sync__Clone(crypto=self.snap.crypto, api=fake_api)
        with pytest.raises(RuntimeError, match='Named branch'):
            clone.clone_read_only(self.vault_id, self.read_key, str(tmp_path / 'out'))


# ---------------------------------------------------------------------------
# Lines 306-312: clone_read_only named_commit_id None → early return
# ---------------------------------------------------------------------------

class Test_Vault__Sync__Clone__ReadOnly__EmptyVault(_CloneTest):

    def test_clone_read_only_no_commit_id_returns_empty_lines_306_312(self, tmp_path):
        """Refs skipped from download → read_ref returns None → named_commit_id='' → 0 blobs."""
        no_refs_api           = _FakeApiNoRefs()
        no_refs_api._real_api = self.snap.api
        clone                 = Vault__Sync__Clone(crypto=self.snap.crypto, api=no_refs_api)
        result = clone.clone_read_only(self.vault_id, self.read_key, str(tmp_path / 'out'))
        assert result.get('mode') == 'read-only'
        assert result.get('file_count') == 0


# ---------------------------------------------------------------------------
# Line 537: _clone_download_blobs no total_blobs → returns 0
# ---------------------------------------------------------------------------

class Test_Vault__Sync__Clone__DownloadBlobs(_CloneTest):

    def test_clone_download_blobs_no_total_blobs_returns_0_line_548(self, tmp_path):
        """flat_map has no blob entries → total_blobs=0 → early return."""
        read_key  = self.snap.crypto.import_read_key(self.read_key, self.vault_id)['read_key_bytes']
        clone_obj = Vault__Sync__Clone(crypto=self.snap.crypto, api=self.snap.api)
        result    = clone_obj._clone_download_blobs(
            self.vault_id, _FakeVC(), _FakeSubTree(),
            'obj-cas-imm-aabbcc112233', read_key,
            lambda *a: None, lambda *a: None,
        )
        assert result == {'n_blobs': 0, 't_blobs': 0.0}

    def test_clone_download_blobs_entry_no_blob_id_hits_continue_line_537(self, tmp_path):
        """Entry with no blob_id → continue skip → total_blobs=0 → early return."""
        read_key  = self.snap.crypto.import_read_key(self.read_key, self.vault_id)['read_key_bytes']
        clone_obj = Vault__Sync__Clone(crypto=self.snap.crypto, api=self.snap.api)
        flat      = {'dir/placeholder.txt': {'size': 0}}
        result    = clone_obj._clone_download_blobs(
            self.vault_id, _FakeVC(), _FakeSubTree(flat),
            'obj-cas-imm-aabbcc112233', read_key,
            lambda *a: None, lambda *a: None,
        )
        assert result == {'n_blobs': 0, 't_blobs': 0.0}

    def test_clone_download_blobs_large_blob_detected_line_541(self, tmp_path):
        """Entry with large=True → appended to large_blobs → fetched via presigned URL."""
        read_key   = self.snap.crypto.import_read_key(self.read_key, self.vault_id)['read_key_bytes']
        server                    = _BlobServer(b'fake-encrypted-blob').start()
        fake_api                  = _FakeApiPresigned()
        fake_api._presigned_url   = server.url()
        clone_obj                 = Vault__Sync__Clone(crypto=self.snap.crypto, api=fake_api)
        flat_large = {'bigfile.bin': {'blob_id': 'obj-cas-imm-aabbcc112233', 'large': True, 'size': 1}}
        result     = clone_obj._clone_download_blobs(
            self.vault_id, _FakeVC(), _FakeSubTree(flat_large),
            'obj-cas-imm-aabbcc112233', read_key,
            lambda fid, data: None, lambda *a: None,
        )
        server.stop()
        assert result.get('n_blobs', 0) >= 1


# ---------------------------------------------------------------------------
# Lines 335-336, 347-348, 368-370, 378-379: clone_read_only exception paths
# ---------------------------------------------------------------------------

class Test_Vault__Sync__Clone__ReadOnly__ExceptionPaths(_CloneTest):
    # The old exception-path tests (load_commit raises, load_tree raises, obj_store.load raises)
    # used monkeypatch and tested defensive try/except blocks in the old ~180-LOC
    # clone_read_only implementation.  That implementation was replaced by
    # Workflow__Clone__ReadOnly (B03), so those tests are no longer meaningful.
    # They are removed here; the workflow's step-level resilience is tested in
    # tests/unit/workflow/clone/test_Workflow__Clone__ReadOnly.py.

    def test_clone_read_only_returns_mode(self, tmp_path):
        """clone_read_only always returns mode='read-only' on success."""
        result = self.sync.clone_read_only(self.vault_id, self.read_key,
                                           str(tmp_path / 'out'))
        assert result.get('mode') == 'read-only'


# ---------------------------------------------------------------------------
# Line 368: nested sub-tree entry in clone_read_only tree BFS
# Line 361: duplicate tree_id in tree_queue (two commits share same tree)
# ---------------------------------------------------------------------------

class _CloneTestNested:
    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_single_vault(files={
            'root.txt': 'root content',
            'subdir/nested.txt': 'nested content',
        })

    @classmethod
    def teardown_class(cls):
        if cls._env:
            cls._env.cleanup_snapshot()

    def setup_method(self):
        self.snap = self._env.restore()
        self.vault = self.snap.vault_dir
        self.sync  = self.snap.sync
        keys           = self.snap.crypto.derive_keys_from_vault_key(self.snap.vault_key)
        self.vault_id  = keys['vault_id']
        self.read_key  = keys['read_key']

    def teardown_method(self):
        self.snap.cleanup()


class Test_Vault__Sync__Clone__ReadOnly__SubTree(_CloneTestNested):

    def test_clone_read_only_sub_tree_entry_hits_line_368(self, tmp_path):
        """Line 368: tree entry has tree_id (sub-dir) → next_trees.append hit."""
        result = self.snap.sync.clone_read_only(
            self.vault_id, self.read_key, str(tmp_path / 'out'))
        assert result.get('mode') == 'read-only'
        assert result.get('file_count', 0) >= 1

    def test_clone_read_only_duplicate_tree_hits_continue_line_361(self, tmp_path):
        """Line 361: two commits share same tree → tree_queue duplicate → continue."""
        with open(os.path.join(self.vault, 'temp_361.txt'), 'w') as f:
            f.write('temp for line 361')
        self.sync.commit(self.vault, 'add temp')
        os.remove(os.path.join(self.vault, 'temp_361.txt'))
        self.sync.commit(self.vault, 'remove temp → same tree as initial')
        self.sync.push(self.vault)

        result = self.snap.sync.clone_read_only(
            self.vault_id, self.read_key, str(tmp_path / 'out2'))
        assert result.get('mode') == 'read-only'
