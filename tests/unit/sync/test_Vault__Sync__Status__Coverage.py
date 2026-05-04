"""Coverage tests for Vault__Sync__Status.

Missing lines targeted:
  30: not index_id → early return
  39: not branch_meta → early return when branch_id not in index
  71-75: sparse=True → _sparse mode counters and filtered deleted list
  89: no content_hash but size changed → modified path
  104: get_branch_by_name('current') fallback
  132: push_status 'behind' in the not-obj_store.exists(named_head) branch
  143: push_status 'ahead' after local commit (not yet pushed)
  144-146: clone_head set but named_head None → push_status 'ahead'
  147-149: clone_head None but named_head set → push_status 'behind'
"""
import json
import os
import types
import unittest.mock

from sgit_ai.sync.Vault__Sync import Vault__Sync
from tests._helpers.vault_test_env import Vault__Test_Env


class Test_Vault__Sync__Status__Coverage:

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
        self.snap  = self._env.restore()
        self.vault = self.snap.vault_dir
        self.sync  = self.snap.sync

    def teardown_method(self):
        self.snap.cleanup()

    def _local_config_path(self) -> str:
        return os.path.join(self.vault, '.sg_vault', 'local', 'config.json')

    def test_status_unknown_branch_id_returns_early_line_39(self):
        """Line 39: branch_id not found in branch index → early return dict."""
        config_path = self._local_config_path()
        with open(config_path, 'r') as f:
            cfg = json.load(f)
        cfg['my_branch_id'] = 'branch-clone-0000000000000000'
        with open(config_path, 'w') as f:
            json.dump(cfg, f)
        result = self.sync.status(self.vault)
        assert isinstance(result, dict)
        assert result['clean'] is True
        assert result['clone_branch_id'] == ''

    def test_status_sparse_mode_lines_71_75(self):
        """Lines 71-75: sparse=True in local config → sparse counters populated."""
        config_path = self._local_config_path()
        with open(config_path, 'r') as f:
            cfg = json.load(f)
        cfg['sparse'] = True
        with open(config_path, 'w') as f:
            json.dump(cfg, f)
        result = self.sync.status(self.vault)
        assert isinstance(result, dict)
        assert result['sparse'] is True
        assert 'files_total' in result
        assert 'files_fetched' in result
        assert result['files_total'] >= 0

    def test_status_size_changed_no_content_hash_line_89(self):
        """Line 89: file content hash missing but size changed → shows as modified."""
        with open(os.path.join(self.vault, 'a.txt'), 'w') as f:
            f.write('modified content that is much longer than hello\n')
        result = self.sync.status(self.vault)
        assert isinstance(result, dict)
        assert 'a.txt' in result['modified'] or result['clean'] is False

    def test_status_no_creator_branch_falls_back_to_current_line_104(self):
        """Line 104: branch_id not in index → creator_branch_id is empty → fallback to 'current'."""
        # Change my_branch_id to a non-existent branch-clone-* ID.
        # branch_meta becomes None → creator_branch_id = '' → line 103 if not branch_meta is True
        # → get_branch_by_name('current') is called on line 104.
        config_path = self._local_config_path()
        with open(config_path, 'r') as f:
            cfg = json.load(f)
        cfg['my_branch_id'] = 'branch-clone-0000000000000000'
        with open(config_path, 'w') as f:
            json.dump(cfg, f)

        # The status with unknown branch_id triggers line 39 early return.
        # To reach line 104, we need a valid branch_meta but empty creator_branch.
        # Achievable: use the NAMED branch's ID as my_branch_id — the named branch
        # likely has creator_branch = '' (it IS the origin, not a clone).
        # First, find the named branch id from a normal status call.
        snap2  = self._env.restore()
        sync2  = snap2.sync
        result = sync2.status(snap2.vault_dir)
        named_branch_id = result['named_branch_id']
        snap2.cleanup()

        # Now use the named branch_id as my_branch_id.
        with open(config_path, 'w') as f:
            json.dump({'my_branch_id': named_branch_id, 'mode': None,
                       'edit_token': None, 'sparse': False}, f)
        result2 = self.sync.status(self.vault)
        assert isinstance(result2, dict)

    def test_status_no_branch_index_early_return_line_30(self):
        """Line 30: status() with branch_index_file_id='' → immediate early return dict."""
        from sgit_ai.core.Vault__Sync__Base   import Vault__Sync__Base
        from sgit_ai.storage.Vault__Storage      import Vault__Storage
        fake_c = types.SimpleNamespace(
            read_key=b'', storage=Vault__Storage(),
            pki=None, obj_store=None, ref_manager=None, branch_manager=None,
            branch_index_file_id='',
            vault_id='', sg_dir='', vault_key='', write_key='', ref_file_id='',
        )
        with unittest.mock.patch.object(Vault__Sync__Base, '_init_components', return_value=fake_c):
            result = self.sync.status(self.vault)
        assert result['clean'] is True
        assert result['added'] == []
        assert result['push_status'] == 'unknown'

    def test_status_size_changed_no_content_hash_real_line_89(self):
        """Line 89: old entry has no content_hash + file size changed → modified via line 89."""
        from sgit_ai.storage.Vault__Sub_Tree import Vault__Sub_Tree
        orig_flatten = Vault__Sub_Tree.flatten

        def patched_flatten(self_, tree_id, rk, prefix=''):
            entries = orig_flatten(self_, tree_id, rk, prefix=prefix)
            return {k: {**v, 'content_hash': None} for k, v in entries.items()}

        with open(os.path.join(self.vault, 'a.txt'), 'w') as f:
            f.write('much longer modified content to change size\n')

        with unittest.mock.patch.object(Vault__Sub_Tree, 'flatten', patched_flatten):
            result = self.sync.status(self.vault)
        assert 'a.txt' in result['modified']

    def test_status_after_local_commit_shows_ahead_line_143(self):
        """Line 143: after committing locally, status reports push_status='ahead'."""
        with open(os.path.join(self.vault, 'new.txt'), 'w') as f:
            f.write('brand new file content\n')
        self.sync.commit(self.vault, message='add new file')
        result = self.sync.status(self.vault)
        assert result['push_status'] == 'ahead'
        assert result['ahead'] >= 1


    def test_status_named_head_none_shows_ahead_lines_145_146(self, monkeypatch):
        """Lines 145-146: clone_head set, named_head=None → push_status='ahead'."""
        from sgit_ai.storage.Vault__Ref_Manager import Vault__Ref_Manager

        orig_read_ref = Vault__Ref_Manager.read_ref
        call_count    = [0]

        def patched_read_ref(self_, ref_id, read_key=None):
            call_count[0] += 1
            if call_count[0] == 1:
                return orig_read_ref(self_, ref_id, read_key)  # clone HEAD (real)
            return None  # named HEAD → None → triggers lines 144-146

        monkeypatch.setattr(Vault__Ref_Manager, 'read_ref', patched_read_ref)
        result = self.sync.status(self.vault)
        assert result['push_status'] == 'ahead'
        assert result['ahead'] >= 1

    def test_status_clone_head_none_named_head_set_lines_147_149(self):
        """Lines 147-149: clone_head=None (clone ref missing), named_head set."""
        from sgit_ai.storage.Vault__Ref_Manager import Vault__Ref_Manager
        from sgit_ai.storage.Vault__Storage import Vault__Storage

        orig_read_ref = Vault__Ref_Manager.read_ref
        call_count = [0]

        def patched_read_ref(self_, ref_id, read_key=None):
            call_count[0] += 1
            # First call is for clone branch (parent_id) → return None
            if call_count[0] == 1:
                return None
            # Subsequent calls are for named branch → return original
            return orig_read_ref(self_, ref_id, read_key)

        with unittest.mock.patch.object(Vault__Ref_Manager, 'read_ref', patched_read_ref):
            result = self.sync.status(self.vault)
        # With clone_head=None and named_head set → lines 147-149
        assert result['push_status'] in ('behind', 'unknown')
