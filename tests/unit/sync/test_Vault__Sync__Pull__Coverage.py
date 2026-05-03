"""Coverage tests for Vault__Sync__Pull — missing lines.

Targets easy/medium paths:
  52:        no branch index in reset() → RuntimeError
  56:        branch not found in reset() → RuntimeError
  61-63:     reset() no commit_id and no current → RuntimeError
  69-70:     reset() FileNotFoundError → RuntimeError
  121:       no branch index in pull() → RuntimeError
  126:       clone branch not found in pull() → RuntimeError
  130:       named branch not found in pull() → RuntimeError
  158-162:   named_commit_id None → up_to_date + remote_unreachable flag
  184-186:   _find_missing_blobs returns non-empty → RuntimeError
  201-203:   lca==named + remote unreachable → up_to_date
  285-286:   signing key load exception silenced
  319-320:   _find_missing_blobs exception → empty list
  361-362:   _batch_save batch_read exception silenced
  379:       commit_wave unvisited empty → break
  434:       duplicate tree_id in tree_wave → continue
  507-508:   blob download exception silenced
"""
import os
import unittest.mock

import pytest

from sgit_ai.objects.Vault__Ref_Manager  import Vault__Ref_Manager
from sgit_ai.sync.Vault__Branch_Manager  import Vault__Branch_Manager
from sgit_ai.sync.Vault__Sync            import Vault__Sync
from sgit_ai.sync.Vault__Sync__Base      import Vault__Sync__Base
from sgit_ai.sync.Vault__Sync__Pull      import Vault__Sync__Pull
from tests._helpers.vault_test_env       import Vault__Test_Env


class _PullTest:
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

    def teardown_method(self):
        self.snap.cleanup()


# ---------------------------------------------------------------------------
# Lines 52, 56: reset() guard checks
# ---------------------------------------------------------------------------

class Test_Vault__Sync__Pull__Reset_Guards(_PullTest):

    def test_reset_no_branch_index_raises_line_52(self, monkeypatch):
        """Line 52: no branch_index_file_id → RuntimeError."""
        import types
        orig = Vault__Sync__Base._init_components

        def patched(self_, d):
            c = orig(self_, d)
            ns = vars(c).copy()
            ns['branch_index_file_id'] = ''
            return types.SimpleNamespace(**ns)

        monkeypatch.setattr(Vault__Sync__Base, '_init_components', patched)
        with pytest.raises(RuntimeError, match='No branch index found'):
            self.sync.reset(self.vault)

    def test_reset_branch_not_found_raises_line_56(self, monkeypatch):
        """Line 56: get_branch_by_id returns None → RuntimeError('Branch not found')."""
        monkeypatch.setattr(Vault__Branch_Manager, 'get_branch_by_id', lambda *a: None)
        with pytest.raises(RuntimeError, match='Branch not found'):
            self.sync.reset(self.vault)


# ---------------------------------------------------------------------------
# Lines 61-63: reset() no commit_id and no current commit
# ---------------------------------------------------------------------------

class Test_Vault__Sync__Pull__Reset_NoCommit(_PullTest):

    def test_reset_no_commits_yet_raises_lines_61_63(self, monkeypatch):
        """Lines 61-63: commit_id=None and current_commit_id is None → RuntimeError."""
        monkeypatch.setattr(Vault__Ref_Manager, 'read_ref', lambda *a, **kw: None)
        with pytest.raises(RuntimeError, match='No commits yet'):
            self.sync.reset(self.vault, commit_id=None)

    def test_reset_uses_current_commit_when_no_explicit_id_line_63(self):
        """Line 63: commit_id=None, current_commit_id exists → assigned on line 63."""
        result = self.sync.reset(self.vault, commit_id=None)
        assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# Lines 69-70: reset() commit not found locally
# ---------------------------------------------------------------------------

class Test_Vault__Sync__Pull__Reset_CommitNotFound(_PullTest):

    def test_reset_commit_not_found_raises_lines_69_70(self):
        """Lines 69-70: load_commit raises FileNotFoundError → RuntimeError."""
        with pytest.raises(RuntimeError, match='Commit not found locally'):
            self.sync.reset(self.vault, commit_id='obj-cas-imm-000000000000')


# ---------------------------------------------------------------------------
# Lines 121, 126, 130: pull() guard checks
# ---------------------------------------------------------------------------

