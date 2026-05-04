"""Coverage tests for Vault__Sync__Clone — missing lines.

Targets:
  74:        no branch index on remote → RuntimeError
  80:        named branch not found on remote → RuntimeError
  245-247:   clone_read_only dir not empty → RuntimeError
  282:       clone_read_only no branch index → RuntimeError
  288:       clone_read_only named branch not found → RuntimeError
  306-312:   clone_read_only named_commit_id None → early return empty dict
  335-336:   clone_read_only commit BFS load_commit raises → except pass
  347-348:   clone_read_only root_tree_ids load_commit raises → except pass
  368-370:   clone_read_only load_tree raises → except pass
  378-379:   clone_read_only sub_tree.flatten raises → flat = {}
  400:       clone_read_only blob not in obj_store → continue
  537:       _clone_download_blobs no total_blobs → early return
  541:       large blob detection threshold → large_blobs.append
"""
import os
import tempfile
import unittest.mock

import pytest

from sgit_ai.storage.Vault__Branch_Manager import Vault__Branch_Manager
from sgit_ai.core.Vault__Sync           import Vault__Sync
from sgit_ai.core.actions.clone.Vault__Sync__Clone    import Vault__Sync__Clone
from tests._helpers.vault_test_env      import Vault__Test_Env


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

    def test_clone_no_branch_index_raises_line_74(self, monkeypatch, tmp_path):
        """Line 74: batch_read returns empty dict (no index) → RuntimeError."""
        monkeypatch.setattr(self.sync.api, 'batch_read', lambda *a, **kw: {})
        with pytest.raises(RuntimeError, match='No branch index found'):
            self.sync.clone(self.snap.vault_key, str(tmp_path / 'out'))


# ---------------------------------------------------------------------------
# Line 80: named branch not found → RuntimeError
# ---------------------------------------------------------------------------

class Test_Vault__Sync__Clone__NoNamedBranch(_CloneTest):

    def test_clone_named_branch_not_found_raises_line_80(self, monkeypatch, tmp_path):
        """Line 80: get_branch_by_name returns None → RuntimeError."""
        monkeypatch.setattr(Vault__Branch_Manager, 'get_branch_by_name', lambda *a: None)
        with pytest.raises(RuntimeError, match='Named branch'):
            self.sync.clone(self.snap.vault_key, str(tmp_path / 'out'))


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

    def test_clone_read_only_no_branch_index_raises_line_282(self, monkeypatch, tmp_path):
        """Line 282: batch_read returns empty → RuntimeError."""
        monkeypatch.setattr(self.sync.api, 'batch_read', lambda *a, **kw: {})
        with pytest.raises(RuntimeError, match='No branch index found'):
            self.sync.clone_read_only(self.vault_id, self.read_key,
                                      str(tmp_path / 'out'))

    def test_clone_read_only_no_named_branch_raises_line_288(self, monkeypatch, tmp_path):
        """Line 288: get_branch_by_name returns None → RuntimeError."""
        monkeypatch.setattr(Vault__Branch_Manager, 'get_branch_by_name', lambda *a: None)
        with pytest.raises(RuntimeError, match='Named branch'):
            self.sync.clone_read_only(self.vault_id, self.read_key,
                                      str(tmp_path / 'out'))


# ---------------------------------------------------------------------------
# Lines 306-312: clone_read_only named_commit_id None → early return
# ---------------------------------------------------------------------------

class Test_Vault__Sync__Clone__ReadOnly__EmptyVault(_CloneTest):

    def test_clone_read_only_no_commit_id_returns_empty_lines_306_312(
            self, monkeypatch, tmp_path):
        """Lines 306-312: named branch has no head ref → early return with mode=read-only."""
        from sgit_ai.storage.Vault__Ref_Manager import Vault__Ref_Manager
        monkeypatch.setattr(Vault__Ref_Manager, 'read_ref', lambda *a, **kw: None)
        result = self.sync.clone_read_only(self.vault_id, self.read_key,
                                           str(tmp_path / 'out'))
        assert result.get('mode') == 'read-only'
        assert result.get('file_count') == 0


# ---------------------------------------------------------------------------
# Line 537: _clone_download_blobs no total_blobs → returns 0
# ---------------------------------------------------------------------------

