"""Coverage tests for Vault__Sync__Sparse._get_head_flat_map.

Missing lines targeted:
  30: not branch_meta via branch_id → fallback to get_branch_by_name('current')
  34: commit_id is None (ref deleted) → return early tuple
"""
import json
import os

from tests._helpers.vault_test_env import Vault__Test_Env


class Test_Vault__Sync__Sparse__Coverage:

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

    def _local_config_path(self) -> str:
        return os.path.join(self.vault, '.sg_vault', 'local', 'config.json')

    def _delete_all_refs(self) -> None:
        refs_dir = os.path.join(self.vault, '.sg_vault', 'bare', 'refs')
        for f in os.listdir(refs_dir):
            if f.startswith('ref-pid-'):
                os.remove(os.path.join(refs_dir, f))

    def test_get_head_flat_map_unknown_branch_falls_back_line_30(self):
        """Line 30: my_branch_id not in index → fallback to get_branch_by_name('current')."""
        config_path = self._local_config_path()
        with open(config_path, 'r') as f:
            cfg = json.load(f)
        cfg['my_branch_id'] = 'branch-clone-0000000000000000'
        with open(config_path, 'w') as f:
            json.dump(cfg, f)
        # sparse_fetch uses _get_head_flat_map internally → falls back to 'current' branch
        result = self.sync.sparse_fetch(self.vault)
        assert isinstance(result, dict)

    def test_get_head_flat_map_no_commit_returns_early_line_34(self):
        """Line 34: no HEAD commit (all refs deleted) → return empty tuple."""
        # Use non-existent branch_id so fallback to 'current' is tried too
        config_path = self._local_config_path()
        with open(config_path, 'r') as f:
            cfg = json.load(f)
        cfg['my_branch_id'] = 'branch-clone-0000000000000000'
        with open(config_path, 'w') as f:
            json.dump(cfg, f)
        # Delete all refs so no HEAD ref for the 'current' branch either
        self._delete_all_refs()
        result = self.sync.sparse_fetch(self.vault)
        assert result.get('fetched', 0) == 0