class Test_Vault__Sync__Pull__Pull_Guards(_PullTest):

    def test_pull_no_branch_index_raises_line_121(self, monkeypatch):
        """Line 121: no branch_index_file_id → RuntimeError."""
        import types
        orig = Vault__Sync__Base._init_components

        def patched(self_, d):
            c = orig(self_, d)
            ns = vars(c).copy()
            ns['branch_index_file_id'] = ''
            return types.SimpleNamespace(**ns)

        monkeypatch.setattr(Vault__Sync__Base, '_init_components', patched)
        with pytest.raises(RuntimeError, match='No branch index found'):
            self.sync.pull(self.vault)

    def test_pull_clone_branch_not_found_raises_line_126(self, monkeypatch):
        """Line 126: get_branch_by_id returns None → RuntimeError."""
        monkeypatch.setattr(Vault__Branch_Manager, 'get_branch_by_id', lambda *a: None)
        with pytest.raises(RuntimeError, match='Clone branch not found'):
            self.sync.pull(self.vault)

    def test_pull_named_branch_not_found_raises_line_130(self, monkeypatch):
        """Line 130: get_branch_by_name returns None → RuntimeError."""
        monkeypatch.setattr(Vault__Branch_Manager, 'get_branch_by_name', lambda *a: None)
        with pytest.raises(RuntimeError, match='Named branch'):
            self.sync.pull(self.vault)


# ---------------------------------------------------------------------------
# Lines 158-162: named_commit_id is None → up_to_date + remote unreachable
# ---------------------------------------------------------------------------

class Test_Vault__Sync__Pull__NamedHeadNone(_PullTest):

    def test_pull_named_commit_none_with_failed_remote_lines_158_162(self, monkeypatch):
        """Lines 158-162: named_head=None + API raises → remote_unreachable=True."""
        orig_read = Vault__Ref_Manager.read_ref
        call_count = [0]

        def patched_read_ref(self_, ref_id, read_key=None):
            call_count[0] += 1
            if call_count[0] == 1:
                return orig_read(self_, ref_id, read_key)   # clone branch ref
            return None                                      # named branch ref → None

        monkeypatch.setattr(Vault__Ref_Manager, 'read_ref', patched_read_ref)
        monkeypatch.setattr(self.sync.api, 'read',
                            lambda *a, **kw: (_ for _ in ()).throw(RuntimeError('network error')))

        result = self.sync.pull(self.vault)
        assert result['status'] == 'up_to_date'
        assert result.get('remote_unreachable') is True


# ---------------------------------------------------------------------------
# Lines 285-286: signing key exception silenced
# ---------------------------------------------------------------------------

class Test_Vault__Sync__Pull__SigningKey(_PullTest):

    def test_pull_signing_key_exception_silenced_lines_285_286(self, monkeypatch):
        """Lines 285-286: load_private_key_locally raises → continues without signing key."""
        from sgit_ai.crypto.Vault__Key_Manager import Vault__Key_Manager
        called_and_raised = []

        def raising(self_, *a, **kw):
            called_and_raised.append(True)
            raise Exception('no key file')

        # Trigger merge path by using two clones setup
        env2  = Vault__Test_Env()
        env2.setup_two_clones(files={'x.txt': 'original'})
        snap2 = env2.restore()
        try:
            sync  = snap2.sync  # single shared sync object with shared api+crypto
            # Push a new commit on Alice's side
            with open(os.path.join(snap2.alice_dir, 'new.txt'), 'w') as f:
                f.write('new content')
            sync.commit(snap2.alice_dir, 'add new')
            sync.push(snap2.alice_dir)

            # Add a local commit on Bob's side to force merge
            with open(os.path.join(snap2.bob_dir, 'bob.txt'), 'w') as f:
                f.write('bob content')
            sync.commit(snap2.bob_dir, 'bob change')

            monkeypatch.setattr(Vault__Key_Manager, 'load_private_key_locally', raising)
            result = sync.pull(snap2.bob_dir)
            assert result['status'] in ('merged', 'fast_forward', 'up_to_date')
            assert len(called_and_raised) > 0
        finally:
            snap2.cleanup()
            env2.cleanup_snapshot()


# ---------------------------------------------------------------------------
# Lines 319-320: _find_missing_blobs exception → []
# ---------------------------------------------------------------------------

