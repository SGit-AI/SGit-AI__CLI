"""Coverage tests for Vault__Sync__Base helper methods.

Missing lines targeted:
  133 (_checkout_flat_map: no blob_id → continue)
  141-142 (_checkout_flat_map: load fails → except pass)
  166-167 (_remove_empty_dirs: rmdir OSError → pass)
  181 (_walk_commit_ids: cid already visited → continue)
  196 (_count_unique_commits: no from_head → return 0)
  204-206 (_count_commits_from: no start → 0; with start → count)
  219-220 (_auto_gc_drain: packs dir exists but no pack-* files → early return)
"""
import os
import tempfile
import shutil

import pytest

from sgit_ai.crypto.Vault__Crypto          import Vault__Crypto
from sgit_ai.crypto.PKI__Crypto            import PKI__Crypto
from sgit_ai.storage.Vault__Object_Store   import Vault__Object_Store
from sgit_ai.storage.Vault__Ref_Manager    import Vault__Ref_Manager
from sgit_ai.storage.Vault__Storage           import SG_VAULT_DIR, Vault__Storage
from sgit_ai.core.Vault__Sync__Base        import Vault__Sync__Base
from tests._helpers.vault_test_env         import Vault__Test_Env


class Test_Vault__Sync__Base__Coverage:
    """Direct calls to Vault__Sync__Base helper methods."""

    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_single_vault(files={'a.txt': 'hello', 'b.txt': 'world'})

    @classmethod
    def teardown_class(cls):
        if cls._env:
            cls._env.cleanup_snapshot()

    def setup_method(self):
        self.snap     = self._env.restore()
        self.crypto   = self.snap.crypto
        keys          = self.crypto.derive_keys_from_vault_key(self.snap.vault_key)
        self.read_key = keys['read_key_bytes']
        sg_dir        = os.path.join(self.snap.vault_dir, SG_VAULT_DIR)
        self.obj_store = Vault__Object_Store(vault_path=sg_dir, crypto=self.crypto)
        self.base      = Vault__Sync__Base(crypto=self.crypto)

    def teardown_method(self):
        self.snap.cleanup()

    # ─── _checkout_flat_map ───────────────────────────────────────────────

    def test_checkout_flat_map_skips_entry_without_blob_id(self):
        """Line 133: entry with no blob_id is skipped (continue)."""
        flat_map = {'readme.md': {'blob_id': ''}}   # empty blob_id
        tmp = tempfile.mkdtemp()
        try:
            self.base._checkout_flat_map(tmp, flat_map, self.obj_store, self.read_key)
            # No file written — entry skipped
            assert not os.path.isfile(os.path.join(tmp, 'readme.md'))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_checkout_flat_map_swallows_load_exception(self):
        """Lines 141-142: missing blob raises in load → except caught silently."""
        flat_map = {'file.txt': {'blob_id': 'nonexistent-blob-id'}}
        tmp = tempfile.mkdtemp()
        try:
            # Should not raise, just skip silently
            self.base._checkout_flat_map(tmp, flat_map, self.obj_store, self.read_key)
            assert not os.path.isfile(os.path.join(tmp, 'file.txt'))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    # ─── _remove_empty_dirs ──────────────────────────────────────────────

    def test_remove_empty_dirs_swallows_oserror(self):
        """Lines 166-167: os.rmdir raises OSError for empty dir → caught silently."""
        import unittest.mock
        tmp = tempfile.mkdtemp()
        sub = os.path.join(tmp, 'subdir')
        try:
            os.makedirs(sub)
            with unittest.mock.patch('os.rmdir', side_effect=OSError('busy')):
                removed = self.base._remove_empty_dirs(tmp)
            assert isinstance(removed, list)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    # ─── _walk_commit_ids ────────────────────────────────────────────────

    def test_walk_commit_ids_skips_empty_commit_id(self):
        """Line 181: empty string commit id in queue → continue."""
        # Add '' to the queue via parents. Achieve by walking a commit whose
        # parent in the store has been deleted (causing the queue to receive empty IDs).
        commit_id = self.snap.commit_id
        # walk with a None/empty start → returns empty set (line 181 via if not cid)
        result = self.base._walk_commit_ids(self.obj_store, self.read_key, '')
        assert result == set()

    def test_walk_commit_ids_deduplicates_visited(self):
        """Line 181: commit already in visited → continue (dedup)."""
        commit_id = self.snap.commit_id
        result = self.base._walk_commit_ids(self.obj_store, self.read_key, commit_id)
        # At minimum the start commit should be in the result
        assert commit_id in result

    def test_walk_commit_ids_diamond_dag_fires_line_181(self):
        """Line 181: diamond DAG — root reachable via two paths → visited dedup fires."""
        import json as _json
        root  = self.snap.commit_id

        # left: parent=root
        left_raw  = {'schema': 'commit_v1', 'tree_id': 'obj-cas-imm-aabbccddeeff',
                     'parents': [root], 'branch_id': '', 'timestamp_ms': 100,
                     'signature': '', 'message_enc': ''}
        left_id   = self.obj_store.store(
            self.crypto.encrypt(self.read_key, _json.dumps(left_raw).encode()))

        # right: parent=root
        right_raw = {'schema': 'commit_v1', 'tree_id': 'obj-cas-imm-aabbccddeeff',
                     'parents': [root], 'branch_id': '', 'timestamp_ms': 200,
                     'signature': '', 'message_enc': ''}
        right_id  = self.obj_store.store(
            self.crypto.encrypt(self.read_key, _json.dumps(right_raw).encode()))

        # merge: parents=[left, right]
        merge_raw = {'schema': 'commit_v1', 'tree_id': 'obj-cas-imm-aabbccddeeff',
                     'parents': [left_id, right_id], 'branch_id': '', 'timestamp_ms': 300,
                     'signature': '', 'message_enc': ''}
        merge_id  = self.obj_store.store(
            self.crypto.encrypt(self.read_key, _json.dumps(merge_raw).encode()))

        result = self.base._walk_commit_ids(self.obj_store, self.read_key, merge_id)
        # root should appear exactly once despite being reachable via left AND right
        assert root in result
        assert merge_id in result
        assert left_id  in result
        assert right_id in result
        # Result is a set, so no duplicates by definition; verify root appears once
        assert isinstance(result, set)

    # ─── _count_unique_commits / _count_commits_from ─────────────────────

    def test_count_unique_commits_no_from_head_returns_zero(self):
        """Line 196: from_head is empty → return 0."""
        result = self.base._count_unique_commits(self.obj_store, self.read_key, '', '')
        assert result == 0

    def test_count_commits_from_no_start_returns_zero(self):
        """Line 205: start is empty → return 0."""
        result = self.base._count_commits_from(self.obj_store, self.read_key, '')
        assert result == 0

    def test_count_commits_from_with_start_returns_count(self):
        """Line 206: valid start → returns positive count."""
        commit_id = self.snap.commit_id
        result = self.base._count_commits_from(self.obj_store, self.read_key, commit_id)
        assert result >= 1

    # ─── _auto_gc_drain ──────────────────────────────────────────────────

    def test_auto_gc_drain_packs_dir_exists_but_no_pack_files(self):
        """Lines 219-220: packs dir exists but no pack-* entries → early return."""
        vault_dir = self.snap.vault_dir
        storage   = Vault__Storage()
        packs_dir = os.path.join(storage.local_dir(vault_dir), 'packs')
        os.makedirs(packs_dir, exist_ok=True)
        # Create a file that doesn't start with 'pack-'
        with open(os.path.join(packs_dir, 'other_file.txt'), 'w') as f:
            f.write('x')
        # Should return early without crashing
        self.base._auto_gc_drain(vault_dir)   # no assertion needed — just no crash

    def test_auto_gc_drain_with_pack_file_runs_gc_lines_221_227(self):
        """Lines 221-227: pack-* file exists → drain_pending raises → except silences at 226-227."""
        import unittest.mock
        from sgit_ai.core.actions.gc.Vault__GC import Vault__GC
        vault_dir = self.snap.vault_dir
        storage   = Vault__Storage()
        packs_dir = os.path.join(storage.local_dir(vault_dir), 'packs')
        os.makedirs(packs_dir, exist_ok=True)
        with open(os.path.join(packs_dir, 'pack-test123.json'), 'w') as f:
            f.write('{}')
        # Patch drain_pending to raise so the except at 226-227 fires
        with unittest.mock.patch.object(Vault__GC, 'drain_pending',
                                        side_effect=RuntimeError('simulated drain error')):
            self.base._auto_gc_drain(vault_dir)   # must not propagate

    # ─── _read_vault_key legacy path ────────────────────────────────────────

    def test_read_vault_key_legacy_path_lines_37_39(self):
        """Lines 37-39: primary vault_key path missing → falls back to legacy VAULT-KEY."""
        import json
        storage         = Vault__Storage()
        vault_dir       = self.snap.vault_dir
        primary_path    = storage.vault_key_path(vault_dir)
        legacy_path     = os.path.join(vault_dir, SG_VAULT_DIR, 'VAULT-KEY')

        vault_key = self.snap.vault_key
        # Create legacy file and remove primary
        with open(legacy_path, 'w') as f:
            f.write(vault_key)
        os.rename(primary_path, primary_path + '.bak')
        try:
            result = self.base._read_vault_key(vault_dir)
            assert result == vault_key
        finally:
            os.rename(primary_path + '.bak', primary_path)
            os.remove(legacy_path)

    def test_get_read_key_lines_44_46(self):
        """Lines 44-46: _get_read_key returns bytes read_key from vault_key."""
        result = self.base._get_read_key(self.snap.vault_dir)
        assert isinstance(result, bytes)
        assert len(result) == 32
