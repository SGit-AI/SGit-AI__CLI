"""Coverage tests for Vault__Sync__Commit — _generate_commit_message (lines 200-210).

Missing lines: 200-210 in _generate_commit_message.
These are only reached when sync.commit() is called WITHOUT an explicit message.
"""
import os

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