class Test_Vault__Sync__Pull__FindMissingBlobs(_PullTest):

    def test_find_missing_blobs_exception_returns_empty_lines_319_320(self):
        """Lines 319-320: load_commit raises → returns []."""
        pull_obj = Vault__Sync__Pull(crypto=self.snap.crypto, api=self.snap.api)
        result   = pull_obj._find_missing_blobs('nonexistent-commit', None, b'')
        assert result == []

    def test_find_missing_blobs_with_bad_obj_store_returns_empty(self):
        """Lines 319-320: obj_store.exists raises → returns []."""
        from sgit_ai.objects.Vault__Object_Store import Vault__Object_Store
        from sgit_ai.sync.Vault__Storage         import SG_VAULT_DIR
        sg_dir    = os.path.join(self.vault, SG_VAULT_DIR)
        obj_store = Vault__Object_Store(vault_path=sg_dir, crypto=self.snap.crypto)
        pull_obj  = Vault__Sync__Pull(crypto=self.snap.crypto, api=self.snap.api)
        result    = pull_obj._find_missing_blobs('obj-cas-imm-badcommit01', obj_store, b'')
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# Lines 201-203: lca==named + remote unreachable → up_to_date with flags
# ---------------------------------------------------------------------------

class Test_Vault__Sync__Pull__LcaEqualsNamed(_PullTest):

    def test_pull_lca_equals_named_remote_unreachable_lines_201_203(self, monkeypatch):
        """Lines 201-203: local is ahead + remote unreachable → up_to_date + remote_unreachable."""
        # Create a new local commit so clone is ahead of named
        with open(os.path.join(self.vault, 'ahead.txt'), 'w') as f:
            f.write('local only content')
        self.sync.commit(self.vault, 'local commit ahead of remote')

        # Mock api.read to fail → remote_fetch_ok = False
        # Local named ref is still the pre-push commit; LCA = named_commit_id
        monkeypatch.setattr(self.sync.api, 'read',
                            lambda *a, **kw: (_ for _ in ()).throw(RuntimeError('network')))
        result = self.sync.pull(self.vault)
        assert result['status'] == 'up_to_date'
        assert result.get('remote_unreachable') is True


# ---------------------------------------------------------------------------
# Lines 391, 437, 457: _fetch_missing_objects — commit/tree not downloaded
# ---------------------------------------------------------------------------

