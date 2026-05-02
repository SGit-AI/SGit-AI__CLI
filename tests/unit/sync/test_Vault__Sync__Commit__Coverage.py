"""Coverage tests for Vault__Sync__Commit — _generate_commit_message (lines 200-210).

Missing lines: 200-210 in _generate_commit_message.
These are only reached when sync.commit() is called WITHOUT an explicit message.
"""
import os
import types
import unittest.mock

import pytest

from tests._helpers.vault_test_env import Vault__Test_Env


class Test_Vault__Sync__Commit__Auto_Message:
    """Call sync.commit() without a message to exercise _generate_commit_message."""

    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_single_vault(files={
            'file1.txt': 'content one\n',
            'file2.txt': 'content two\n',
        })

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

    def test_commit_without_message_generates_added_count(self):
        """Lines 200-210: added file → auto message includes 'added'."""
        with open(os.path.join(self.vault, 'new.txt'), 'w') as f:
            f.write('brand new\n')
        result = self.sync.commit(self.vault)   # no message arg
        assert 'added' in result['message']

    def test_commit_without_message_generates_modified_count(self):
        """Line 203+ (modified branch): modified file counted in auto message."""
        with open(os.path.join(self.vault, 'file1.txt'), 'w') as f:
            f.write('modified content\n')
        result = self.sync.commit(self.vault)
        assert 'modified' in result['message']

    def test_commit_without_message_generates_deleted_count(self):
        """Line 201+ (deleted branch): deleted file counted in auto message."""
        os.remove(os.path.join(self.vault, 'file1.txt'))
        result = self.sync.commit(self.vault)
        assert 'deleted' in result['message']

    def test_generate_commit_message_no_content_hash_uses_size_lines_207_210(self):
        """Lines 207-210: old entry missing content_hash → falls back to size comparison."""
        from sgit_ai.sync.Vault__Sync__Commit import Vault__Sync__Commit
        commit_mod = Vault__Sync__Commit(crypto=self.snap.crypto, api=self.snap.api)

        old_entries = {'file.txt': {'blob_id': 'obj-cas-imm-aabbccddeeff', 'size': 10, 'content_hash': ''}}
        new_file_map = {'file.txt': {'blob_id': 'obj-cas-imm-112233445566', 'size': 20, 'content_hash': ''}}
        msg = commit_mod._generate_commit_message(old_entries, new_file_map)
        assert 'modified' in msg   # size changed → counted as modified

    def test_generate_commit_message_no_content_hash_same_size_not_modified(self):
        """Lines 207-210: old and new entries same size, no content_hash → not modified."""
        from sgit_ai.sync.Vault__Sync__Commit import Vault__Sync__Commit
        commit_mod = Vault__Sync__Commit(crypto=self.snap.crypto, api=self.snap.api)

        old_entries  = {'file.txt': {'size': 10, 'content_hash': ''}}
        new_file_map = {'file.txt': {'size': 10, 'content_hash': ''}}
        msg = commit_mod._generate_commit_message(old_entries, new_file_map)
        assert '0 modified' in msg

    # ─── no-branch-index guard ──────────────────────────────────────────────

    def _fake_components(self):
        from sgit_ai.sync.Vault__Storage import Vault__Storage
        return types.SimpleNamespace(
            read_key=b'',
            storage=Vault__Storage(),
            obj_store=None, ref_manager=None, pki=None,
            key_manager=None, branch_manager=None,
            branch_index_file_id='',
            vault_id='', sg_dir='', vault_key='', write_key='', ref_file_id='',
        )

    def test_commit_no_branch_index_raises_line_31(self):
        """Line 31: commit() with empty branch_index_file_id → RuntimeError."""
        from sgit_ai.sync.Vault__Sync__Base   import Vault__Sync__Base
        from sgit_ai.sync.Vault__Sync__Commit import Vault__Sync__Commit
        commit_mod = Vault__Sync__Commit(crypto=self.snap.crypto, api=self.snap.api)
        with unittest.mock.patch.object(Vault__Sync__Base, '_init_components',
                                        return_value=self._fake_components()):
            with pytest.raises(RuntimeError, match='No branch index found'):
                commit_mod.commit(self.vault)

    def test_write_file_no_branch_index_raises_line_111(self):
        """Line 111: write_file() with empty branch_index_file_id → RuntimeError."""
        from sgit_ai.sync.Vault__Sync__Base   import Vault__Sync__Base
        from sgit_ai.sync.Vault__Sync__Commit import Vault__Sync__Commit
        commit_mod = Vault__Sync__Commit(crypto=self.snap.crypto, api=self.snap.api)
        fake_c = self._fake_components()
        fake_c.write_key = 'nonempty-write-key'   # pass the read-only guard
        with unittest.mock.patch.object(Vault__Sync__Base, '_init_components', return_value=fake_c):
            with pytest.raises(RuntimeError, match='No branch index found'):
                commit_mod.write_file(self.vault, 'test.txt', b'hello')
