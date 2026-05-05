"""Tests for Vault__Sync__Sparse — sparse_ls, sparse_fetch, sparse_cat.

Uses a class-level snapshot (push already done so API has all objects).
Per-test restore gives an isolated vault copy with a fresh API instance.
"""
import os
import shutil

import pytest

from sgit_ai.crypto.Vault__Crypto      import Vault__Crypto
from sgit_ai.core.actions.sparse.Vault__Sync__Sparse  import Vault__Sync__Sparse
from sgit_ai.storage.Vault__Storage       import SG_VAULT_DIR
from tests._helpers.vault_test_env     import Vault__Test_Env


class Test_Vault__Sync__Sparse__Ls:

    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_single_vault(files={
            'readme.md':      'hello world',
            'docs/guide.txt': 'guide content',
            'docs/api.txt':   'api content',
        })

    @classmethod
    def teardown_class(cls):
        if cls._env:
            cls._env.cleanup_snapshot()

    def setup_method(self):
        self.env    = self._env.restore()
        self.sparse = Vault__Sync__Sparse(crypto=self.env.crypto, api=self.env.api)

    def teardown_method(self):
        self.env.cleanup()

    def test_sparse_ls_returns_all_entries(self):
        entries = self.sparse.sparse_ls(self.env.vault_dir)
        paths = [e['path'] for e in entries]
        assert 'readme.md'      in paths
        assert 'docs/guide.txt' in paths
        assert 'docs/api.txt'   in paths

    def test_sparse_ls_entry_fields(self):
        entries = self.sparse.sparse_ls(self.env.vault_dir)
        entry   = next(e for e in entries if e['path'] == 'readme.md')
        assert 'path'    in entry
        assert 'size'    in entry
        assert 'blob_id' in entry
        assert 'fetched' in entry
        assert 'large'   in entry

    def test_sparse_ls_fetched_true_for_local_blobs(self):
        entries  = self.sparse.sparse_ls(self.env.vault_dir)
        # All blobs should be local (vault was freshly restored from snapshot)
        assert all(e['fetched'] for e in entries if e['blob_id'])

    def test_sparse_ls_with_path_prefix_filters_results(self):
        """Line 50: path filter — skip entries that don't match prefix."""
        entries = self.sparse.sparse_ls(self.env.vault_dir, path='docs')
        paths   = [e['path'] for e in entries]
        assert 'docs/guide.txt' in paths
        assert 'docs/api.txt'   in paths
        assert 'readme.md'      not in paths

    def test_sparse_ls_exact_path_match(self):
        entries = self.sparse.sparse_ls(self.env.vault_dir, path='readme.md')
        assert len(entries) == 1
        assert entries[0]['path'] == 'readme.md'

    def test_sparse_ls_empty_result_for_unknown_path(self):
        entries = self.sparse.sparse_ls(self.env.vault_dir, path='nonexistent/')
        assert entries == []

    def test_sparse_ls_fetched_false_after_blob_deleted(self):
        """Blob deleted locally → fetched=False."""
        entries  = self.sparse.sparse_ls(self.env.vault_dir)
        readme   = next(e for e in entries if e['path'] == 'readme.md')
        blob_id  = readme['blob_id']
        blob_path = os.path.join(self.env.vault_dir, SG_VAULT_DIR, 'bare', 'data', blob_id)
        os.remove(blob_path)
        entries_after = self.sparse.sparse_ls(self.env.vault_dir)
        readme_after  = next(e for e in entries_after if e['path'] == 'readme.md')
        assert readme_after['fetched'] is False