class Test_Vault__Sync__Pull__FetchMissingObjects(_PullTest):

    def test_fetch_missing_objects_commit_not_saved_hits_continue_line_391(self):
        """Line 391: batch_save returns nothing → commit not in obj_store → continue."""
        import shutil, tempfile
        from sgit_ai.sync.Vault__Sync__Pull  import Vault__Sync__Pull
        from sgit_ai.objects.Vault__Object_Store import Vault__Object_Store
        from sgit_ai.sync.Vault__Storage     import SG_VAULT_DIR

        keys     = self.snap.crypto.derive_keys_from_vault_key(self.snap.vault_key)
        vault_id = keys['vault_id']
        read_key = self.snap.crypto.import_read_key(keys['read_key'], vault_id)['read_key_bytes']

        fresh_sg  = tempfile.mkdtemp()
        try:
            obj_store = Vault__Object_Store(vault_path=fresh_sg, crypto=self.snap.crypto)
            pull_obj  = Vault__Sync__Pull(crypto=self.snap.crypto, api=self.snap.api)

            # Mock batch_read to return {} → commit never saved → line 391
            with unittest.mock.patch.object(pull_obj.api, 'batch_read', return_value={}):
                result = pull_obj._fetch_missing_objects(
                    vault_id, 'obj-cas-imm-aabbcc112233',
                    obj_store, read_key, fresh_sg, include_blobs=True)
            assert isinstance(result, dict)
        finally:
            shutil.rmtree(fresh_sg, ignore_errors=True)

    def test_fetch_missing_objects_load_commit_raises_lines_412_413(self):
        """Lines 412-413: commit in obj_store but load_commit raises → except pass."""
        from sgit_ai.sync.Vault__Sync__Pull  import Vault__Sync__Pull
        from sgit_ai.objects.Vault__Object_Store import Vault__Object_Store
        from sgit_ai.objects.Vault__Commit    import Vault__Commit
        from sgit_ai.sync.Vault__Storage     import SG_VAULT_DIR

        keys     = self.snap.crypto.derive_keys_from_vault_key(self.snap.vault_key)
        vault_id = keys['vault_id']
        read_key = self.snap.crypto.import_read_key(keys['read_key'], vault_id)['read_key_bytes']
        commit_id = self.snap.commit_id
        if not commit_id:
            return

        sg_dir    = os.path.join(self.vault, SG_VAULT_DIR)
        obj_store = Vault__Object_Store(vault_path=sg_dir, crypto=self.snap.crypto)
        pull_obj  = Vault__Sync__Pull(crypto=self.snap.crypto, api=self.snap.api)

        # Commit IS in obj_store (real vault); load_commit raises → lines 412-413
        with unittest.mock.patch.object(Vault__Commit, 'load_commit',
                                        side_effect=Exception('bad commit data')):
            result = pull_obj._fetch_missing_objects(
                vault_id, commit_id, obj_store, read_key, sg_dir, include_blobs=True)
        assert isinstance(result, dict)

    def test_fetch_missing_objects_load_tree_raises_lines_444_445_466_467(self):
        """Lines 444-445, 466-467: tree in obj_store but load_tree raises → except pass."""
        from sgit_ai.sync.Vault__Sync__Pull  import Vault__Sync__Pull
        from sgit_ai.objects.Vault__Object_Store import Vault__Object_Store
        from sgit_ai.objects.Vault__Commit    import Vault__Commit
        from sgit_ai.sync.Vault__Storage     import SG_VAULT_DIR

        keys     = self.snap.crypto.derive_keys_from_vault_key(self.snap.vault_key)
        vault_id = keys['vault_id']
        read_key = self.snap.crypto.import_read_key(keys['read_key'], vault_id)['read_key_bytes']
        commit_id = self.snap.commit_id
        if not commit_id:
            return

        sg_dir    = os.path.join(self.vault, SG_VAULT_DIR)
        obj_store = Vault__Object_Store(vault_path=sg_dir, crypto=self.snap.crypto)
        pull_obj  = Vault__Sync__Pull(crypto=self.snap.crypto, api=self.snap.api)

        # Tree IS in obj_store; load_tree raises → lines 444-445 (Phase 2) + 466-467 (Phase 3)
        with unittest.mock.patch.object(Vault__Commit, 'load_tree',
                                        side_effect=Exception('bad tree data')):
            result = pull_obj._fetch_missing_objects(
                vault_id, commit_id, obj_store, read_key, sg_dir, include_blobs=True)
        assert isinstance(result, dict)

    def test_fetch_missing_objects_decrypt_metadata_raises_lines_478_479(self):
        """Lines 478-479: commit_infos has enc_msg; decrypt_metadata raises → except pass."""
        import shutil, tempfile
        from sgit_ai.sync.Vault__Sync__Pull  import Vault__Sync__Pull
        from sgit_ai.objects.Vault__Object_Store import Vault__Object_Store
        from sgit_ai.sync.Vault__Storage     import SG_VAULT_DIR
        from sgit_ai.crypto.Vault__Crypto    import Vault__Crypto

        keys     = self.snap.crypto.derive_keys_from_vault_key(self.snap.vault_key)
        vault_id = keys['vault_id']
        read_key = self.snap.crypto.import_read_key(keys['read_key'], vault_id)['read_key_bytes']
        commit_id = self.snap.commit_id
        if not commit_id:
            return

        fresh_sg  = tempfile.mkdtemp()
        try:
            obj_store = Vault__Object_Store(vault_path=fresh_sg, crypto=self.snap.crypto)
            pull_obj  = Vault__Sync__Pull(crypto=self.snap.crypto, api=self.snap.api)

            # Use real batch_read (downloads commit), then patch decrypt_metadata to raise
            # Commit is NOT in obj_store → gets downloaded → commit_infos populated → decrypt_metadata called
            with unittest.mock.patch.object(Vault__Crypto, 'decrypt_metadata',
                                            side_effect=Exception('decrypt fail')):
                result = pull_obj._fetch_missing_objects(
                    vault_id, commit_id, obj_store, read_key, fresh_sg, include_blobs=True)
            assert isinstance(result, dict)
        finally:
            shutil.rmtree(fresh_sg, ignore_errors=True)

    def test_fetch_missing_objects_duplicate_tree_id_hits_continue_line_434(self):
        """Line 434: two commits share same tree_id → duplicate in tree_wave → continue.

        Uses a fresh empty obj_store so the BFS processes ALL commits one by one
        (each iteration fetches the next missing commit via batch_read). When two
        commits share the same tree T, root_tree_ids = [T, T2, T] → tree_wave has
        duplicate T → second T hits `if tid in seen_trees: continue` at line 434.
        """
        import tempfile
        from sgit_ai.sync.Vault__Sync__Pull      import Vault__Sync__Pull
        from sgit_ai.objects.Vault__Object_Store  import Vault__Object_Store
        from sgit_ai.sync.Vault__Storage          import SG_VAULT_DIR

        keys     = self.snap.crypto.derive_keys_from_vault_key(self.snap.vault_key)
        vault_id = keys['vault_id']
        read_key = self.snap.crypto.import_read_key(keys['read_key'], vault_id)['read_key_bytes']

        with open(os.path.join(self.vault, 'temp_line434.txt'), 'w') as f:
            f.write('temporary file for line 434 test')
        self.sync.commit(self.vault, 'add temp')
        os.remove(os.path.join(self.vault, 'temp_line434.txt'))
        commit3 = self.sync.commit(self.vault, 'remove temp → tree same as initial')
        commit3_id = commit3['commit_id']

        sg_dir = os.path.join(self.vault, SG_VAULT_DIR)

        def fake_batch_read(vid, fids):
            out = {}
            for fid in fids:
                local = os.path.join(sg_dir, fid.replace('/', os.sep))
                if os.path.isfile(local):
                    with open(local, 'rb') as fp:
                        out[fid] = fp.read()
            return out

        with tempfile.TemporaryDirectory() as tmp_store:
            fresh_os = Vault__Object_Store(vault_path=tmp_store, crypto=self.snap.crypto)
            pull_obj = Vault__Sync__Pull(crypto=self.snap.crypto, api=self.snap.api)

            with unittest.mock.patch.object(self.snap.api, 'batch_read',
                                            side_effect=fake_batch_read):
                result = pull_obj._fetch_missing_objects(
                    vault_id, commit3_id, fresh_os, read_key, tmp_store,
                    include_blobs=False)

        assert isinstance(result, dict)

    def test_fetch_missing_objects_tree_not_saved_hits_lines_437_457(self):
        """Lines 437, 457: commit fetched but tree not saved → continue in Phase 2 and 3."""
        import shutil, tempfile
        from sgit_ai.sync.Vault__Sync__Pull  import Vault__Sync__Pull
        from sgit_ai.objects.Vault__Object_Store import Vault__Object_Store
        from sgit_ai.sync.Vault__Storage     import SG_VAULT_DIR

        keys     = self.snap.crypto.derive_keys_from_vault_key(self.snap.vault_key)
        vault_id = keys['vault_id']
        read_key = self.snap.crypto.import_read_key(keys['read_key'], vault_id)['read_key_bytes']
        commit_id = self.snap.commit_id
        if not commit_id:
            return  # skip if no commit in snapshot

        fresh_sg  = tempfile.mkdtemp()
        try:
            obj_store = Vault__Object_Store(vault_path=fresh_sg, crypto=self.snap.crypto)
            pull_obj  = Vault__Sync__Pull(crypto=self.snap.crypto, api=self.snap.api)

            orig_batch_read = self.snap.api.batch_read
            call_count      = [0]

            def batch_first_only(vid, fids):
                call_count[0] += 1
                if call_count[0] == 1:
                    return orig_batch_read(vid, fids)  # return commit data
                return {}  # subsequent calls (trees, blobs) return nothing

            with unittest.mock.patch.object(pull_obj.api, 'batch_read', batch_first_only):
                result = pull_obj._fetch_missing_objects(
                    vault_id, commit_id,
                    obj_store, read_key, fresh_sg, include_blobs=True)
            assert isinstance(result, dict)
        finally:
            shutil.rmtree(fresh_sg, ignore_errors=True)


