import os
import shutil
import tempfile

import pytest

from sgit_ai.api.Vault__API__In_Memory   import Vault__API__In_Memory
from sgit_ai.crypto.Vault__Crypto        import Vault__Crypto
from sgit_ai.sync.Vault__Revert          import Vault__Revert
from sgit_ai.sync.Vault__Sync            import Vault__Sync
from tests.unit.sync.vault_test_env      import Vault__Test_Env


class Test_Vault__Revert:

    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_single_vault()

    def setup_method(self):
        self.env       = self._env.restore()
        self.crypto    = self.env.crypto
        self.api       = self.env.api
        self.sync      = self.env.sync
        self.directory = self.env.vault_dir
        self.revert    = Vault__Revert(crypto=self.crypto)

    def teardown_method(self):
        self.env.cleanup()

    def _write(self, rel_path: str, content: str | bytes):
        full = os.path.join(self.directory, rel_path)
        parent = os.path.dirname(full)
        if parent:
            os.makedirs(parent, exist_ok=True)
        mode = 'wb' if isinstance(content, bytes) else 'w'
        with open(full, mode) as fh:
            fh.write(content)

    def _read(self, rel_path: str) -> bytes:
        with open(os.path.join(self.directory, rel_path), 'rb') as fh:
            return fh.read()

    def _exists(self, rel_path: str) -> bool:
        return os.path.isfile(os.path.join(self.directory, rel_path))

    def _commit(self, msg='test commit'):
        return self.sync.commit(self.directory, message=msg)

    # ------------------------------------------------------------------
    # Revert single file to HEAD — modified file
    # ------------------------------------------------------------------

    def test_revert_single_file_restores_committed_content(self):
        self._write('hello.txt', 'committed content')
        self._commit('add hello.txt')

        # Modify the file
        self._write('hello.txt', 'modified content')
        assert self._read('hello.txt') == b'modified content'

        result = self.revert.revert_to_head(self.directory, files=['hello.txt'])
        assert 'hello.txt' in result['restored']
        assert self._read('hello.txt') == b'committed content'

    def test_revert_single_file_returns_correct_commit_id(self):
        self._write('data.txt', 'v1')
        commit_result = self._commit('add data.txt')
        head_commit   = commit_result['commit_id']

        self._write('data.txt', 'v2')
        result = self.revert.revert_to_head(self.directory, files=['data.txt'])
        assert result['commit_id'] == head_commit

    # ------------------------------------------------------------------
    # Revert all files to HEAD
    # ------------------------------------------------------------------

    def test_revert_all_files_to_head(self):
        self._write('a.txt', 'aaa')
        self._write('b.txt', 'bbb')
        self._commit('add a+b')

        self._write('a.txt', 'modified a')
        self._write('b.txt', 'modified b')

        result = self.revert.revert_all_to_head(self.directory)
        assert 'a.txt' in result['restored']
        assert 'b.txt' in result['restored']
        assert self._read('a.txt') == b'aaa'
        assert self._read('b.txt') == b'bbb'

    def test_revert_all_deletes_count(self):
        self._write('keep.txt', 'keep')
        self._commit('add keep.txt')

        self._write('keep.txt', 'changed')
        result = self.revert.revert_all_to_head(self.directory)
        assert len(result['restored']) >= 1
        assert self._read('keep.txt') == b'keep'

    # ------------------------------------------------------------------
    # Revert file that was added (not in HEAD) — should delete it
    # ------------------------------------------------------------------

    def test_revert_added_file_deletes_it(self):
        self._write('existing.txt', 'base')
        self._commit('add existing.txt')

        # Add new file without committing
        self._write('newfile.txt', 'new content')
        assert self._exists('newfile.txt')

        result = self.revert.revert_all_to_head(self.directory)
        assert 'newfile.txt' in result['deleted']
        assert not self._exists('newfile.txt')

    def test_revert_added_file_single(self):
        self._write('base.txt', 'base')
        self._commit('add base.txt')

        self._write('extra.txt', 'extra')
        result = self.revert.revert_to_head(self.directory, files=['extra.txt'])
        assert 'extra.txt' in result['deleted']
        assert not self._exists('extra.txt')

    # ------------------------------------------------------------------
    # Revert file that was deleted (was in HEAD) — should restore it
    # ------------------------------------------------------------------

    def test_revert_deleted_file_restores_it(self):
        self._write('important.txt', 'important data')
        self._commit('add important.txt')

        # Delete file from working copy
        os.remove(os.path.join(self.directory, 'important.txt'))
        assert not self._exists('important.txt')

        result = self.revert.revert_all_to_head(self.directory)
        assert 'important.txt' in result['restored']
        assert self._exists('important.txt')
        assert self._read('important.txt') == b'important data'

    def test_revert_deleted_file_single(self):
        self._write('gone.txt', 'was here')
        self._commit('add gone.txt')

        os.remove(os.path.join(self.directory, 'gone.txt'))
        result = self.revert.revert_to_head(self.directory, files=['gone.txt'])
        assert 'gone.txt' in result['restored']
        assert self._read('gone.txt') == b'was here'

    # ------------------------------------------------------------------
    # Revert to specific commit ID (not HEAD)
    # ------------------------------------------------------------------

    def test_revert_to_specific_commit(self):
        self._write('file.txt', 'version 1')
        c1 = self._commit('v1')['commit_id']

        self._write('file.txt', 'version 2')
        self._commit('v2')

        # Working copy is at v2; revert to c1
        result = self.revert.revert_to_commit(self.directory, c1)
        assert 'file.txt' in result['restored']
        assert self._read('file.txt') == b'version 1'
        assert result['commit_id'] == c1

    def test_revert_to_specific_commit_removes_later_file(self):
        self._write('orig.txt', 'original')
        c1 = self._commit('c1')['commit_id']

        # Add a new file in the second commit
        self._write('later.txt', 'added later')
        self._commit('c2')

        # Revert to c1 — later.txt should be deleted
        result = self.revert.revert_to_commit(self.directory, c1)
        assert 'later.txt' in result['deleted']
        assert not self._exists('later.txt')
        assert self._exists('orig.txt')

    # ------------------------------------------------------------------
    # Revert with no uncommitted changes — no-op (files still restored)
    # ------------------------------------------------------------------

    def test_revert_on_clean_vault_is_noop(self):
        self._write('clean.txt', 'clean content')
        self._commit('clean commit')

        # No changes — revert should just restore same content
        result = self.revert.revert_all_to_head(self.directory)
        assert 'clean.txt' in result['restored']
        assert self._read('clean.txt') == b'clean content'
        assert result['deleted'] == []

    # ------------------------------------------------------------------
    # Initial vault (no committed files) — nothing to revert
    # ------------------------------------------------------------------

    def test_revert_empty_vault_no_commits(self):
        """After init, vault has an empty root tree. Revert is safe and no-op."""
        result = self.revert.revert_all_to_head(self.directory)
        # Empty vault: commit_id should still be set (init commit), restored/deleted can be empty
        # This just must not raise
        assert isinstance(result, dict)
        assert 'restored' in result
        assert 'deleted' in result

    # ------------------------------------------------------------------
    # Nested directory support
    # ------------------------------------------------------------------

    def test_revert_nested_file(self):
        self._write('sub/dir/deep.txt', 'deep content')
        self._commit('nested')

        self._write('sub/dir/deep.txt', 'modified deep')
        result = self.revert.revert_all_to_head(self.directory)
        assert 'sub/dir/deep.txt' in result['restored']
        assert self._read('sub/dir/deep.txt') == b'deep content'

    def test_revert_deleted_nested_dir_restored(self):
        self._write('nested/file.txt', 'nested file')
        self._commit('nested file')

        shutil.rmtree(os.path.join(self.directory, 'nested'))
        result = self.revert.revert_all_to_head(self.directory)
        assert 'nested/file.txt' in result['restored']
        assert self._read('nested/file.txt') == b'nested file'

    # ------------------------------------------------------------------
    # files filter — only specified paths are processed
    # ------------------------------------------------------------------

    def test_revert_files_filter_only_targets_specified(self):
        self._write('a.txt', 'aaa')
        self._write('b.txt', 'bbb')
        self._commit('a and b')

        self._write('a.txt', 'changed a')
        self._write('b.txt', 'changed b')

        result = self.revert.revert_to_head(self.directory, files=['a.txt'])
        assert 'a.txt' in result['restored']
        assert 'b.txt' not in result['restored']
        assert self._read('a.txt') == b'aaa'
        # b.txt was NOT reverted
        assert self._read('b.txt') == b'changed b'
