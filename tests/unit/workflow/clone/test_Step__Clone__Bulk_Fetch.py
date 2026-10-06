"""Full clones fetch the whole store in one parallel sweep; the walks then run
against a store that already has everything, and still fetch anything missing."""
import os
from tests._helpers.vault_test_env              import Vault__Test_Env
from sgit_ai.core.Vault__Sync                   import Vault__Sync
from sgit_ai.network.api.Vault__API__In_Memory  import Vault__API__In_Memory


class _Counting_API(Vault__API__In_Memory):
    """A real in-memory API that counts what the clone asks it for."""
    def setup(self):
        super().setup(); self.calls = {'list_files': 0, 'batch_read': 0, 'ids_requested': 0}; return self
    def list_files(self, vault_id, prefix=''):
        self.calls['list_files'] += 1; return super().list_files(vault_id, prefix)
    def batch_read(self, vault_id, file_ids, failures=None):
        self.calls['batch_read'] += 1
        self.calls['ids_requested'] += sum(1 for f in file_ids if '/bare/data/' in f'/{f}')   # objects only
        return super().batch_read(vault_id, file_ids, failures)


class _No_Listing_API(_Counting_API):
    def list_files(self, vault_id, prefix=''):
        self.calls['list_files'] += 1
        raise RuntimeError('API Error: HTTP 404 Not Found — no listing endpoint')


def _write(d, rel, content):
    full = os.path.join(d, rel); os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, 'w') as f: f.write(content)


class Test_Step__Clone__Bulk_Fetch:
    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_single_vault(files={'a.txt': 'a', 'docs/b.md': 'b'})

    @classmethod
    def teardown_class(cls):
        if cls._env: cls._env.cleanup_snapshot()

    def setup_method(self):
        self.env = self._env.restore()
        for i in range(3):                                      # a little history
            _write(self.env.vault_dir, 'a.txt', f'a v{i}'); _write(self.env.vault_dir, f'n{i}.txt', 'x')
            self.env.sync.commit(self.env.vault_dir, message=f'c{i}')
        self.env.sync.push(self.env.vault_dir)
        self.n_objects = sum(1 for k in self.env.api._store if '/bare/data/obj-cas-imm-' in k)

    def teardown_method(self):
        self.env.cleanup()

    def _clone_with(self, api_cls):
        api = api_cls(); api.setup(); api._store = self.env.api._store
        sync = Vault__Sync(crypto=self.env.crypto, api=api)
        target = os.path.join(self.env.tmp_dir, 'bulk-clone')
        result = sync.clone(self.env.vault_key, target)
        return api, result, target

    def test_full_clone_lists_once_and_fetches_everything_in_bulk(self):
        api, result, target = self._clone_with(_Counting_API)
        assert api.calls['list_files'] == 1
        assert api.calls['ids_requested'] >= self.n_objects          # every object came through the bulk sweep
        assert sorted(os.listdir(os.path.join(target, '.sg_vault', 'bare', 'data'))) == \
               sorted(k.rsplit('/', 1)[-1] for k in self.env.api._store if '/bare/data/obj-cas-imm-' in k)
        assert open(os.path.join(target, 'a.txt')).read() == 'a v2'
        assert os.path.exists(os.path.join(target, 'n2.txt'))

    def test_walks_fetch_nothing_after_the_bulk_sweep(self):
        api, result, target = self._clone_with(_Counting_API)
        assert api.calls['ids_requested'] == self.n_objects         # every object requested exactly once, by the sweep

    def test_without_a_listing_the_clone_still_completes(self):
        api, result, target = self._clone_with(_No_Listing_API)
        assert api.calls['list_files'] == 1
        assert open(os.path.join(target, 'a.txt')).read() == 'a v2'
        assert api.calls['ids_requested'] >= self.n_objects         # the walks did the fetching (trees once per level)

    def test_sparse_clone_skips_the_sweep(self):
        api = _Counting_API(); api.setup(); api._store = self.env.api._store
        sync = Vault__Sync(crypto=self.env.crypto, api=api)
        target = os.path.join(self.env.tmp_dir, 'sparse-clone')
        sync.clone(self.env.vault_key, target, sparse=True)
        assert api.calls['list_files'] == 0
        blobs_local = [k for k in os.listdir(os.path.join(target, '.sg_vault', 'bare', 'data'))]
        assert len(blobs_local) < self.n_objects                    # no blobs downloaded