# ---------------------------------------------------------------------------
# Line 379: stop_at == start commit → unvisited empty → break
# ---------------------------------------------------------------------------

class Test_Vault__Sync__Pull__FetchStopAt(_PullTest):

    def test_fetch_missing_objects_stop_at_equals_start_hits_break_line_379(self):
        """Line 379: stop_at == commit_id → visited_commits has start → unvisited=[] → break."""
        import tempfile
        from sgit_ai.sync.Vault__Sync__Pull      import Vault__Sync__Pull
        from sgit_ai.objects.Vault__Object_Store  import Vault__Object_Store
        from sgit_ai.sync.Vault__Storage          import SG_VAULT_DIR

        keys      = self.snap.crypto.derive_keys_from_vault_key(self.snap.vault_key)
        vault_id  = keys['vault_id']
        read_key  = self.snap.crypto.import_read_key(keys['read_key'], vault_id)['read_key_bytes']
        commit_id = self.snap.commit_id
        sg_dir    = os.path.join(self.vault, SG_VAULT_DIR)
        obj_store = Vault__Object_Store(vault_path=sg_dir, crypto=self.snap.crypto)
        pull_obj  = Vault__Sync__Pull(crypto=self.snap.crypto, api=self.snap.api)

        result = pull_obj._fetch_missing_objects(
            vault_id, commit_id, obj_store, read_key, sg_dir,
            stop_at=commit_id)
        assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# Lines 361-362: _batch_save batch_read raises → exception silenced