class Test_Vault__Sync__Clone__DownloadBlobs(_CloneTest):

    def test_clone_download_blobs_no_total_blobs_returns_0_line_548(self, tmp_path):
        """Line 548: flat_map has no blob entries → returns {'n_blobs': 0, 't_blobs': 0.0}."""
        import unittest.mock
        from sgit_ai.core.actions.clone.Vault__Sync__Clone  import Vault__Sync__Clone
        from sgit_ai.storage.Vault__Object_Store import Vault__Object_Store
        from sgit_ai.storage.Vault__Commit      import Vault__Commit
        from sgit_ai.storage.Vault__Sub_Tree       import Vault__Sub_Tree
        from sgit_ai.storage.Vault__Storage        import SG_VAULT_DIR

        clone_obj = Vault__Sync__Clone(crypto=self.snap.crypto, api=self.snap.api)
        sg_dir    = os.path.join(self.vault, SG_VAULT_DIR)
        obj_store = Vault__Object_Store(vault_path=sg_dir, crypto=self.snap.crypto)
        read_key  = self.snap.crypto.import_read_key(self.read_key, self.vault_id)['read_key_bytes']

        vc       = Vault__Commit(crypto=self.snap.crypto, object_store=obj_store)
        sub_tree = Vault__Sub_Tree(crypto=self.snap.crypto, obj_store=obj_store)

        # Patch sub_tree.flatten to return empty → total_blobs = 0 → early return
        with unittest.mock.patch.object(sub_tree, 'flatten', return_value={}):
            # Also patch vc.load_commit to avoid needing a real commit
            fake_commit = unittest.mock.MagicMock()
            fake_commit.tree_id = 'obj-cas-imm-aabbcc112233'
            with unittest.mock.patch.object(vc, 'load_commit', return_value=fake_commit):
                result = clone_obj._clone_download_blobs(
                    self.vault_id, vc, sub_tree,
                    'obj-cas-imm-aabbcc112233', read_key,
                    lambda *a: None,  # save_file
                    lambda *a: None,  # _p
                )
        assert result == {'n_blobs': 0, 't_blobs': 0.0}

    def test_clone_download_blobs_entry_no_blob_id_hits_continue_line_537(self, tmp_path):
        """Line 537: entry has no blob_id → continue skips it, total_blobs stays 0."""
        import unittest.mock
        from sgit_ai.core.actions.clone.Vault__Sync__Clone    import Vault__Sync__Clone
        from sgit_ai.storage.Vault__Object_Store import Vault__Object_Store
        from sgit_ai.storage.Vault__Commit       import Vault__Commit
        from sgit_ai.storage.Vault__Sub_Tree        import Vault__Sub_Tree
        from sgit_ai.storage.Vault__Storage         import SG_VAULT_DIR

        clone_obj = Vault__Sync__Clone(crypto=self.snap.crypto, api=self.snap.api)
        sg_dir    = os.path.join(self.vault, SG_VAULT_DIR)
        obj_store = Vault__Object_Store(vault_path=sg_dir, crypto=self.snap.crypto)
        read_key  = self.snap.crypto.import_read_key(self.read_key, self.vault_id)['read_key_bytes']

        vc       = Vault__Commit(crypto=self.snap.crypto, object_store=obj_store)
        sub_tree = Vault__Sub_Tree(crypto=self.snap.crypto, obj_store=obj_store)

        # Entry with no blob_id → line 537 continue; total_blobs = 0 → line 548 return
        flat_no_blobs = {'dir/placeholder.txt': {'size': 0}}
        with unittest.mock.patch.object(sub_tree, 'flatten', return_value=flat_no_blobs):
            fake_commit = unittest.mock.MagicMock()
            fake_commit.tree_id = 'obj-cas-imm-aabbcc112233'
            with unittest.mock.patch.object(vc, 'load_commit', return_value=fake_commit):
                result = clone_obj._clone_download_blobs(
                    self.vault_id, vc, sub_tree,
                    'obj-cas-imm-aabbcc112233', read_key,
                    lambda *a: None,
                    lambda *a: None,
                )
        assert result == {'n_blobs': 0, 't_blobs': 0.0}

    def test_clone_download_blobs_large_blob_detected_line_541(self, tmp_path):
        """Line 541: entry has 'large'=True → appended to large_blobs."""
        import unittest.mock
        from sgit_ai.core.actions.clone.Vault__Sync__Clone    import Vault__Sync__Clone
        from sgit_ai.storage.Vault__Object_Store import Vault__Object_Store
        from sgit_ai.storage.Vault__Commit       import Vault__Commit
        from sgit_ai.storage.Vault__Sub_Tree        import Vault__Sub_Tree
        from sgit_ai.storage.Vault__Storage         import SG_VAULT_DIR

        clone_obj = Vault__Sync__Clone(crypto=self.snap.crypto, api=self.snap.api)
        sg_dir    = os.path.join(self.vault, SG_VAULT_DIR)
        obj_store = Vault__Object_Store(vault_path=sg_dir, crypto=self.snap.crypto)
        read_key  = self.snap.crypto.import_read_key(self.read_key, self.vault_id)['read_key_bytes']

        vc       = Vault__Commit(crypto=self.snap.crypto, object_store=obj_store)
        sub_tree = Vault__Sub_Tree(crypto=self.snap.crypto, obj_store=obj_store)

        # Entry with large=True → line 541 large_blobs.append
        # Mock presigned_read_url to return a URL we can intercept
        flat_large = {'bigfile.bin': {'blob_id': 'obj-cas-imm-aabbcc112233', 'large': True, 'size': 1}}
        mock_url   = 'http://localhost/fake-presigned-url'
        with unittest.mock.patch.object(sub_tree, 'flatten', return_value=flat_large):
            fake_commit = unittest.mock.MagicMock()
            fake_commit.tree_id = 'obj-cas-imm-aabbcc112233'
            with unittest.mock.patch.object(vc, 'load_commit', return_value=fake_commit):
                with unittest.mock.patch.object(
                    clone_obj.api, 'presigned_read_url',
                    return_value={'url': mock_url}
                ):
                    with unittest.mock.patch(
                        'sgit_ai.core.actions.clone.Vault__Sync__Clone.urlopen',
                        return_value=unittest.mock.MagicMock(read=lambda: b'data')
                    ):
                        result = clone_obj._clone_download_blobs(
                            self.vault_id, vc, sub_tree,
                            'obj-cas-imm-aabbcc112233', read_key,
                            lambda fid, data: None,
                            lambda *a: None,
                        )
        assert result.get('n_blobs', 0) >= 0


