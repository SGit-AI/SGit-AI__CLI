"""Coverage-focused tests for Vault__Batch missing lines.

Targets:
  - Lines 55-57: _upload_large returns True → large_uploaded++, continue
  - Lines 113-115: presigned_initiate success path
  - Lines 119-149: single-part + multi-part upload loop
  - Lines 154-159: exception in upload → cancel + re-raise
  - Line 165: _collect_tree_objects skips already-visited tree
  - Line 180: recursive sub-tree collection
  - Lines 229-230: execute_batch single plain chunk (oversized)
  - Line 233: execute_batch CAS chunk loop
"""
import base64
import json
import os
import shutil
import tempfile
import types
from unittest.mock import patch, MagicMock

import pytest

from sgit_ai.network.api.Vault__API            import LARGE_BLOB_THRESHOLD
from sgit_ai.network.api.Vault__API__In_Memory import Vault__API__In_Memory
from sgit_ai.crypto.Vault__Crypto      import Vault__Crypto
from sgit_ai.storage.Vault__Object_Store import Vault__Object_Store
from sgit_ai.storage.Vault__Ref_Manager  import Vault__Ref_Manager
from sgit_ai.safe_types.Enum__Batch_Op   import Enum__Batch_Op
from sgit_ai.core.actions.push.Vault__Batch          import Vault__Batch, LARGE_PART_SIZE
from sgit_ai.core.Vault__Sync           import Vault__Sync
from tests.unit.sync.vault_test_env      import Vault__Test_Env


def _make_batch(api=None):
    crypto = Vault__Crypto()
    if api is None:
        api = Vault__API__In_Memory()
        api.setup()
    return Vault__Batch(crypto=crypto, api=api), crypto, api


# ---------------------------------------------------------------------------
# Lines 55-57: _upload_large returns True → large_uploaded++, continue
# ---------------------------------------------------------------------------

class Test_Vault__Batch__LargeUploaded:

    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_single_vault(files={'init.txt': 'init'})

    @classmethod
    def teardown_class(cls):
        if cls._env:
            cls._env.cleanup_snapshot()

    def setup_method(self):
        self.snap   = self._env.restore()
        self.vault  = self.snap.vault_dir
        self.sync   = self.snap.sync
        self.crypto = self.snap.crypto
        self.api    = self.snap.api

    def teardown_method(self):
        self.snap.cleanup()

    def test_build_push_operations_large_blob_increments_counter(self):
        """Lines 55-57: _upload_large True → blob counted as large_uploaded."""
        # Add a large file
        with open(os.path.join(self.vault, 'big.bin'), 'wb') as f:
            f.write(b'B' * (LARGE_BLOB_THRESHOLD + 1))
        self.sync.commit(self.vault, message='add big')

        c    = self.sync._init_components(self.vault)
        batch = Vault__Batch(crypto=self.crypto, api=self.api)

        # Patch _upload_large to return True (pretend presigned upload succeeded)
        with patch.object(batch, '_upload_large', return_value=True) as mock_upload:
            from sgit_ai.core.actions.fetch.Vault__Fetch import Vault__Fetch
            from sgit_ai.storage.Vault__Commit import Vault__Commit
            from sgit_ai.crypto.PKI__Crypto import PKI__Crypto
            fetcher = Vault__Fetch(crypto=self.crypto)
            pki     = PKI__Crypto()
            vc      = Vault__Commit(crypto=self.crypto, pki=pki,
                                     object_store=c.obj_store,
                                     ref_manager=c.ref_manager)

            local_cfg  = self.sync._read_local_config(self.vault, c.storage)
            branch_idx = c.branch_manager.load_branch_index(
                self.vault, c.branch_index_file_id, c.read_key)
            branch_meta = c.branch_manager.get_branch_by_id(
                branch_idx, str(local_cfg.my_branch_id))
            head_commit_id = c.ref_manager.read_ref(
                str(branch_meta.head_ref_id), c.read_key)

            commit_chain = fetcher.fetch_commit_chain(
                c.obj_store, c.read_key, head_commit_id)
            flat = {}
            for cid in commit_chain:
                commit = vc.load_commit(cid, c.read_key)
                from sgit_ai.storage.Vault__Sub_Tree import Vault__Sub_Tree
                sub_tree = Vault__Sub_Tree(crypto=self.crypto, obj_store=c.obj_store)
                flat.update(sub_tree.flatten(str(commit.tree_id), c.read_key))

            clone_tree_entries = list(flat.values())

            ops, large_count = batch.build_push_operations(
                c.obj_store, c.ref_manager,
                clone_tree_entries=clone_tree_entries,
                named_blob_ids=set(),
                commit_chain=commit_chain,
                named_commit_id='',
                read_key=c.read_key,
                named_ref_id='ref-named-test',
                clone_commit_id=head_commit_id,
                vault_id='test-vault',
                write_key='test-write-key',
            )
            # _upload_large was called for the large blob and returned True
            assert mock_upload.called
            assert large_count > 0