# ---------------------------------------------------------------------------

class Test_Vault__Sync__Pull__BatchSaveException(_PullTest):

    def test_fetch_missing_objects_batch_read_raises_lines_361_362(self):
        """Lines 361-362: batch_read raises in _batch_save → silenced → result returned."""
        import tempfile
        from sgit_ai.sync.Vault__Sync__Pull      import Vault__Sync__Pull
        from sgit_ai.objects.Vault__Object_Store  import Vault__Object_Store
        from sgit_ai.sync.Vault__Storage          import SG_VAULT_DIR

        keys      = self.snap.crypto.derive_keys_from_vault_key(self.snap.vault_key)
        vault_id  = keys['vault_id']
        read_key  = self.snap.crypto.import_read_key(keys['read_key'], vault_id)['read_key_bytes']
        commit_id = self.snap.commit_id

        with tempfile.TemporaryDirectory() as tmp:
            fresh_os = Vault__Object_Store(vault_path=tmp, crypto=self.snap.crypto)
            pull_obj = Vault__Sync__Pull(crypto=self.snap.crypto, api=self.snap.api)

            with unittest.mock.patch.object(self.snap.api, 'batch_read',
                                            side_effect=RuntimeError('network failure')):
                result = pull_obj._fetch_missing_objects(
                    vault_id, commit_id, fresh_os, read_key, tmp)
        assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# Lines 507-508: blob download api.read raises → exception silenced
# ---------------------------------------------------------------------------

class Test_Vault__Sync__Pull__BlobDownloadException(_PullTest):

    def test_fetch_missing_objects_blob_download_exception_silenced_lines_507_508(self):
        """Lines 507-508: api.read raises during blob download → exception silenced."""
        import tempfile
        from sgit_ai.sync.Vault__Sync__Pull      import Vault__Sync__Pull
        from sgit_ai.objects.Vault__Object_Store  import Vault__Object_Store
        from sgit_ai.sync.Vault__Storage          import SG_VAULT_DIR

        keys      = self.snap.crypto.derive_keys_from_vault_key(self.snap.vault_key)
        vault_id  = keys['vault_id']
        read_key  = self.snap.crypto.import_read_key(keys['read_key'], vault_id)['read_key_bytes']
        commit_id = self.snap.commit_id
        sg_dir    = os.path.join(self.vault, SG_VAULT_DIR)

        def fake_batch_read(vid, fids):
            out = {}
            for fid in fids:
                local = os.path.join(sg_dir, fid.replace('/', os.sep))
                if os.path.isfile(local):
                    with open(local, 'rb') as fp:
                        out[fid] = fp.read()
            return out

        with tempfile.TemporaryDirectory() as tmp:
            fresh_os = Vault__Object_Store(vault_path=tmp, crypto=self.snap.crypto)
            pull_obj = Vault__Sync__Pull(crypto=self.snap.crypto, api=self.snap.api)

            with unittest.mock.patch.object(self.snap.api, 'batch_read', fake_batch_read):
                with unittest.mock.patch.object(self.snap.api, 'read',
                                                side_effect=Exception('network error')):
                    result = pull_obj._fetch_missing_objects(
                        vault_id, commit_id, fresh_os, read_key, tmp,
                        include_blobs=True)
        assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# Lines 184-186: pull() _find_missing_blobs returns non-empty → RuntimeError
