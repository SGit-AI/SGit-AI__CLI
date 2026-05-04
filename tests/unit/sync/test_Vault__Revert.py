import json
import os
import shutil
import tempfile

import pytest

from sgit_ai.api.Vault__API__In_Memory   import Vault__API__In_Memory
from sgit_ai.crypto.Vault__Crypto        import Vault__Crypto
from sgit_ai.storage.Vault__Commit       import Vault__Commit
from sgit_ai.core.actions.revert.Vault__Revert          import Vault__Revert
from sgit_ai.storage.Vault__Sub_Tree        import Vault__Sub_Tree
from sgit_ai.core.Vault__Sync            import Vault__Sync
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

    def test_revert_removes_empty_parent_dirs(self):
        """Lines 193-197: adding a file in a new subdir, then reverting deletes it and
        removes the now-empty parent directory."""
        # Commit some file so HEAD has content
        self._write('base.txt', 'base content')
        self._commit('base')
        # Add a new file in a brand-new subdirectory (not committed)
        self._write('newdir/sub/extra.txt', 'uncommitted')
        # Revert to head → deletes newdir/sub/extra.txt → removes empty newdir/sub and newdir
        result = self.revert.revert_all_to_head(self.directory)
        assert 'newdir/sub/extra.txt' in result['deleted']
        assert not os.path.isdir(os.path.join(self.directory, 'newdir'))

    def test_revert_no_head_commit_returns_empty_result(self):
        """Line 34: when vault has no resolvable HEAD commit, returns empty result.

        We simulate this by patching _resolve_head_commit_id to return None.
        """
        from sgit_ai.core.actions.revert.Vault__Revert import Vault__Revert
        from unittest.mock import patch

        with patch.object(Vault__Revert, '_resolve_head_commit_id', return_value=None):
            result = self.revert.revert_all_to_head(self.directory)
        assert result == dict(restored=[], deleted=[], commit_id=None)

    def test_revert_scan_ignores_files_in_sgignore(self):
        """Line 142: files matching .sgignore are skipped in working-dir scan."""
        import os
        # Commit a file
        self._write('keep.txt', 'keep')
        self._commit('keep commit')
        # Write a .gitignore
        self._write('.gitignore', '*.log\n')
        # Write a file that should be ignored
        self._write('debug.log', 'should be ignored')
        # The ignored file should NOT appear in the scan
        from sgit_ai.core.actions.revert.Vault__Revert import Vault__Revert
        revert = Vault__Revert(crypto=self.crypto)
        result = revert.revert_all_to_head(self.directory)
        # debug.log should NOT be in deleted (it was ignored)
        assert 'debug.log' not in result.get('deleted', [])

    # ------------------------------------------------------------------
    # Line 96: _resolve_head_commit_id returns None when no branch_index_file_id
    # ------------------------------------------------------------------

    def test_resolve_head_commit_id_returns_none_when_no_index(self, monkeypatch):
        """Line 96: _resolve_head_commit_id returns None when branch_index_file_id is ''."""
        orig_init = Vault__Revert._init_components

        def fake_init(self_, dir_):
            c = orig_init(self_, dir_)
            c.branch_index_file_id = ''
            return c

        monkeypatch.setattr(Vault__Revert, '_init_components', fake_init)
        result = self.revert.revert_all_to_head(self.directory)
        assert result == dict(restored=[], deleted=[], commit_id=None)

    # ------------------------------------------------------------------
    # Line 100: _resolve_head_commit_id returns None when branch_meta not found
    # ------------------------------------------------------------------

    def test_resolve_head_commit_id_returns_none_when_branch_meta_missing(self):
        """Line 100: _resolve_head_commit_id returns None when my_branch_id not in index."""
        c           = self.revert._init_components(self.directory)
        config_path = c.storage.local_config_path(self.directory)
        with open(config_path, 'w') as fh:
            json.dump({'my_branch_id': 'branch-clone-00000000deadbeef'}, fh)
        result = self.revert.revert_all_to_head(self.directory)
        assert result == dict(restored=[], deleted=[], commit_id=None)

    # ------------------------------------------------------------------
    # Line 123: _flatten_commit continues when blob_id is empty
    # ------------------------------------------------------------------

    def test_flatten_commit_skips_entry_with_no_blob_id(self, monkeypatch):
        """Line 123: flat_map entry with empty blob_id → continue (not included in result)."""
        self._write('file.txt', 'content')
        self._commit('initial')

        class FakeCommit:
            tree_id = 'tree-0000000000000000'

        monkeypatch.setattr(Vault__Commit, 'load_commit',
                            lambda self_, cid, rk: FakeCommit())
        monkeypatch.setattr(Vault__Sub_Tree, 'flatten',
                            lambda self_, tree_id, rk: {
                                'empty.txt': {'blob_id': '', 'size': 0, 'content_hash': ''}
                            })

        c      = self.revert._init_components(self.directory)
        result = self.revert._flatten_commit(c, 'any-commit-id')
        # Entry with empty blob_id was skipped → result is empty
        assert result == {}

    # ------------------------------------------------------------------
    # Line 197: _remove_empty_parent_dirs breaks when parent dir is not empty
    # ------------------------------------------------------------------

    def test_remove_empty_parent_dirs_stops_at_nonempty_dir(self):
        """Line 197: break when parent directory is not empty (has other files)."""
        tmp = tempfile.mkdtemp()
        try:
            # Create: tmp/parent/sibling.txt  (parent will not be empty)
            #         tmp/parent/sub/removed.txt
            sub_dir = os.path.join(tmp, 'parent', 'sub')
            os.makedirs(sub_dir)
            sibling = os.path.join(tmp, 'parent', 'sibling.txt')
            removed = os.path.join(sub_dir, 'removed.txt')
            with open(sibling, 'w') as fh:
                fh.write('sibling')
            with open(removed, 'w') as fh:
                fh.write('removed')
            # Simulate the file being removed before calling _remove_empty_parent_dirs
            os.remove(removed)
            # 'sub' is now empty → should be removed; 'parent' has sibling → break
            self.revert._remove_empty_parent_dirs(tmp, removed)
            # 'sub' should be gone (was empty)
            assert not os.path.isdir(sub_dir)
            # 'parent' should still exist (has sibling.txt)
            assert os.path.isdir(os.path.join(tmp, 'parent'))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
