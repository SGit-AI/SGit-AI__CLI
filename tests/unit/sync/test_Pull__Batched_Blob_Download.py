"""The pull path downloads blobs in batches, in parallel — never one request per blob.

A pull that was 12k files behind the comms vault made 12k single-file requests (the
agents' report, 14 Oct). _fetch_missing_objects now hands the blobs to batch_read in
chunks; per-object verification and per-file failure classification are unchanged."""
import os
import tempfile

import pytest

from sgit_ai.core.actions.pull.Vault__Sync__Pull   import Vault__Sync__Pull
from sgit_ai.network.api.Vault__API                import MAX_BATCH_OPS
from sgit_ai.safe_types.Enum__Fetch_Failure_Class  import Enum__Fetch_Failure_Class
from sgit_ai.storage.Vault__Object_Store           import Vault__Object_Store
from tests._helpers.vault_test_env                 import Vault__Test_Env

N_FILES = 2 * MAX_BATCH_OPS + 7                                   # three chunks, the last one partial


class Test_Pull__Batched_Blob_Download:

    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_single_vault(files={f'docs/file-{i:03}.md': f'content {i}' for i in range(N_FILES)})

    @classmethod
    def teardown_class(cls):
        cls._env.cleanup_snapshot()

    def setup_method(self):
        self.s    = self._env.restore()
        self.pull = Vault__Sync__Pull(crypto=self.s.crypto, api=self.s.api)
        c         = self.pull._init_components(self.s.vault_dir)
        cfg       = self.pull._read_local_config(self.s.vault_dir, c.storage)
        index     = c.branch_manager.load_branch_index(self.s.vault_dir, c.branch_index_file_id, c.read_key)
        meta      = c.branch_manager.get_branch_by_id(index, str(cfg.my_branch_id))
        self.head     = c.ref_manager.read_ref(str(meta.head_ref_id), c.read_key)
        self.vault_id = str(c.vault_id)
        self.read_key = c.read_key
        self.tmp      = tempfile.mkdtemp()
        self.sg_dir   = os.path.join(self.tmp, '.sg_vault')
        os.makedirs(os.path.join(self.sg_dir, 'bare', 'data'))
        self.store    = Vault__Object_Store(vault_path=self.sg_dir, crypto=self.s.crypto)

    def teardown_method(self):
        self.s.cleanup()

    def _fetch(self, failures=None, progress=None):
        return self.pull._fetch_missing_objects(self.vault_id, self.head, self.store, self.read_key, self.sg_dir,
                                                _p=progress or (lambda *a, **k: None),
                                                include_blobs=True, failures=failures)

    def test_blobs_come_through_batch_read_never_one_request_each(self, monkeypatch):
        api        = self.s.api
        batch_calls = []
        real_batch  = api.batch_read

        def counting_batch_read(vault_id, file_ids, failures=None):
            batch_calls.append(len(file_ids))
            return real_batch(vault_id, file_ids, failures=failures)

        def no_single_reads(vault_id, file_id):
            raise AssertionError(f'a blob was fetched with one request of its own: {file_id}')

        monkeypatch.setattr(api, 'batch_read', counting_batch_read)
        monkeypatch.setattr(api, 'read', no_single_reads)
        progress = []
        result   = self._fetch(progress=lambda kind, msg, detail='': progress.append((kind, detail)))

        assert result['n_blobs'] == N_FILES
        assert all(self.store.exists(oid) for oid in self._head_blob_ids())
        blob_batches = [n for n in batch_calls if n > 1 or n == MAX_BATCH_OPS]
        assert len([n for n in batch_calls if n == MAX_BATCH_OPS]) >= 2       # full chunks, not one id at a time
        assert max(batch_calls) <= MAX_BATCH_OPS
        downloads = [d for kind, d in progress if kind == 'download']
        assert downloads[0] == f'0/{N_FILES}' and downloads[-1] == f'{N_FILES}/{N_FILES}'
        assert len(downloads) >= 4                                            # the bar moves per chunk, not once at the end

    def test_a_blob_the_server_lost_is_classified_absent_and_the_rest_arrive(self):
        lost = sorted(self._head_blob_ids())[5]
        self.s.api._store.pop(f'{self.vault_id}/bare/data/{lost}')
        failures = {}
        self._fetch(failures=failures)
        assert not self.store.exists(lost)
        assert sum(1 for oid in self._head_blob_ids() if self.store.exists(oid)) == N_FILES - 1
        failure = failures[f'bare/data/{lost}']
        assert failure.classification == Enum__Fetch_Failure_Class.ABSENT
        assert all(fid == f'bare/data/{lost}' for fid in failures)             # nothing else is reported

    def test_a_corrupt_object_is_refused_not_written(self):
        oid = sorted(self._head_blob_ids())[0]
        key = f'{self.vault_id}/bare/data/{oid}'
        self.s.api._store[key] = self.s.api._store[key] + b'tampered'
        failures = {}
        self._fetch(failures=failures)
        assert not self.store.exists(oid)
        assert f'bare/data/{oid}' in failures

    def _head_blob_ids(self):
        from sgit_ai.crypto.PKI__Crypto   import PKI__Crypto
        from sgit_ai.storage.Vault__Commit import Vault__Commit
        from sgit_ai.storage.Vault__Sub_Tree import Vault__Sub_Tree
        c   = self.pull._init_components(self.s.vault_dir)
        vc  = Vault__Commit(crypto=self.s.crypto, pki=PKI__Crypto(), object_store=c.obj_store, ref_manager=c.ref_manager)
        commit = vc.load_commit(self.head, c.read_key)
        flat   = Vault__Sub_Tree(crypto=self.s.crypto, obj_store=c.obj_store).flatten(str(commit.tree_id), c.read_key)
        return {e['blob_id'] for e in flat.values() if e.get('blob_id')}