# ---------------------------------------------------------------------------

class _PullTestTwoClones:
    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_two_clones(files={'a.txt': 'hello'})

    @classmethod
    def teardown_class(cls):
        if cls._env:
            cls._env.cleanup_snapshot()

    def setup_method(self):
        self.snap = self._env.restore()

    def teardown_method(self):
        self.snap.cleanup()


# ---------------------------------------------------------------------------
# Lines 501-502: large blob presigned URL download in _fetch_missing_objects
# ---------------------------------------------------------------------------

class Test_Vault__Sync__Pull__LargeBlobPresigned(_PullTest):

    def test_fetch_missing_objects_large_blob_presigned_url_lines_501_502(self):
        """Lines 501-502: is_large=True → presigned_read_url + urlopen called."""
        import tempfile
        from sgit_ai.sync.Vault__Sync__Pull      import Vault__Sync__Pull
        from sgit_ai.objects.Vault__Object_Store  import Vault__Object_Store
        from sgit_ai.objects.Vault__Commit        import Vault__Commit
        from sgit_ai.sync.Vault__Storage          import SG_VAULT_DIR

        keys      = self.snap.crypto.derive_keys_from_vault_key(self.snap.vault_key)
        vault_id  = keys['vault_id']
        read_key  = self.snap.crypto.import_read_key(keys['read_key'], vault_id)['read_key_bytes']
        commit_id = self.snap.commit_id
        sg_dir    = os.path.join(self.vault, SG_VAULT_DIR)

        def fake_batch_read(vid, fids):
            out = {}
            for fid in fids:
                local = os.path.join(sg_dir, fid.replace('/', os.sep))
                if os.path.isfile(local):
                    with open(local, 'rb') as fp:
                        out[fid] = fp.read()
            return out

        from sgit_ai.schemas.Schema__Object_Tree_Entry import Schema__Object_Tree_Entry
        from sgit_ai.safe_types.Safe_Str__Object_Id   import Safe_Str__Object_Id

        fake_blob_id   = 'obj-cas-imm-aabbcc112233'
        orig_load_tree = Vault__Commit.load_tree

        def fake_load_tree(self_, tree_id, read_key_):
            real_tree  = orig_load_tree(self_, tree_id, read_key_)
            fake_entry = Schema__Object_Tree_Entry()
            fake_entry.blob_id = Safe_Str__Object_Id(fake_blob_id)
            fake_entry.large   = True
            real_tree.entries.append(fake_entry)
            return real_tree

        with tempfile.TemporaryDirectory() as tmp:
            fresh_os = Vault__Object_Store(vault_path=tmp, crypto=self.snap.crypto)
            pull_obj = Vault__Sync__Pull(crypto=self.snap.crypto, api=self.snap.api)

            with unittest.mock.patch.object(self.snap.api, 'batch_read', fake_batch_read):
                with unittest.mock.patch.object(
                    Vault__Commit, 'load_tree', fake_load_tree
                ):
                    with unittest.mock.patch.object(
                        self.snap.api, 'presigned_read_url',
                        return_value={'url': 'http://localhost/fake-url'}
                    ):
                        with unittest.mock.patch(
                            'sgit_ai.sync.Vault__Sync__Pull.urlopen',
                            return_value=unittest.mock.MagicMock(read=lambda: b'blob-data')
                        ):
                            result = pull_obj._fetch_missing_objects(
                                vault_id, commit_id, fresh_os, read_key, tmp,
                                include_blobs=True)
        assert isinstance(result, dict)


class Test_Vault__Sync__Pull__MissingBlobsRaised(_PullTestTwoClones):

    def test_pull_missing_blobs_raises_runtime_error_lines_184_186(self, monkeypatch):
        """Lines 184-186: _find_missing_blobs returns non-empty list → RuntimeError."""
        alice = self.snap.alice_dir
        bob   = self.snap.bob_dir
        sync  = self.snap.sync

        with open(os.path.join(alice, 'new.txt'), 'w') as f:
            f.write('new content from alice')
        sync.commit(alice, 'alice adds new file')
        sync.push(alice)

        monkeypatch.setattr(Vault__Sync__Pull, '_find_missing_blobs',
                            lambda *a: ['fake-missing-blob-001'])
        with pytest.raises(RuntimeError, match='Pull incomplete'):
            sync.pull(bob)
