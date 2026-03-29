import copy
import json
import os
import shutil
import tempfile
import time
import zipfile

import pytest

from sgit_ai.api.Vault__API__In_Memory   import Vault__API__In_Memory
from sgit_ai.crypto.Vault__Crypto        import Vault__Crypto
from sgit_ai.schemas.Schema__Stash_Meta  import Schema__Stash_Meta
from sgit_ai.sync.Vault__Stash           import Vault__Stash, STASH_PREFIX
from sgit_ai.sync.Vault__Sync            import Vault__Sync


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _VaultFixture:
    """Per-test fixture restored from a class-level snapshot."""

    def __init__(self, tmp_dir, vault_dir, crypto, api, sync):
        self.tmp_dir   = tmp_dir
        self.directory = vault_dir
        self.crypto    = crypto
        self.api       = api
        self.sync      = sync
        self.stash     = Vault__Stash(crypto=crypto)

    def write(self, rel_path: str, content: str | bytes):
        full = os.path.join(self.directory, rel_path)
        parent = os.path.dirname(full)
        if parent:
            os.makedirs(parent, exist_ok=True)
        mode = 'wb' if isinstance(content, bytes) else 'w'
        with open(full, mode) as fh:
            fh.write(content)

    def read(self, rel_path: str) -> bytes:
        with open(os.path.join(self.directory, rel_path), 'rb') as fh:
            return fh.read()

    def exists(self, rel_path: str) -> bool:
        return os.path.isfile(os.path.join(self.directory, rel_path))

    def commit(self, msg='test'):
        return self.sync.commit(self.directory, message=msg)

    def stash_dir(self) -> str:
        return os.path.join(self.directory, '.sg_vault', 'local', 'stash')

    def cleanup(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------

class Test_Vault__Stash:

    # ------------------------------------------------------------------ #
    # Class-level snapshot: init vault once, snapshot directory + API
    # ------------------------------------------------------------------ #
    _snapshot_dir   = None
    _snapshot_store = None
    _vault_sub      = 'vault'

    @classmethod
    def setup_class(cls):
        crypto = Vault__Crypto()
        api    = Vault__API__In_Memory()
        api.setup()
        sync   = Vault__Sync(crypto=crypto, api=api)

        snap_dir  = tempfile.mkdtemp()
        vault_dir = os.path.join(snap_dir, cls._vault_sub)
        sync.init(vault_dir)

        cls._snapshot_dir   = snap_dir
        cls._snapshot_store = copy.deepcopy(api._store)

    @classmethod
    def teardown_class(cls):
        if cls._snapshot_dir and os.path.isdir(cls._snapshot_dir):
            shutil.rmtree(cls._snapshot_dir, ignore_errors=True)

    def setup_method(self):
        self.tmp_dir  = tempfile.mkdtemp()

        # Copy snapshot vault directory
        src = os.path.join(self._snapshot_dir, self._vault_sub)
        dst = os.path.join(self.tmp_dir, self._vault_sub)
        shutil.copytree(src, dst)

        # Restore API
        api = Vault__API__In_Memory()
        api.setup()
        api._store = copy.deepcopy(self._snapshot_store)

        crypto = Vault__Crypto()
        sync   = Vault__Sync(crypto=crypto, api=api)

        self.fix = _VaultFixture(self.tmp_dir, dst, crypto, api, sync)

    def teardown_method(self):
        self.fix.cleanup()

    # ------------------------------------------------------------------
    # stash on clean vault — nothing to stash
    # ------------------------------------------------------------------

    def test_stash_clean_vault_nothing_to_stash(self):
        fix    = self.fix
        fix.write('file.txt', 'committed')
        fix.commit('add file')

        result = fix.stash.stash(fix.directory)
        assert result.get('nothing_to_stash') is True

    def test_stash_after_init_nothing_to_stash(self):
        fix    = self.fix
        result = fix.stash.stash(fix.directory)
        assert result.get('nothing_to_stash') is True

    # ------------------------------------------------------------------
    # stash with modified file — zip contains file, working copy reverted
    # ------------------------------------------------------------------

    def test_stash_modified_file_creates_zip(self):
        fix = self.fix
        fix.write('data.txt', 'original')
        fix.commit('add data.txt')

        fix.write('data.txt', 'modified')
        result = fix.stash.stash(fix.directory)

        assert result.get('nothing_to_stash') is False
        zip_path = result['stash_path']
        assert os.path.isfile(zip_path)

    def test_stash_modified_file_zip_contains_file(self):
        fix = self.fix
        fix.write('data.txt', 'original')
        fix.commit('add data.txt')

        fix.write('data.txt', 'modified')
        result   = fix.stash.stash(fix.directory)
        zip_path = result['stash_path']

        with zipfile.ZipFile(zip_path, 'r') as zf:
            names = zf.namelist()
        assert 'data.txt' in names

    def test_stash_reverts_working_copy_to_head(self):
        fix = self.fix
        fix.write('data.txt', 'original')
        fix.commit('add data.txt')

        fix.write('data.txt', 'modified')
        fix.stash.stash(fix.directory)

        # After stash, working copy should be back to 'original'
        assert fix.read('data.txt') == b'original'

    def test_stash_added_file_reverted_after_stash(self):
        fix = self.fix
        fix.write('base.txt', 'base')
        fix.commit('base')

        fix.write('new.txt', 'new content')
        assert fix.exists('new.txt')

        fix.stash.stash(fix.directory)
        assert not fix.exists('new.txt')

    # ------------------------------------------------------------------
    # stash pop — restores file content
    # ------------------------------------------------------------------

    def test_stash_pop_restores_file(self):
        fix = self.fix
        fix.write('msg.txt', 'original')
        fix.commit('add msg.txt')

        fix.write('msg.txt', 'stashed content')
        fix.stash.stash(fix.directory)

        # Working copy now at 'original'
        assert fix.read('msg.txt') == b'original'

        pop_result = fix.stash.pop(fix.directory)
        assert pop_result.get('no_stash') is False
        assert 'msg.txt' in pop_result['restored']
        assert fix.read('msg.txt') == b'stashed content'

    def test_stash_pop_no_stash(self):
        fix    = self.fix
        result = fix.stash.pop(fix.directory)
        assert result.get('no_stash') is True

    # ------------------------------------------------------------------
    # stash pop round-trip — content identical after stash + pop
    # ------------------------------------------------------------------

    def test_stash_pop_round_trip_single_file(self):
        fix = self.fix
        fix.write('round.txt', 'base')
        fix.commit('base')

        modified_content = 'round-trip content after modification'
        fix.write('round.txt', modified_content)
        fix.stash.stash(fix.directory)
        fix.stash.pop(fix.directory)

        assert fix.read('round.txt') == modified_content.encode()

    def test_stash_pop_round_trip_multiple_files(self):
        fix = self.fix
        fix.write('a.txt', 'aaa')
        fix.write('b.txt', 'bbb')
        fix.commit('two files')

        fix.write('a.txt', 'AAA modified')
        fix.write('b.txt', 'BBB modified')
        fix.stash.stash(fix.directory)
        fix.stash.pop(fix.directory)

        assert fix.read('a.txt') == b'AAA modified'
        assert fix.read('b.txt') == b'BBB modified'

    def test_stash_pop_round_trip_added_file(self):
        fix = self.fix
        fix.write('base.txt', 'base')
        fix.commit('base')

        fix.write('added.txt', 'brand new file content')
        fix.stash.stash(fix.directory)
        assert not fix.exists('added.txt')

        fix.stash.pop(fix.directory)
        assert fix.exists('added.txt')
        assert fix.read('added.txt') == b'brand new file content'

    # ------------------------------------------------------------------
    # stash creates file in .sg_vault/local/stash/
    # ------------------------------------------------------------------

    def test_stash_zip_in_sg_vault_local_stash(self):
        fix = self.fix
        fix.write('f.txt', 'v1')
        fix.commit('c1')
        fix.write('f.txt', 'v2')

        result   = fix.stash.stash(fix.directory)
        zip_path = result['stash_path']
        assert fix.stash_dir() in zip_path
        assert STASH_PREFIX in os.path.basename(zip_path)
        assert zip_path.endswith('.zip')

    def test_stash_meta_file_created_alongside_zip(self):
        fix = self.fix
        fix.write('f.txt', 'v1')
        fix.commit('c1')
        fix.write('f.txt', 'v2')

        result   = fix.stash.stash(fix.directory)
        zip_path = result['stash_path']
        # Meta file should be named stash-{ts}.stash-meta.json
        meta_path = zip_path.replace('.zip', '.stash-meta.json')
        assert os.path.isfile(meta_path)

    def test_stash_meta_content_valid(self):
        fix = self.fix
        fix.write('f.txt', 'v1')
        fix.commit('c1')
        fix.write('f.txt', 'v2')

        result    = fix.stash.stash(fix.directory)
        meta      = result['meta']
        assert isinstance(meta, Schema__Stash_Meta)
        assert 'f.txt' in meta.files_modified

    # ------------------------------------------------------------------
    # stash pop removes stash file
    # ------------------------------------------------------------------

    def test_stash_pop_removes_zip(self):
        fix = self.fix
        fix.write('f.txt', 'v1')
        fix.commit('c1')
        fix.write('f.txt', 'v2')

        result   = fix.stash.stash(fix.directory)
        zip_path = result['stash_path']
        assert os.path.isfile(zip_path)

        fix.stash.pop(fix.directory)
        assert not os.path.isfile(zip_path)

    def test_stash_pop_removes_meta_file(self):
        fix = self.fix
        fix.write('f.txt', 'v1')
        fix.commit('c1')
        fix.write('f.txt', 'v2')

        result    = fix.stash.stash(fix.directory)
        zip_path  = result['stash_path']
        meta_path = zip_path.replace('.zip', '.stash-meta.json')

        fix.stash.pop(fix.directory)
        assert not os.path.isfile(meta_path)

    # ------------------------------------------------------------------
    # stash list — returns list of stash entries
    # ------------------------------------------------------------------

    def test_stash_list_empty(self):
        fix     = self.fix
        entries = fix.stash.list_stashes(fix.directory)
        assert entries == []

    def test_stash_list_single_entry(self):
        fix = self.fix
        fix.write('f.txt', 'v1')
        fix.commit('c1')
        fix.write('f.txt', 'v2')
        fix.stash.stash(fix.directory)

        entries = fix.stash.list_stashes(fix.directory)
        assert len(entries) == 1
        assert 'zip_path' in entries[0]
        assert 'meta'     in entries[0]
        assert 'timestamp' in entries[0]

    def test_stash_list_multiple_entries_newest_first(self):
        fix = self.fix
        fix.write('f.txt', 'v1')
        fix.commit('c1')

        fix.write('f.txt', 'v2')
        fix.stash.stash(fix.directory)

        fix.write('f.txt', 'v3')
        fix.stash.stash(fix.directory)

        entries = fix.stash.list_stashes(fix.directory)
        assert len(entries) == 2
        # Newest first
        assert entries[0]['timestamp'] >= entries[1]['timestamp']

    def test_stash_list_after_pop_is_empty(self):
        fix = self.fix
        fix.write('f.txt', 'v1')
        fix.commit('c1')
        fix.write('f.txt', 'v2')
        fix.stash.stash(fix.directory)
        fix.stash.pop(fix.directory)

        entries = fix.stash.list_stashes(fix.directory)
        assert entries == []

    # ------------------------------------------------------------------
    # stash drop — removes stash without applying
    # ------------------------------------------------------------------

    def test_stash_drop_removes_zip_without_applying(self):
        fix = self.fix
        fix.write('f.txt', 'v1')
        fix.commit('c1')
        fix.write('f.txt', 'v2')
        fix.stash.stash(fix.directory)

        # After stash, working copy is 'v1'
        assert fix.read('f.txt') == b'v1'

        fix.stash.drop(fix.directory)

        # Stash list is now empty
        assert fix.stash.list_stashes(fix.directory) == []
        # Working copy still at 'v1' (drop did NOT apply)
        assert fix.read('f.txt') == b'v1'

    def test_stash_drop_no_stash(self):
        fix    = self.fix
        result = fix.stash.drop(fix.directory)
        assert result.get('no_stash') is True

    def test_stash_drop_returns_dropped_path(self):
        fix = self.fix
        fix.write('f.txt', 'v1')
        fix.commit('c1')
        fix.write('f.txt', 'v2')

        stash_result = fix.stash.stash(fix.directory)
        drop_result  = fix.stash.drop(fix.directory)
        assert drop_result.get('no_stash') is False
        assert 'dropped_path' in drop_result

    # ------------------------------------------------------------------
    # meta base_commit is set to HEAD commit id
    # ------------------------------------------------------------------

    def test_stash_meta_base_commit_set(self):
        fix = self.fix
        fix.write('f.txt', 'v1')
        commit_result = fix.commit('c1')
        head_cid      = commit_result['commit_id']

        fix.write('f.txt', 'v2')
        result = fix.stash.stash(fix.directory)
        meta   = result['meta']

        assert str(meta.base_commit) == head_cid

    # ------------------------------------------------------------------
    # stash with deleted file noted in meta
    # ------------------------------------------------------------------

    def test_stash_deleted_file_in_meta(self):
        fix = self.fix
        fix.write('gone.txt', 'to be deleted')
        fix.write('keep.txt', 'stays')
        fix.commit('two files')

        os.remove(os.path.join(fix.directory, 'gone.txt'))

        result = fix.stash.stash(fix.directory)
        meta   = result['meta']
        assert 'gone.txt' in meta.files_deleted

    def test_stash_status_counts_correct(self):
        fix = self.fix
        fix.write('modified.txt', 'original')
        fix.write('deleted.txt',  'will be deleted')
        fix.commit('setup')

        fix.write('modified.txt', 'changed')
        fix.write('added.txt',    'brand new')
        os.remove(os.path.join(fix.directory, 'deleted.txt'))

        result = fix.stash.stash(fix.directory)
        status = result['status']
        assert 'modified.txt' in status['modified']
        assert 'added.txt'    in status['added']
        assert 'deleted.txt'  in status['deleted']