class Test_Vault__Sync__Sparse__Fetch:

    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_single_vault(files={
            'file1.txt': 'content one',
            'file2.txt': 'content two',
            'sub/file3.txt': 'content three',
        })

    @classmethod
    def teardown_class(cls):
        if cls._env:
            cls._env.cleanup_snapshot()

    def setup_method(self):
        self.env    = self._env.restore()
        self.sparse = Vault__Sync__Sparse(crypto=self.env.crypto, api=self.env.api)
        # Remove all local blob data so sparse_fetch has to download
        self._remove_local_blobs()

    def teardown_method(self):
        self.env.cleanup()

    def _remove_local_blobs(self):
        """Delete local blob objects so sparse_fetch must re-download from API."""
        data_dir = os.path.join(self.env.vault_dir, SG_VAULT_DIR, 'bare', 'data')
        if os.path.isdir(data_dir):
            # Keep only commit and tree objects (they're referenced but not blobs)
            # We can't easily distinguish, so delete all and let fetch restore blobs
            entries = self.sparse.sparse_ls(self.env.vault_dir)
            for entry in entries:
                blob_path = os.path.join(data_dir, entry['blob_id'])
                if os.path.isfile(blob_path):
                    os.remove(blob_path)

    def test_sparse_fetch_all_downloads_blobs(self):
        """Lines 64-133: fetch all missing blobs from API."""
        result = self.sparse.sparse_fetch(self.env.vault_dir)
        assert result['fetched'] >= 0
        assert isinstance(result['written'], list)

    def test_sparse_fetch_writes_files_to_disk(self):
        result = self.sparse.sparse_fetch(self.env.vault_dir)
        assert len(result['written']) > 0
        # Check that the written files actually exist
        for rel_path in result['written']:
            full = os.path.join(self.env.vault_dir, rel_path)
            assert os.path.isfile(full), f'{rel_path} not written'

    def test_sparse_fetch_already_local_counted(self):
        """Fetch once, fetch again — second time all are already_local."""
        self.sparse.sparse_fetch(self.env.vault_dir)   # first: download
        result2 = self.sparse.sparse_fetch(self.env.vault_dir)  # second: already local
        assert result2['already_local'] > 0
        assert result2['fetched'] == 0

    def test_sparse_fetch_with_path_filter(self):
        """Path-filtered fetch only downloads blobs matching the prefix."""
        result = self.sparse.sparse_fetch(self.env.vault_dir, path='sub')
        written = result['written']
        assert all(p.startswith('sub') for p in written)

    def test_sparse_fetch_with_progress_callback(self):
        """on_progress callback is called during fetch."""
        events = []
        def _on_progress(stage, message, detail=None):
            events.append(stage)

        self.sparse.sparse_fetch(self.env.vault_dir, on_progress=_on_progress)
        assert 'download' in events

    def test_sparse_fetch_empty_when_no_entries_match_path(self):
        result = self.sparse.sparse_fetch(self.env.vault_dir, path='nonexistent/')
        assert result == dict(fetched=0, already_local=0, written=[])

    def test_sparse_fetch_empty_vault_returns_empty(self):
        """When vault HEAD has no files, sparse_fetch returns empty."""
        from sgit_ai.network.api.Vault__API__In_Memory import Vault__API__In_Memory
        from sgit_ai.core.Vault__Sync          import Vault__Sync
        import tempfile
        tmp = tempfile.mkdtemp()
        try:
            crypto = Vault__Crypto()
            api    = Vault__API__In_Memory()
            api.setup()
            sync   = Vault__Sync(crypto=crypto, api=api)
            sync.init(tmp)
            sync.push(tmp)
            sparse = Vault__Sync__Sparse(crypto=crypto, api=api)
            result = sparse.sparse_fetch(tmp)
            assert result == dict(fetched=0, already_local=0, written=[])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class Test_Vault__Sync__Sparse__Cat:

    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_single_vault(files={
            'hello.txt': 'Hello, sparse world!',
            'data.bin':  b'\x00\x01\x02\x03',
        })

    @classmethod
    def teardown_class(cls):
        if cls._env:
            cls._env.cleanup_snapshot()

    def setup_method(self):
        self.env    = self._env.restore()
        self.sparse = Vault__Sync__Sparse(crypto=self.env.crypto, api=self.env.api)

    def teardown_method(self):
        self.env.cleanup()

    def test_sparse_cat_reads_text_file(self):
        """Lines 137-165: cat a locally cached file."""
        content = self.sparse.sparse_cat(self.env.vault_dir, 'hello.txt')
        assert content == b'Hello, sparse world!'

    def test_sparse_cat_reads_binary_file(self):
        content = self.sparse.sparse_cat(self.env.vault_dir, 'data.bin')
        assert content == b'\x00\x01\x02\x03'

    def test_sparse_cat_fetches_from_api_when_missing(self):
        """Lines 146-159: blob not local → fetches from API → returns content."""
        entries  = self.sparse.sparse_ls(self.env.vault_dir)
        hello    = next(e for e in entries if e['path'] == 'hello.txt')
        blob_path = os.path.join(self.env.vault_dir, SG_VAULT_DIR, 'bare', 'data', hello['blob_id'])
        os.remove(blob_path)

        content = self.sparse.sparse_cat(self.env.vault_dir, 'hello.txt')
        assert content == b'Hello, sparse world!'

    def test_sparse_cat_raises_for_nonexistent_path(self):
        """Line 140: file not in vault → RuntimeError."""
        with pytest.raises(RuntimeError, match='File not found in vault'):
            self.sparse.sparse_cat(self.env.vault_dir, 'nonexistent.txt')

    def test_sparse_cat_raises_when_fetch_fails(self):
        """Line 162: API can't provide the blob → RuntimeError."""
        from sgit_ai.network.api.Vault__API__In_Memory import Vault__API__In_Memory

        class EmptyAPI(Vault__API__In_Memory):
            def read(self, vault_id, path, **kwargs):
                return None   # simulate missing object on server

        entries  = self.sparse.sparse_ls(self.env.vault_dir)
        hello    = next(e for e in entries if e['path'] == 'hello.txt')
        blob_path = os.path.join(self.env.vault_dir, SG_VAULT_DIR, 'bare', 'data', hello['blob_id'])
        os.remove(blob_path)

        empty_api    = EmptyAPI()
        empty_api.setup()
        broken_sparse = Vault__Sync__Sparse(crypto=self.env.crypto, api=empty_api)
        with pytest.raises(RuntimeError, match='Failed to fetch'):
            broken_sparse.sparse_cat(self.env.vault_dir, 'hello.txt')


