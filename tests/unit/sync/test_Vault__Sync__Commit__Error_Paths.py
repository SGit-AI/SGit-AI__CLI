"""Coverage tests for Vault__Sync__Commit error/edge paths.

Missing lines targeted:
  35: commit() branch not found → RuntimeError
  61-62: commit() signing key not found → except pass (commit still succeeds)
  115: write_file() branch not found → RuntimeError
  167-168: write_file() signing key not found → except pass
"""
import json
import os
import glob

import pytest

from tests._helpers.vault_test_env import Vault__Test_Env


class Test_Vault__Sync__Commit__Error_Paths:

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

    def _delete_signing_key(self) -> None:
        local_dir = os.path.join(self.vault, '.sg_vault', 'local')
        for pem in glob.glob(os.path.join(local_dir, 'key-*.pem')):
            os.remove(pem)

    # ─── lines 35: branch not found in commit() ──────────────────────────

    def test_commit_unknown_branch_raises_line_35(self):
        """Line 35: my_branch_id not in index → RuntimeError 'Branch not found'."""
        config_path = self._local_config_path()
        with open(config_path, 'r') as f:
            cfg = json.load(f)
        cfg['my_branch_id'] = 'branch-clone-0000000000000000'
        with open(config_path, 'w') as f:
            json.dump(cfg, f)
        with open(os.path.join(self.vault, 'new.txt'), 'w') as f:
            f.write('new')
        with pytest.raises(RuntimeError, match='Branch not found'):
            self.sync.commit(self.vault, message='test')

    # ─── lines 61-62: no signing key in commit() ─────────────────────────

    def test_commit_missing_signing_key_still_commits_lines_61_62(self):
        """Lines 61-62: private key file absent → except pass → commit proceeds unsigned."""
        self._delete_signing_key()
        with open(os.path.join(self.vault, 'new.txt'), 'w') as f:
            f.write('content')
        result = self.sync.commit(self.vault, message='no sig')
        assert result['commit_id'] is not None

    # ─── line 115: branch not found in write_file() ──────────────────────

    def test_write_file_unknown_branch_raises_line_115(self):
        """Line 115: my_branch_id not in index → RuntimeError 'Branch not found'."""
        config_path = self._local_config_path()
        with open(config_path, 'r') as f:
            cfg = json.load(f)
        cfg['my_branch_id'] = 'branch-clone-0000000000000000'
        with open(config_path, 'w') as f:
            json.dump(cfg, f)
        with pytest.raises(RuntimeError, match='Branch not found'):
            self.sync.write_file(self.vault, 'new.txt', b'hello')

    # ─── lines 167-168: no signing key in write_file() ─────────────────���─

    def test_write_file_missing_signing_key_still_writes_lines_167_168(self):
        """Lines 167-168: private key file absent → except pass → write proceeds."""
        self._delete_signing_key()
        result = self.sync.write_file(self.vault, 'via_write.txt', b'written')
        assert result['commit_id'] is not None
