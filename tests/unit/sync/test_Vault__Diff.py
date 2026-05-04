import hashlib
import os
import shutil
import tempfile

import pytest

from sgit_ai.crypto.Vault__Crypto        import Vault__Crypto
from sgit_ai.schemas.Schema__Diff_File   import Schema__Diff_File
from sgit_ai.schemas.Schema__Diff_Result import Schema__Diff_Result
from sgit_ai.core.actions.diff.Vault__Diff            import Vault__Diff, BINARY_CHECK_BYTES
from tests._helpers.vault_test_env       import Vault__Test_Env


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _make_diff() -> Vault__Diff:
    return Vault__Diff(crypto=Vault__Crypto())


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------

class Test_Vault__Diff:

    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_single_vault()

    @classmethod
    def teardown_class(cls):
        if cls._env:
            cls._env.cleanup_snapshot()

    # ------------------------------------------------------------------
    # Binary detection
    # ------------------------------------------------------------------

    def test_is_binary_null_byte(self):
        d = _make_diff()
        assert d._is_binary(b'hello\x00world') is True

    def test_is_binary_no_null_byte(self):
        d = _make_diff()
        assert d._is_binary(b'hello world') is False

    def test_is_binary_empty(self):
        d = _make_diff()
        assert d._is_binary(b'') is False

    def test_is_binary_only_null(self):
        d = _make_diff()
        assert d._is_binary(b'\x00') is True

    def test_is_binary_null_after_check_limit(self):
        # null byte beyond BINARY_CHECK_BYTES — should NOT be detected as binary
        d    = _make_diff()
        data = b'a' * BINARY_CHECK_BYTES + b'\x00'
        assert d._is_binary(data) is False

    def test_is_binary_null_at_limit_boundary(self):
        # null byte exactly at position BINARY_CHECK_BYTES - 1 — inside check window
        d    = _make_diff()
        data = b'a' * (BINARY_CHECK_BYTES - 1) + b'\x00'
        assert d._is_binary(data) is True

    def test_is_binary_text_with_high_bytes(self):
        # UTF-8 content has high bytes but no null
        d = _make_diff()
        assert d._is_binary('héllo'.encode('utf-8')) is False

    # ------------------------------------------------------------------
    # SHA-256 helper
    # ------------------------------------------------------------------

    def test_sha256_known_value(self):
        d      = _make_diff()
        result = d._sha256(b'hello')
        assert result == hashlib.sha256(b'hello').hexdigest()

    def test_sha256_empty(self):
        d      = _make_diff()
        result = d._sha256(b'')
        assert result == hashlib.sha256(b'').hexdigest()

    # ------------------------------------------------------------------
    # diff_single_file — added
    # ------------------------------------------------------------------

    def test_diff_single_file_added(self):
        d      = _make_diff()
        result = d.diff_single_file('new.txt', None, b'hello')
        assert result.status      == 'added'
        assert int(result.size_before) == 0
        assert int(result.size_after)  == 5
        assert result.hash_before is None
        assert str(result.hash_after) == _sha256(b'hello')

    def test_diff_single_file_added_binary(self):
        d      = _make_diff()
        result = d.diff_single_file('img.bin', None, b'\x00\x01\x02')
        assert result.status    == 'added'
        assert result.is_binary is True

    def test_diff_single_file_added_diff_text_empty(self):
        d      = _make_diff()
        result = d.diff_single_file('new.txt', None, b'hello')
        # diff_text should not be present for added files
        assert not result.diff_text

    # ------------------------------------------------------------------
    # diff_single_file — deleted
    # ------------------------------------------------------------------

    def test_diff_single_file_deleted(self):
        d      = _make_diff()
        result = d.diff_single_file('old.txt', b'hello', None)
        assert result.status      == 'deleted'
        assert int(result.size_before) == 5
        assert int(result.size_after)  == 0
        assert str(result.hash_before) == _sha256(b'hello')
        assert result.hash_after is None

    def test_diff_single_file_deleted_binary(self):
        d      = _make_diff()
        result = d.diff_single_file('img.bin', b'\x00data', None)
        assert result.status    == 'deleted'
        assert result.is_binary is True

    def test_diff_single_file_deleted_diff_text_empty(self):
        d      = _make_diff()
        result = d.diff_single_file('old.txt', b'hello', None)
        assert not result.diff_text

    # ------------------------------------------------------------------
    # diff_single_file — unchanged
    # ------------------------------------------------------------------

    def test_diff_single_file_unchanged(self):
        d    = _make_diff()
        data = b'same content'
        result = d.diff_single_file('file.txt', data, data)
        assert result.status == 'unchanged'

    def test_diff_single_file_unchanged_hashes_equal(self):
        d    = _make_diff()
        data = b'same'
        result = d.diff_single_file('f.txt', data, data)
        assert str(result.hash_before) == str(result.hash_after)

    def test_diff_single_file_unchanged_no_diff_text(self):
        d    = _make_diff()
        data = b'same'
        result = d.diff_single_file('f.txt', data, data)
        assert not result.diff_text

    def test_diff_single_file_both_none_unchanged(self):
        d      = _make_diff()
        result = d.diff_single_file('ghost.txt', None, None)
        assert result.status == 'unchanged'

    # ------------------------------------------------------------------
    # diff_single_file — modified (text)
    # ------------------------------------------------------------------

    def test_diff_single_file_modified_text(self):
        d      = _make_diff()
        before = b'line one\nline two\n'
        after  = b'line one\nline two\nline three\n'
        result = d.diff_single_file('file.txt', before, after)
        assert result.status    == 'modified'
        assert result.is_binary is False
        assert result.diff_text
        assert '+line three' in str(result.diff_text)

    def test_diff_single_file_modified_diff_has_headers(self):
        d      = _make_diff()
        before = b'a\n'
        after  = b'b\n'
        result = d.diff_single_file('test.txt', before, after)
        diff   = str(result.diff_text)
        assert '--- a/test.txt' in diff
        assert '+++ b/test.txt' in diff

    def test_diff_single_file_modified_sizes_correct(self):
        d      = _make_diff()
        before = b'hello'
        after  = b'hello world'
        result = d.diff_single_file('f.txt', before, after)
        assert int(result.size_before) == 5
        assert int(result.size_after)  == 11

    def test_diff_single_file_modified_hashes_differ(self):
        d      = _make_diff()
        before = b'aaa'
        after  = b'bbb'
        result = d.diff_single_file('f.txt', before, after)
        assert str(result.hash_before) != str(result.hash_after)
        assert str(result.hash_before) == _sha256(b'aaa')
        assert str(result.hash_after)  == _sha256(b'bbb')

    def test_diff_single_file_whitespace_only_change(self):
        d      = _make_diff()
        before = b'line\n'
        after  = b'line  \n'
        result = d.diff_single_file('f.txt', before, after)
        assert result.status == 'modified'
        assert result.diff_text

    # ------------------------------------------------------------------
    # diff_single_file — modified (binary)
    # ------------------------------------------------------------------

    def test_diff_single_file_modified_binary(self):
        d      = _make_diff()
        before = b'\x00\x01\x02\x03'
        after  = b'\x00\x04\x05\x06'
        result = d.diff_single_file('img.bin', before, after)
        assert result.status    == 'modified'
        assert result.is_binary is True
        assert not result.diff_text

    def test_diff_single_file_modified_binary_before_only(self):
        # before is binary, after is text — still binary
        d      = _make_diff()
        before = b'\x00data'
        after  = b'text'
        result = d.diff_single_file('mixed.bin', before, after)
        assert result.is_binary is True
        assert not result.diff_text

    # ------------------------------------------------------------------
    # diff_single_file — unicode text
    # ------------------------------------------------------------------

    def test_diff_single_file_unicode(self):
        d      = _make_diff()
        before = 'héllo wörld\n'.encode('utf-8')
        after  = 'héllo wörld!\n'.encode('utf-8')
        result = d.diff_single_file('unicode.txt', before, after)
        assert result.status == 'modified'
        assert result.diff_text

    # ------------------------------------------------------------------
    # diff_single_file — empty file
    # ------------------------------------------------------------------

    def test_diff_single_file_empty_file_not_binary(self):
        d      = _make_diff()
        result = d.diff_single_file('empty.txt', b'', b'')
        assert result.status    == 'unchanged'
        assert result.is_binary is False

    def test_diff_single_file_empty_to_content(self):
        d      = _make_diff()
        result = d.diff_single_file('f.txt', b'', b'new content\n')
        assert result.status == 'modified'

    # ------------------------------------------------------------------
    # diff_single_file — subdirectory paths
    # ------------------------------------------------------------------

    def test_diff_single_file_subdir_path(self):
        d      = _make_diff()
        result = d.diff_single_file('subdir/deep/file.txt', None, b'content')
        assert result.status == 'added'
        assert str(result.path) == 'subdir/deep/file.txt'

    # ------------------------------------------------------------------
    # diff_files — empty dicts
    # ------------------------------------------------------------------

    def test_diff_files_both_empty(self):
        d      = _make_diff()
        result = d.diff_files({}, {})
        assert result == []

    def test_diff_files_working_only(self):
        d      = _make_diff()
        result = d.diff_files({'a.txt': b'hello'}, {})
        assert len(result) == 1
        assert result[0].status == 'added'

    def test_diff_files_committed_only(self):
        d      = _make_diff()
        result = d.diff_files({}, {'a.txt': b'hello'})
        assert len(result) == 1
        assert result[0].status == 'deleted'

    def test_diff_files_identical(self):
        data   = {f'file{i}.txt': b'content' for i in range(5)}
        d      = _make_diff()
        result = d.diff_files(data, data)
        assert all(r.status == 'unchanged' for r in result)

    def test_diff_files_all_added(self):
        working = {'a.txt': b'aaa', 'b.txt': b'bbb'}
        d       = _make_diff()
        result  = d.diff_files(working, {})
        assert all(r.status == 'added' for r in result)
        assert len(result) == 2

    def test_diff_files_all_deleted(self):
        committed = {'a.txt': b'aaa', 'b.txt': b'bbb'}
        d         = _make_diff()
        result    = d.diff_files({}, committed)
        assert all(r.status == 'deleted' for r in result)
        assert len(result) == 2

    def test_diff_files_mixed(self):
        working   = {'new.txt': b'new', 'same.txt': b'same', 'mod.txt': b'v2'}
        committed = {'old.txt': b'old', 'same.txt': b'same', 'mod.txt': b'v1'}
        d         = _make_diff()
        result    = d.diff_files(working, committed)
        by_path   = {str(r.path): r for r in result}
        assert by_path['new.txt'].status  == 'added'
        assert by_path['old.txt'].status  == 'deleted'
        assert by_path['same.txt'].status == 'unchanged'
        assert by_path['mod.txt'].status  == 'modified'

    def test_diff_files_sorted_paths(self):
        working   = {'z.txt': b'z', 'a.txt': b'a', 'm.txt': b'm'}
        d         = _make_diff()
        result    = d.diff_files(working, {})
        paths     = [str(r.path) for r in result]
        assert paths == sorted(paths)

    # ------------------------------------------------------------------
    # _build_result — count fields
    # ------------------------------------------------------------------

    def test_build_result_counts(self):
        d = _make_diff()
        files = [
            Schema__Diff_File(path='a.txt', status='added'),
            Schema__Diff_File(path='b.txt', status='added'),
            Schema__Diff_File(path='c.txt', status='modified'),
            Schema__Diff_File(path='d.txt', status='deleted'),
            Schema__Diff_File(path='e.txt', status='unchanged'),
        ]
        result = d._build_result('/tmp/vault', 'head', '', files)
        assert int(result.added_count)    == 2
        assert int(result.modified_count) == 1
        assert int(result.deleted_count)  == 1

    def test_build_result_mode_head(self):
        d      = _make_diff()
        result = d._build_result('/tmp', 'head', '', [])
        assert str(result.mode) == 'head'

    def test_build_result_mode_commit_with_id(self):
        d      = _make_diff()
        result = d._build_result('/tmp', 'commit', 'abc123', [])
        assert str(result.mode)      == 'commit'
        assert str(result.commit_id) == 'abc123'

    def test_build_result_returns_schema(self):
        d      = _make_diff()
        result = d._build_result('/tmp', 'head', '', [])
        assert isinstance(result, Schema__Diff_Result)

    # ------------------------------------------------------------------
    # Large diff
    # ------------------------------------------------------------------

    def test_diff_large_text_file(self):
        d      = _make_diff()
        before = '\n'.join(f'line {i}' for i in range(500)).encode()
        after  = '\n'.join(f'line {i}' for i in range(250)).encode()
        result = d.diff_single_file('large.txt', before, after)
        assert result.status == 'modified'
        assert result.diff_text

    # ------------------------------------------------------------------
    # diff_vs_head with a real on-disk vault (integration-style but local)
    # ------------------------------------------------------------------

    def test_diff_vs_head_with_real_vault(self):
        """Commit a file, modify it and add another, then diff."""
        env = self._env.restore()
        try:
            tmp = env.vault_dir
            with open(os.path.join(tmp, 'hello.txt'), 'w') as f:
                f.write('Hello, world!\n')
            env.sync.commit(tmp, message='add hello.txt')

            with open(os.path.join(tmp, 'hello.txt'), 'w') as f:
                f.write('Hello, world!\nNew line!\n')
            with open(os.path.join(tmp, 'new.txt'), 'w') as f:
                f.write('brand new\n')

            diff_engine = Vault__Diff(crypto=Vault__Crypto())
            result      = diff_engine.diff_vs_head(tmp)

            by_path = {str(f.path): f for f in result.files}
            assert by_path['hello.txt'].status == 'modified'
            assert by_path['new.txt'].status   == 'added'
            assert int(result.modified_count)  == 1
            assert int(result.added_count)     == 1
        finally:
            env.cleanup()

    def test_diff_vs_head_clean_vault(self):
        """Vault with no working changes should show no diffs."""
        env = self._env.restore()
        try:
            tmp = env.vault_dir
            with open(os.path.join(tmp, 'file.txt'), 'w') as f:
                f.write('content\n')
            env.sync.commit(tmp, message='initial')

            diff_engine = Vault__Diff(crypto=Vault__Crypto())
            result      = diff_engine.diff_vs_head(tmp)

            assert int(result.added_count)    == 0
            assert int(result.modified_count) == 0
            assert int(result.deleted_count)  == 0
        finally:
            env.cleanup()

    def test_diff_vs_head_deleted_file(self):
        """Delete a committed file and confirm it shows as deleted."""
        env = self._env.restore()
        try:
            tmp  = env.vault_dir
            path = os.path.join(tmp, 'todelete.txt')
            with open(path, 'w') as f:
                f.write('will be deleted\n')
            env.sync.commit(tmp, message='add file')
            os.remove(path)

            diff_engine = Vault__Diff(crypto=Vault__Crypto())
            result      = diff_engine.diff_vs_head(tmp)

            assert int(result.deleted_count) == 1
            deleted = [f for f in result.files if f.status == 'deleted']
            assert deleted[0].path == 'todelete.txt'
        finally:
            env.cleanup()

    def test_diff_scan_working_ignores_gitignored_file(self):
        """Files matching .gitignore are skipped in _scan_working_files."""
        env = self._env.restore()
        try:
            tmp = env.vault_dir
            with open(os.path.join(tmp, 'keep.txt'), 'w') as f:
                f.write('keep\n')
            with open(os.path.join(tmp, '.gitignore'), 'w') as f:
                f.write('*.log\n')
            env.sync.commit(tmp, message='initial')
            with open(os.path.join(tmp, 'debug.log'), 'w') as f:
                f.write('ignored\n')

            diff_engine = Vault__Diff(crypto=Vault__Crypto())
            result      = diff_engine.diff_vs_head(tmp)
            added_paths = [str(f.path) for f in result.files if f.status == 'added']
            assert 'debug.log' not in added_paths
        finally:
            env.cleanup()

    def test_read_commit_files_none_commit_id(self):
        """Line 286: _read_commit_files returns {} when commit_id is None."""
        from sgit_ai.core.Vault__Components import Vault__Components
        diff    = _make_diff()
        c       = Vault__Components()
        result  = diff._read_commit_files(c, None)
        assert result == {}

    def test_read_head_files_empty_index_id(self):
        """Line 249: _read_head_files returns {} when branch_index_file_id is ''."""
        from unittest.mock import patch, MagicMock
        from sgit_ai.core.Vault__Components import Vault__Components
        diff = _make_diff()
        c    = Vault__Components()  # branch_index_file_id defaults to ''
        fake_config = MagicMock()
        fake_config.my_branch_id = 'br-test'
        with patch.object(diff, '_read_local_config', return_value=fake_config):
            result = diff._read_head_files(c)
        assert result == {}

    def test_read_head_files_no_branch_meta(self):
        """Line 253: _read_head_files returns {} when branch_meta is None."""
        from unittest.mock import patch, MagicMock
        from sgit_ai.core.Vault__Components     import Vault__Components
        from sgit_ai.storage.Vault__Branch_Manager import Vault__Branch_Manager
        diff = _make_diff()
        c    = Vault__Components(branch_index_file_id='some-index-id')
        fake_config = MagicMock()
        fake_config.my_branch_id = 'br-test'
        with patch.object(diff, '_read_local_config', return_value=fake_config), \
             patch.object(Vault__Branch_Manager, 'load_branch_index', return_value=MagicMock()), \
             patch.object(Vault__Branch_Manager, 'get_branch_by_id',  return_value=None):
            result = diff._read_head_files(c)
        assert result == {}

    def test_read_head_files_no_commit_id(self):
        """Line 258: _read_head_files returns {} when ref returns None."""
        from unittest.mock import patch, MagicMock
        from sgit_ai.core.Vault__Components     import Vault__Components
        from sgit_ai.storage.Vault__Branch_Manager import Vault__Branch_Manager
        from sgit_ai.storage.Vault__Ref_Manager import Vault__Ref_Manager
        diff      = _make_diff()
        fake_meta = MagicMock()
        fake_meta.head_ref_id = 'some-ref-id'
        fake_config = MagicMock()
        fake_config.my_branch_id = 'br-test'
        c = Vault__Components(branch_index_file_id='some-index-id')
        with patch.object(diff, '_read_local_config', return_value=fake_config), \
             patch.object(Vault__Branch_Manager, 'load_branch_index', return_value=MagicMock()), \
             patch.object(Vault__Branch_Manager, 'get_branch_by_id',  return_value=fake_meta), \
             patch.object(Vault__Ref_Manager,    'read_ref',           return_value=None):
            result = diff._read_head_files(c)
        assert result == {}

    def test_read_named_branch_files_empty_index_id(self):
        """Line 270: _read_named_branch_files returns {} when branch_index_file_id is ''."""
        from sgit_ai.core.Vault__Components import Vault__Components
        diff   = _make_diff()
        c      = Vault__Components()
        result = diff._read_named_branch_files(c, '/tmp/fake')
        assert result == {}

    def test_read_named_branch_files_no_named_meta(self):
        """Line 274: _read_named_branch_files returns {} when named_meta is None."""
        from unittest.mock import patch, MagicMock
        from sgit_ai.core.Vault__Components  import Vault__Components
        from sgit_ai.storage.Vault__Branch_Manager import Vault__Branch_Manager
        diff = _make_diff()
        c    = Vault__Components(branch_index_file_id='some-index-id')
        with patch.object(Vault__Branch_Manager, 'load_branch_index',  return_value=MagicMock()), \
             patch.object(Vault__Branch_Manager, 'get_branch_by_name', return_value=None):
            result = diff._read_named_branch_files(c, '/tmp/fake')
        assert result == {}

    def test_read_named_branch_files_no_commit_id(self):
        """Line 279: _read_named_branch_files returns {} when ref returns None."""
        from unittest.mock import patch, MagicMock
        from sgit_ai.core.Vault__Components  import Vault__Components
        from sgit_ai.storage.Vault__Branch_Manager import Vault__Branch_Manager
        from sgit_ai.storage.Vault__Ref_Manager  import Vault__Ref_Manager
        diff      = _make_diff()
        fake_meta = MagicMock()
        fake_meta.head_ref_id = 'some-ref-id'
        c = Vault__Components(branch_index_file_id='some-index-id')
        with patch.object(Vault__Branch_Manager, 'load_branch_index',  return_value=MagicMock()), \
             patch.object(Vault__Branch_Manager, 'get_branch_by_name', return_value=fake_meta), \
             patch.object(Vault__Ref_Manager,    'read_ref',           return_value=None):
            result = diff._read_named_branch_files(c, '/tmp/fake')
        assert result == {}

    def test_flatten_commit_skips_entry_without_blob_id(self):
        """Line 227: _flatten_commit skips tree entries with no blob_id."""
        from unittest.mock import patch, MagicMock
        from sgit_ai.core.Vault__Components import Vault__Components
        from sgit_ai.storage.Vault__Sub_Tree    import Vault__Sub_Tree
        from sgit_ai.storage.Vault__Commit   import Vault__Commit
        diff = _make_diff()
        c    = Vault__Components(read_key=b'\x00' * 32)
        fake_commit = MagicMock()
        fake_commit.tree_id = 'fake-tree-id'
        flat_map = {'no_blob.txt': {'size': 10}}  # no 'blob_id' key
        with patch.object(Vault__Commit,   'load_commit', return_value=fake_commit), \
             patch.object(Vault__Sub_Tree, 'flatten',     return_value=flat_map):
            result = diff._flatten_commit(c, 'fake-commit-id')
        assert result == {}