class Test_Vault__Sync__Sparse__Edge_Cases:
    """Tests for _get_head_flat_map edge cases: lines 28-30, 34."""

    def test_get_head_flat_map__empty_vault_returns_empty_dict(self):
        """Lines 33-34: vault with no committed files → commit_id is an init commit."""
        from sgit_ai.network.api.Vault__API__In_Memory import Vault__API__In_Memory
        from sgit_ai.core.Vault__Sync          import Vault__Sync
        import tempfile
        tmp = tempfile.mkdtemp()
        try:
            crypto = Vault__Crypto()
            api    = Vault__API__In_Memory()
            api.setup()
            sync   = Vault__Sync(crypto=crypto, api=api)
            sync.init(tmp)
            sparse = Vault__Sync__Sparse(crypto=crypto, api=api)
            result = sparse.sparse_ls(tmp)
            assert result == []   # empty vault has no file entries
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_get_head_flat_map__no_commit_id_when_branch_missing(self):
        """Lines 28-30: branch_id points to nonexistent branch → empty result."""
        import json as _json
        from sgit_ai.network.api.Vault__API__In_Memory import Vault__API__In_Memory
        from sgit_ai.core.Vault__Sync          import Vault__Sync
        import tempfile
        tmp = tempfile.mkdtemp()
        try:
            crypto = Vault__Crypto()
            api    = Vault__API__In_Memory()
            api.setup()
            sync   = Vault__Sync(crypto=crypto, api=api)
            sync.init(tmp)
            # Overwrite config to reference a nonexistent branch
            config_path = os.path.join(tmp, SG_VAULT_DIR, 'local', 'config.json')
            with open(config_path, 'w') as f:
                _json.dump({
                    'my_branch_id': 'branch-clone-0000000000000000',
                    'mode': None, 'edit_token': None, 'sparse': False
                }, f)
            sparse = Vault__Sync__Sparse(crypto=crypto, api=api)
            result = sparse.sparse_ls(tmp)
            assert result == []
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