# ---------------------------------------------------------------------------
# Lines 113-159: _upload_large success/failure paths
# ---------------------------------------------------------------------------

class Test_Vault__Batch__UploadLarge:

    def setup_method(self):
        self.batch, self.crypto, self.api = _make_batch()

    def _fake_presigned_result(self, num_parts=1):
        return {
            'upload_id': 'upload-abc123',
            'part_size': LARGE_PART_SIZE,
            'part_urls': [
                {'part_number': i + 1, 'upload_url': f'https://s3.example.com/part{i+1}'}
                for i in range(num_parts)
            ],
        }

    def _mock_urlopen(self, status=200, etag='"abc123"'):
        """Create a mock context-manager response for urlopen."""
        mock_resp = MagicMock()
        mock_resp.headers.get.return_value = etag
        mock_resp.read.return_value = b''
        mock_resp.status = status
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        return mock_resp

    def test_upload_large_presigned_not_available_returns_false(self):
        """Lines 116-118: presigned_not_available RuntimeError → return False."""
        self.api.presigned_initiate = lambda *a, **kw: (_ for _ in ()).throw(
            RuntimeError('presigned_not_available'))
        result = self.batch._upload_large('vid', 'file_id', b'data', 'wkey')
        assert result is False

    def test_upload_large_presigned_other_error_reraises(self):
        """Line 119: other RuntimeError → re-raised."""
        self.api.presigned_initiate = lambda *a, **kw: (_ for _ in ()).throw(
            RuntimeError('server error'))
        with pytest.raises(RuntimeError, match='server error'):
            self.batch._upload_large('vid', 'file_id', b'data', 'wkey')

    def test_upload_large_single_part_success(self):
        """Lines 113-115, 119-122, 148-153: single-part upload succeeds → True."""
        self.api.presigned_initiate = lambda *a, **kw: self._fake_presigned_result(1)
        self.api.presigned_complete = lambda *a, **kw: {'status': 'ok'}
        mock_resp = self._mock_urlopen()
        with patch('sgit_ai.core.actions.push.Vault__Batch.urlopen', return_value=mock_resp):
            result = self.batch._upload_large('vid', 'file_id', b'A' * 100, 'wkey')
        assert result is True

    def test_upload_large_multi_part_success(self):
        """Lines 141-147: multi-part concurrent upload succeeds → True."""
        self.api.presigned_initiate = lambda *a, **kw: self._fake_presigned_result(2)
        self.api.presigned_complete = lambda *a, **kw: {'status': 'ok'}
        mock_resp = self._mock_urlopen()
        with patch('sgit_ai.core.actions.push.Vault__Batch.urlopen', return_value=mock_resp):
            result = self.batch._upload_large(
                'vid', 'file_id',
                b'A' * (LARGE_PART_SIZE + 1),  # force 2 parts
                'wkey')
        assert result is True

    def test_upload_large_exception_calls_cancel(self):
        """Lines 154-159: PUT raises → presigned_cancel called, exception re-raised."""
        self.api.presigned_initiate = lambda *a, **kw: self._fake_presigned_result(1)
        cancel_called = []
        self.api.presigned_cancel  = lambda *a, **kw: cancel_called.append(True)

        with patch('sgit_ai.core.actions.push.Vault__Batch.urlopen',
                   side_effect=OSError('network error')):
            with pytest.raises(OSError, match='network error'):
                self.batch._upload_large('vid', 'file_id', b'A' * 100, 'wkey')
        assert cancel_called

    def test_upload_large_cancel_exception_silenced(self):
        """Lines 157-158: cancel raises → silenced, original exception still raised."""
        self.api.presigned_initiate = lambda *a, **kw: self._fake_presigned_result(1)
        self.api.presigned_cancel   = lambda *a, **kw: (_ for _ in ()).throw(
            RuntimeError('cancel failed'))

        with patch('sgit_ai.core.actions.push.Vault__Batch.urlopen',
                   side_effect=OSError('network error')):
            with pytest.raises(OSError, match='network error'):
                self.batch._upload_large('vid', 'file_id', b'A' * 100, 'wkey')

    def test_upload_large_with_debug_log(self):
        """Lines 131/136: debug_log attached to api → log_request/log_response called."""
        debug_log = MagicMock()
        debug_log.log_request.return_value = MagicMock()  # entry object
        self.api.debug_log = debug_log

        self.api.presigned_initiate = lambda *a, **kw: self._fake_presigned_result(1)
        self.api.presigned_complete = lambda *a, **kw: {'status': 'ok'}
        mock_resp = self._mock_urlopen()
        with patch('sgit_ai.core.actions.push.Vault__Batch.urlopen', return_value=mock_resp):
            result = self.batch._upload_large('vid', 'file_id', b'A' * 100, 'wkey')
        assert result is True
        assert debug_log.log_request.called
        assert debug_log.log_response.called