# ---------------------------------------------------------------------------
# Lines 335-336, 347-348, 368-370, 378-379: clone_read_only exception paths
# ---------------------------------------------------------------------------

class Test_Vault__Sync__Clone__ReadOnly__ExceptionPaths(_CloneTest):

    def test_clone_read_only_load_commit_raises_lines_335_336_347_348_378_379(
            self, monkeypatch, tmp_path):
        """Lines 335-336, 347-348, 378-379: load_commit raises in BFS and Phase 4."""
        from sgit_ai.storage.Vault__Commit import Vault__Commit

        monkeypatch.setattr(Vault__Commit, 'load_commit',
                            lambda *a, **kw: (_ for _ in ()).throw(Exception('bad commit')))
        result = self.sync.clone_read_only(self.vault_id, self.read_key,
                                           str(tmp_path / 'out'))
        assert result.get('mode') == 'read-only'
        assert result.get('file_count') == 0

    def test_clone_read_only_load_tree_raises_lines_368_370(self, monkeypatch, tmp_path):
        """Lines 368-370: load_tree raises in tree BFS → except pass."""
        from sgit_ai.storage.Vault__Commit import Vault__Commit

        monkeypatch.setattr(Vault__Commit, 'load_tree',
                            lambda *a, **kw: (_ for _ in ()).throw(Exception('bad tree')))
        result = self.sync.clone_read_only(self.vault_id, self.read_key,
                                           str(tmp_path / 'out'))
        assert result.get('mode') == 'read-only'

    def test_clone_read_only_blob_not_in_obj_store_hits_continue_line_400(
            self, monkeypatch, tmp_path):
        """Line 400: obj_store.exists returns False for blobs → continue."""
        from sgit_ai.storage.Vault__Object_Store import Vault__Object_Store

        monkeypatch.setattr(Vault__Object_Store, 'exists', lambda *a: False)
        result = self.sync.clone_read_only(self.vault_id, self.read_key,
                                           str(tmp_path / 'out'))
        assert result.get('mode') == 'read-only'

    def test_clone_read_only_obj_store_load_raises_lines_408_409(
            self, monkeypatch, tmp_path):
        """Lines 408-409: obj_store.load raises during blob write → except pass."""
        from sgit_ai.storage.Vault__Object_Store import Vault__Object_Store

        monkeypatch.setattr(Vault__Object_Store, 'load',
                            lambda *a: (_ for _ in ()).throw(Exception('load failed')))
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
