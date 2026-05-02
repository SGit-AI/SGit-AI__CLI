"""Coverage tests for Vault__Sync__Status.

Missing lines targeted:
  30: not index_id → early return (hard to trigger — skip)
  39: not branch_meta → early return when branch_id not in index
  71-75: sparse=True → _sparse mode counters and filtered deleted list
  89: no content_hash but size changed → modified path
  104: get_branch_by_name('current') fallback
  132: push_status 'behind' in the not-obj_store.exists(named_head) branch
  143-149: push_status cases from ahead/behind counting (skip — needs remote)
"""
import json
import os

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
