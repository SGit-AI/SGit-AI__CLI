import hashlib
import os
import shutil
import tempfile

import pytest

from sgit_ai.crypto.Vault__Crypto        import Vault__Crypto
from sgit_ai.schemas.Schema__Diff_File   import Schema__Diff_File
from sgit_ai.schemas.Schema__Diff_Result import Schema__Diff_Result
from sgit_ai.sync.Vault__Diff            import Vault__Diff, BINARY_CHECK_BYTES
from tests.unit.sync.vault_test_env      import Vault__Test_Env


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
    #
    # These three tests share a single class-level vault snapshot to avoid
    # three separate sync.init() calls (~400 ms each).

    _diff_env     = None   # Vault__Test_Env with 'hello.txt' already committed

    @classmethod
    def setup_class(cls):
        cls._diff_env = Vault__Test_Env()
        cls._diff_env.setup_single_vault(files={'hello.txt': 'Hello, world!\n',
                                                 'file.txt':  'content\n',
                                                 'todelete.txt': 'will be deleted\n'})

    def test_diff_vs_head_with_real_vault(self):
        """Create a real vault, commit a file, modify it, then diff."""
        env = self._diff_env.restore()
        try:
            vault_dir = env.vault_dir

            # Modify an existing committed file
            with open(os.path.join(vault_dir, 'hello.txt'), 'w') as f:
                f.write('Hello, world!\nNew line!\n')

            # Add a new file
            with open(os.path.join(vault_dir, 'new.txt'), 'w') as f:
                f.write('brand new\n')

            diff_engine = Vault__Diff(crypto=env.crypto)
            result      = diff_engine.diff_vs_head(vault_dir)

            by_path = {str(f.path): f for f in result.files}
            assert by_path['hello.txt'].status == 'modified'
            assert by_path['new.txt'].status   == 'added'
            assert int(result.modified_count)  >= 1
            assert int(result.added_count)     >= 1
        finally:
            env.cleanup()

    def test_diff_vs_head_clean_vault(self):
        """Vault with no working changes should show no diffs."""
        env = self._diff_env.restore()
        try:
            vault_dir   = env.vault_dir
            diff_engine = Vault__Diff(crypto=env.crypto)
            result      = diff_engine.diff_vs_head(vault_dir)

            assert int(result.added_count)    == 0
            assert int(result.modified_count) == 0
            assert int(result.deleted_count)  == 0
        finally:
            env.cleanup()

    def test_diff_vs_head_deleted_file(self):
        """Delete a committed file and confirm it shows as deleted."""
        env = self._diff_env.restore()
        try:
            vault_dir = env.vault_dir
            os.remove(os.path.join(vault_dir, 'todelete.txt'))

            diff_engine = Vault__Diff(crypto=env.crypto)
            result      = diff_engine.diff_vs_head(vault_dir)

            assert int(result.deleted_count) >= 1
            deleted = [f for f in result.files if f.status == 'deleted']
            assert any(str(f.path) == 'todelete.txt' for f in deleted)
        finally:
            env.cleanup()
