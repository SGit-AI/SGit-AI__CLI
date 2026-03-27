import os
import shutil
import tempfile

import pytest

from sgit_ai.api.Vault__API__In_Memory   import Vault__API__In_Memory
from sgit_ai.crypto.Vault__Crypto        import Vault__Crypto
from sgit_ai.sync.Vault__Revert          import Vault__Revert
from sgit_ai.sync.Vault__Sync            import Vault__Sync


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_revert() -> Vault__Revert:
    return Vault__Revert(crypto=Vault__Crypto())


class _VaultFixture:
    """Thin helper: sets up a real temp vault with Vault__Sync."""

    def __init__(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.crypto  = Vault__Crypto()
        self.api     = Vault__API__In_Memory()
        self.api.setup()
        self.sync    = Vault__Sync(crypto=self.crypto, api=self.api)
        self.revert  = Vault__Revert(crypto=self.crypto)
        self.directory = os.path.join(self.tmp_dir, 'vault')
        self.sync.init(self.directory)

    def write(self, rel_path: str, content: str | bytes):
        full = os.path.join(self.directory, rel_path)
        os.makedirs(os.path.dirname(full), exist_ok=True) if os.path.dirname(full) else None
        mode = 'wb' if isinstance(content, bytes) else 'w'
        with open(full, mode) as fh:
            fh.write(content)

    def read(self, rel_path: str) -> bytes:
        full = os.path.join(self.directory, rel_path)
        with open(full, 'rb') as fh:
            return fh.read()

    def exists(self, rel_path: str) -> bool:
        return os.path.isfile(os.path.join(self.directory, rel_path))

    def commit(self, msg='test commit'):
        return self.sync.commit(self.directory, message=msg)

    def cleanup(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------

class Test_Vault__Revert:

    def setup_method(self):
        self.fix = _VaultFixture()

    def teardown_method(self):
        self.fix.cleanup()

    # ------------------------------------------------------------------
    # Revert single file to HEAD — modified file
    # ------------------------------------------------------------------

    def test_revert_single_file_restores_committed_content(self):
        fix = self.fix
        fix.write('hello.txt', 'committed content')
        fix.commit('add hello.txt')

        # Modify the file
        fix.write('hello.txt', 'modified content')
        assert fix.read('hello.txt') == b'modified content'

        result = fix.revert.revert_to_head(fix.directory, files=['hello.txt'])
        assert 'hello.txt' in result['restored']
        assert fix.read('hello.txt') == b'committed content'

    def test_revert_single_file_returns_correct_commit_id(self):
        fix = self.fix
        fix.write('data.txt', 'v1')
        commit_result = fix.commit('add data.txt')
        head_commit   = commit_result['commit_id']

        fix.write('data.txt', 'v2')
        result = fix.revert.revert_to_head(fix.directory, files=['data.txt'])
        assert result['commit_id'] == head_commit

    # ------------------------------------------------------------------
    # Revert all files to HEAD
    # ------------------------------------------------------------------

    def test_revert_all_files_to_head(self):
        fix = self.fix
        fix.write('a.txt', 'aaa')
        fix.write('b.txt', 'bbb')
        fix.commit('add a+b')

        fix.write('a.txt', 'modified a')
        fix.write('b.txt', 'modified b')

        result = fix.revert.revert_all_to_head(fix.directory)
        assert 'a.txt' in result['restored']
        assert 'b.txt' in result['restored']
        assert fix.read('a.txt') == b'aaa'
        assert fix.read('b.txt') == b'bbb'

    def test_revert_all_deletes_count(self):
        fix = self.fix
        fix.write('keep.txt', 'keep')
        fix.commit('add keep.txt')

        fix.write('keep.txt', 'changed')
        result = fix.revert.revert_all_to_head(fix.directory)
        assert len(result['restored']) >= 1
        assert fix.read('keep.txt') == b'keep'

    # ------------------------------------------------------------------
    # Revert file that was added (not in HEAD) — should delete it
    # ------------------------------------------------------------------

    def test_revert_added_file_deletes_it(self):
        fix = self.fix
        fix.write('existing.txt', 'base')
        fix.commit('add existing.txt')

        # Add new file without committing
        fix.write('newfile.txt', 'new content')
        assert fix.exists('newfile.txt')

        result = fix.revert.revert_all_to_head(fix.directory)
        assert 'newfile.txt' in result['deleted']
        assert not fix.exists('newfile.txt')

    def test_revert_added_file_single(self):
        fix = self.fix
        fix.write('base.txt', 'base')
        fix.commit('add base.txt')

        fix.write('extra.txt', 'extra')
        result = fix.revert.revert_to_head(fix.directory, files=['extra.txt'])
        assert 'extra.txt' in result['deleted']
        assert not fix.exists('extra.txt')

    # ------------------------------------------------------------------
    # Revert file that was deleted (was in HEAD) — should restore it
    # ------------------------------------------------------------------

    def test_revert_deleted_file_restores_it(self):
        fix = self.fix
        fix.write('important.txt', 'important data')
        fix.commit('add important.txt')

        # Delete file from working copy
        os.remove(os.path.join(fix.directory, 'important.txt'))
        assert not fix.exists('important.txt')

        result = fix.revert.revert_all_to_head(fix.directory)
        assert 'important.txt' in result['restored']
        assert fix.exists('important.txt')
        assert fix.read('important.txt') == b'important data'

    def test_revert_deleted_file_single(self):
        fix = self.fix
        fix.write('gone.txt', 'was here')
        fix.commit('add gone.txt')

        os.remove(os.path.join(fix.directory, 'gone.txt'))
        result = fix.revert.revert_to_head(fix.directory, files=['gone.txt'])
        assert 'gone.txt' in result['restored']
        assert fix.read('gone.txt') == b'was here'

    # ------------------------------------------------------------------
    # Revert to specific commit ID (not HEAD)
    # ------------------------------------------------------------------

    def test_revert_to_specific_commit(self):
        fix = self.fix
        fix.write('file.txt', 'version 1')
        c1 = fix.commit('v1')['commit_id']

        fix.write('file.txt', 'version 2')
        fix.commit('v2')

        # Working copy is at v2; revert to c1
        result = fix.revert.revert_to_commit(fix.directory, c1)
        assert 'file.txt' in result['restored']
        assert fix.read('file.txt') == b'version 1'
        assert result['commit_id'] == c1

    def test_revert_to_specific_commit_removes_later_file(self):
        fix = self.fix
        fix.write('orig.txt', 'original')
        c1 = fix.commit('c1')['commit_id']

        # Add a new file in the second commit
        fix.write('later.txt', 'added later')
        fix.commit('c2')

        # Revert to c1 — later.txt should be deleted
        result = fix.revert.revert_to_commit(fix.directory, c1)
        assert 'later.txt' in result['deleted']
        assert not fix.exists('later.txt')
        assert fix.exists('orig.txt')

    # ------------------------------------------------------------------
    # Revert with no uncommitted changes — no-op (files still restored)
    # ------------------------------------------------------------------

    def test_revert_on_clean_vault_is_noop(self):
        fix = self.fix
        fix.write('clean.txt', 'clean content')
        fix.commit('clean commit')

        # No changes — revert should just restore same content
        result = fix.revert.revert_all_to_head(fix.directory)
        assert 'clean.txt' in result['restored']
        assert fix.read('clean.txt') == b'clean content'
        assert result['deleted'] == []

    # ------------------------------------------------------------------
    # Initial vault (no committed files) — nothing to revert
    # ------------------------------------------------------------------

    def test_revert_empty_vault_no_commits(self):
        """After init, vault has an empty root tree. Revert is safe and no-op."""
        fix    = self.fix
        result = fix.revert.revert_all_to_head(fix.directory)
        # Empty vault: commit_id should still be set (init commit), restored/deleted can be empty
        # This just must not raise
        assert isinstance(result, dict)
        assert 'restored' in result
        assert 'deleted' in result

    # ------------------------------------------------------------------
    # Nested directory support
    # ------------------------------------------------------------------

    def test_revert_nested_file(self):
        fix = self.fix
        fix.write('sub/dir/deep.txt', 'deep content')
        fix.commit('nested')

        fix.write('sub/dir/deep.txt', 'modified deep')
        result = fix.revert.revert_all_to_head(fix.directory)
        assert 'sub/dir/deep.txt' in result['restored']
        assert fix.read('sub/dir/deep.txt') == b'deep content'

    def test_revert_deleted_nested_dir_restored(self):
        fix = self.fix
        fix.write('nested/file.txt', 'nested file')
        fix.commit('nested file')

        shutil.rmtree(os.path.join(fix.directory, 'nested'))
        result = fix.revert.revert_all_to_head(fix.directory)
        assert 'nested/file.txt' in result['restored']
        assert fix.read('nested/file.txt') == b'nested file'

    # ------------------------------------------------------------------
    # files filter — only specified paths are processed
    # ------------------------------------------------------------------

    def test_revert_files_filter_only_targets_specified(self):
        fix = self.fix
        fix.write('a.txt', 'aaa')
        fix.write('b.txt', 'bbb')
        fix.commit('a and b')

        fix.write('a.txt', 'changed a')
        fix.write('b.txt', 'changed b')

        result = fix.revert.revert_to_head(fix.directory, files=['a.txt'])
        assert 'a.txt' in result['restored']
        assert 'b.txt' not in result['restored']
        assert fix.read('a.txt') == b'aaa'
        # b.txt was NOT reverted
        assert fix.read('b.txt') == b'changed b'
