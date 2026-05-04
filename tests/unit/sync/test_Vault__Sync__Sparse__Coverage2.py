"""Coverage tests for Vault__Sync__Sparse — batch 2.

Missing lines targeted:
  30:      _get_head_flat_map — both get_branch_by_id and get_branch_by_name return None
  74:      sparse_fetch — entry with empty blob_id → continue
  110-120: sparse_fetch — large file loop (presigned URL download)
  144:     sparse_cat — blob_id empty → RuntimeError
  149-152: sparse_cat — large file via presigned URL
"""
import os
import unittest.mock
from io import BytesIO

import pytest

from sgit_ai.api.Vault__API__In_Memory   import Vault__API__In_Memory
from sgit_ai.storage.Vault__Object_Store import Vault__Object_Store
from sgit_ai.storage.Vault__Branch_Manager  import Vault__Branch_Manager
from sgit_ai.storage.Vault__Storage         import SG_VAULT_DIR
from sgit_ai.sync.Vault__Sync            import Vault__Sync
from sgit_ai.sync.Vault__Sync__Sparse    import Vault__Sync__Sparse
from tests._helpers.vault_test_env       import Vault__Test_Env


class Test_Vault__Sync__Sparse__Coverage2:

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
        self.snap      = self._env.restore()
        self.vault     = self.snap.vault_dir
        self.sync      = self.snap.sync
        keys           = self.snap.crypto.derive_keys_from_vault_key(self.snap.vault_key)
        self.read_key  = keys['read_key_bytes']
        self.vault_id  = keys['vault_id']
        sg_dir         = os.path.join(self.vault, SG_VAULT_DIR)
        self.obj_store = Vault__Object_Store(vault_path=sg_dir, crypto=self.snap.crypto)
        self.sg_dir    = sg_dir

    def teardown_method(self):
        self.snap.cleanup()

    # ── Line 30: both branch lookups return None ───────────────────────────

    def test_get_head_flat_map_no_branch_returns_empty_line_30(self, monkeypatch):
        """Line 30: get_branch_by_id AND get_branch_by_name('current') both None → early {}."""
        monkeypatch.setattr(Vault__Branch_Manager, 'get_branch_by_id',   lambda *a: None)
        monkeypatch.setattr(Vault__Branch_Manager, 'get_branch_by_name', lambda *a: None)
        result = self.sync.sparse_fetch(self.vault)
        assert result == {'fetched': 0, 'already_local': 0, 'written': []}

    # ── Line 74: sparse_fetch entry with no blob_id ────────────────────────

    def test_sparse_fetch_entry_no_blob_id_skips_line_74(self, monkeypatch):
        """Line 74: entry with empty blob_id → continue (not added to entries)."""
        flat_with_empty = {'ghost.txt': {'blob_id': '', 'size': 0}}
        monkeypatch.setattr(
            Vault__Sync__Sparse, '_get_head_flat_map',
            lambda self_, d: (flat_with_empty, self.obj_store,
                              self.read_key, self.vault_id, self.sg_dir))
        result = self.sync.sparse_fetch(self.vault)
        assert result['fetched'] == 0

    # ── Lines 110-120: large file download via presigned URL ─────────────

    def test_sparse_fetch_large_file_presigned_url_lines_110_120(self, monkeypatch):
        """Lines 110-120: large=True entry → presigned_read_url called, urlopen used."""
        import sgit_ai.sync.Vault__Sync__Sparse as _mod

        fake_blob_id   = 'obj-cas-imm-largeblob1234'
        fake_encrypted = self.snap.crypto.encrypt(self.read_key, b'large file data')
        flat = {
            'large_file.bin': {
                'blob_id': fake_blob_id,
                'size':    3 * 1024 * 1024,
                'large':   True,
            }
        }

        monkeypatch.setattr(
            Vault__Sync__Sparse, '_get_head_flat_map',
            lambda self_, d: (flat, self.obj_store, self.read_key, self.vault_id, self.sg_dir))

        class _FakeAPI(Vault__API__In_Memory):
            def presigned_read_url(self, vault_id, fid):
                return {'url': 'http://fake-s3/blob'}
            def batch_read(self, vault_id, file_ids):
                return {}

        fake_api = _FakeAPI()
        fake_api.setup()

        def fake_urlopen(url):
            resp = unittest.mock.MagicMock()
            resp.__enter__ = lambda s: s
            resp.__exit__  = lambda s, *a: None
            resp.read      = lambda: fake_encrypted
            return resp

        sync = Vault__Sync(crypto=self.snap.crypto, api=fake_api)
        monkeypatch.setattr(_mod, 'urlopen', fake_urlopen)
        monkeypatch.setattr(Vault__Sync__Sparse, '_get_head_flat_map',
                            lambda self_, d: (flat, self.obj_store, self.read_key,
                                              self.vault_id, self.sg_dir))

        result = sync.sparse_fetch(self.vault)
        assert isinstance(result, dict)

    # ── Line 144: sparse_cat with empty blob_id ───────────────────────────

    def test_sparse_cat_empty_blob_id_raises_line_144(self, monkeypatch):
        """Line 144: entry exists but blob_id is empty → RuntimeError."""
        flat = {'empty.txt': {'blob_id': '', 'size': 0, 'large': False}}

        monkeypatch.setattr(
            Vault__Sync__Sparse, '_get_head_flat_map',
            lambda self_, d: (flat, self.obj_store, self.read_key, self.vault_id, self.sg_dir))

        with pytest.raises(RuntimeError, match='No blob stored'):
            self.sync.sparse_cat(self.vault, 'empty.txt')

    # ── Lines 149-152: sparse_cat large file presigned URL ───────────────

    def test_sparse_cat_large_file_presigned_url_lines_149_152(self, monkeypatch):
        """Lines 149-152: large=True entry not cached → presigned_read_url + urlopen."""
        import sgit_ai.sync.Vault__Sync__Sparse as _mod

        fake_blob_id   = 'obj-cas-imm-catlargeblob1'
        plaintext      = b'cat large content'
        fake_encrypted = self.snap.crypto.encrypt(self.read_key, plaintext)

        flat = {'big.bin': {'blob_id': fake_blob_id, 'size': 5 * 1024 * 1024, 'large': True}}

        class _FakeAPI(Vault__API__In_Memory):
            def presigned_read_url(self, vault_id, fid):
                return {'url': 'http://fake-s3/big-blob'}
            def read(self, vault_id, fid):
                return None

        fake_api = _FakeAPI()
        fake_api.setup()

        def fake_urlopen(url):
            resp = unittest.mock.MagicMock()
            resp.__enter__ = lambda s: s
            resp.__exit__  = lambda s, *a: None
            resp.read      = lambda: fake_encrypted
            return resp

        sync = Vault__Sync(crypto=self.snap.crypto, api=fake_api)
        monkeypatch.setattr(_mod, 'urlopen', fake_urlopen)
        monkeypatch.setattr(Vault__Sync__Sparse, '_get_head_flat_map',
                            lambda self_, d: (flat, self.obj_store, self.read_key,
                                              self.vault_id, self.sg_dir))

        result = sync.sparse_cat(self.vault, 'big.bin')
        assert result == plaintext


def _dummy_obj_store():
    """Minimal obj_store stub that always says objects don't exist."""
    class _Stub:
        def exists(self, bid): return False
        def load(self, bid):   raise RuntimeError('not found')
    return _Stub()
