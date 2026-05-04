"""Coverage tests for Vault__Sync delegation methods and _pull_stats_line."""
import os
import tempfile
import shutil

import pytest

from sgit_ai.core.Vault__Sync                      import Vault__Sync
from sgit_ai.core.actions.pull.Vault__Sync__Pull   import Vault__Sync__Pull
from tests._helpers.vault_test_env import Vault__Test_Env


class Test_Pull_Stats_Line:
    """Tests for Vault__Sync__Pull._pull_stats_line instance method."""

    def test_pull_stats_line_zero_counts(self):
        result = Vault__Sync__Pull()._pull_stats_line({'t_graph': 0.1, 't_download': 0.2}, 0.3)
        assert 'commits' in result
        assert 'trees'   in result
        assert 'blobs'   in result
        assert 'in'      in result

    def test_pull_stats_line_with_commits_and_blobs(self):
        result = Vault__Sync__Pull()._pull_stats_line({'t_graph': 0.0, 't_download': 0.5,
                                                       'n_commits': 3, 'n_blobs': 10}, 1.0)
        assert '3 commits' in result
        assert '10 blobs'  in result


class Test_Vault__Sync__Delegations:
    """Quick delegation test for uncovered Vault__Sync pass-through methods."""

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

    def test_reset_to_commit(self):
        """Line 164: sync.reset() delegates to Vault__Sync__Pull."""
        result = self.sync.reset(self.vault, commit_id=self.snap.commit_id)
        assert isinstance(result, dict)

    def test_remote_add_and_list_and_remove(self):
        """Lines 191/194/197: remote_add, remote_remove, remote_list delegations."""
        add_result = self.sync.remote_add(self.vault, 'origin2', 'https://x.com', 'vid001')
        assert isinstance(add_result, dict)
        list_result = self.sync.remote_list(self.vault)   # line 197
        assert isinstance(list_result, dict)
        rm_result = self.sync.remote_remove(self.vault, 'origin2')   # line 194
        assert isinstance(rm_result, dict)

    def test_get_head_flat_map(self):
        """Line 239: sync._get_head_flat_map() delegates to Vault__Sync__Sparse."""
        result = self.sync._get_head_flat_map(self.vault)
        assert isinstance(result, tuple)
        flat = result[0]
        assert isinstance(flat, dict)

    def test_sparse_fetch(self):
        """Line 246: sync.sparse_fetch() delegates to Vault__Sync__Sparse."""
        result = self.sync.sparse_fetch(self.vault)
        assert isinstance(result, dict)
        assert 'fetched' in result

    def test_sparse_cat(self):
        """Line 250: sync.sparse_cat() delegates to Vault__Sync__Sparse."""
        content = self.sync.sparse_cat(self.vault, 'a.txt')
        assert content == b'hello'

    def test_repair_object_returns_bool(self):
        """Line 257: sync._repair_object() delegates to Vault__Sync__Fsck."""
        # Use a nonexistent object ID — should return False (not found on server)
        result = self.sync._repair_object('nonexistent-object-id', 'dummy-vault', self.vault)
        assert isinstance(result, bool)