# ---------------------------------------------------------------------------
# Line 165: _collect_tree_objects skips already-visited tree
# Line 180: recursive sub-tree
# ---------------------------------------------------------------------------

class Test_Vault__Batch__CollectTree:

    def setup_method(self):
        self.batch, self.crypto, self.api = _make_batch()
        self.tmp_dir = tempfile.mkdtemp()
        # Create bare directory structure
        bare_data = os.path.join(self.tmp_dir, 'bare', 'data')
        os.makedirs(bare_data, exist_ok=True)
        self.obj_store = Vault__Object_Store(vault_path=self.tmp_dir, crypto=self.crypto)
        self.read_key = os.urandom(32)

    def teardown_method(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def _store_tree(self, entries=None):
        """Create an encrypted tree object in the obj_store and return its ID."""
        tree_dict = {'schema': 'tree_v1', 'entries': entries or []}
        plaintext = json.dumps(tree_dict).encode()
        ciphertext = self.crypto.encrypt(self.read_key, plaintext)
        import hashlib
        h = hashlib.sha256(ciphertext).hexdigest()[:12]
        obj_id = f'obj-cas-imm-{h}'
        bare_data = os.path.join(self.tmp_dir, 'bare', 'data')
        with open(os.path.join(bare_data, obj_id), 'wb') as f:
            f.write(ciphertext)
        return obj_id

    def test_collect_tree_skips_already_visited(self):
        """Line 165: tree_id already in uploaded_ids → returns early."""
        tree_id    = self._store_tree()
        uploaded   = {tree_id}   # already visited
        operations = []
        self.batch._collect_tree_objects(tree_id, self.obj_store,
                                         self.read_key, operations, uploaded)
        # Nothing added since it was already visited
        assert operations == []

    def test_collect_tree_recurses_into_subtree(self):
        """Line 180: tree with sub_tree_id → recursively collects sub-tree."""
        # First create a sub-tree
        sub_tree_id = self._store_tree()
        # Create a parent tree that references the sub-tree
        parent_tree_id = self._store_tree(entries=[{'tree_id': sub_tree_id, 'name_enc': ''}])

        uploaded   = set()
        operations = []
        self.batch._collect_tree_objects(parent_tree_id, self.obj_store,
                                          self.read_key, operations, uploaded)
        # Both parent and sub-tree should be collected
        assert parent_tree_id in uploaded
        assert sub_tree_id in uploaded
        assert len(operations) == 2


# ---------------------------------------------------------------------------
# Lines 229-230, 233: execute_batch chunking paths
# ---------------------------------------------------------------------------

class Test_Vault__Batch__ExecuteBatch:

    def setup_method(self):
        self.batch, self.crypto, self.api = _make_batch()

    def _make_ops(self, n_plain, b64_size_each, with_cas=False):
        """Create n plain WRITE ops each with b64_size_each bytes of data."""
        ops = []
        for i in range(n_plain):
            ops.append(dict(
                op=Enum__Batch_Op.WRITE.value,
                file_id=f'bare/data/obj-{i:03d}',
                data='A' * b64_size_each,
            ))
        if with_cas:
            ops.append(dict(
                op=Enum__Batch_Op.WRITE_IF_MATCH.value,
                file_id='bare/refs/ref-named',
                data='B' * 10,
            ))
        return ops

    def test_execute_batch_single_plain_chunk_over_budget(self):
        """Lines 229-230: 1 plain chunk + 1 CAS chunk → elif plain_chunks branch."""
        MAX_B64 = 4 * 1024 * 1024
        # op1 (plain, 4MB+1B) → forces a chunk boundary before op2 (CAS)
        # Resulting: plain_chunks=[[op1]], cas_chunks=[[op2]] → len==1 → elif branch
        ops = [
            dict(op=Enum__Batch_Op.WRITE.value,
                 file_id='bare/data/obj-001',
                 data='A' * (MAX_B64 + 1)),
            dict(op=Enum__Batch_Op.WRITE_IF_MATCH.value,
                 file_id='bare/refs/ref',
                 data='B' * 10),
        ]
        batch_calls = []
        self.api.batch = lambda vid, wk, c: batch_calls.append(c) or {'status': 'ok'}
        result = self.batch.execute_batch('vid', 'wkey', ops)
        assert result == {'status': 'ok'}
        # plain chunk + CAS chunk = 2 calls
        assert len(batch_calls) == 2

    def test_execute_batch_cas_chunk_loop(self):
        """Line 233: CAS chunk in cas_chunks → iterated in for loop."""
        # 2 plain + 1 CAS, all small → fits in 1 batch (fast path)
        # To force chunking with CAS: total > MAX_B64_BYTES with a CAS op
        MB3 = 3 * 1024 * 1024
        ops = [
            dict(op=Enum__Batch_Op.WRITE.value,          file_id='bare/data/obj-001', data='A' * MB3),
            dict(op=Enum__Batch_Op.WRITE.value,          file_id='bare/data/obj-002', data='A' * MB3),
            dict(op=Enum__Batch_Op.WRITE_IF_MATCH.value, file_id='bare/refs/ref',     data='B' * 10),
        ]
        # Total = 6MB+10B > 4MB → chunking:
        # chunk1 = [obj-001], chunk2 = [obj-002, ref-cas]
        # plain_chunks = [chunk1], cas_chunks = [chunk2] (contains CAS op)
        batch_calls = []
        self.api.batch = lambda vid, wk, c: batch_calls.append(c) or {'status': 'ok'}
        self.batch.execute_batch('vid', 'wkey', ops)
        assert len(batch_calls) >= 2

    def test_execute_batch_parallel_plain_chunks(self):
        """Lines 223-228: >1 plain chunks → ThreadPoolExecutor parallel path."""
        MB3 = 3 * 1024 * 1024
        ops = [
            dict(op=Enum__Batch_Op.WRITE.value, file_id='bare/data/obj-001', data='A' * MB3),
            dict(op=Enum__Batch_Op.WRITE.value, file_id='bare/data/obj-002', data='A' * MB3),
        ]
        # Both plain, total > 4MB → 2 plain_chunks, no CAS → parallel path
        batch_calls = []
        self.api.batch = lambda vid, wk, c: batch_calls.append(c) or {'status': 'ok'}
        self.batch.execute_batch('vid', 'wkey', ops)
        assert len(batch_calls) == 2
