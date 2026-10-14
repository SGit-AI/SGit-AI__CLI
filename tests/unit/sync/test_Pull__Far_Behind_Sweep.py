"""A pull far behind a linear history used to make one request per commit before a
single tree arrived (the comms vault: 1,227 commits). Past SWEEP_AFTER_WAVES missing
waves the walk lists the store once and fetches everything not local in parallel, as a
clone does. Partial clones never sweep."""
import os
import tempfile

from sgit_ai.core.actions.pull.Vault__Sync__Pull   import Vault__Sync__Pull, SWEEP_AFTER_WAVES
from sgit_ai.storage.Vault__Object_Store           import Vault__Object_Store
from sgit_ai.storage.Vault__Scope                  import Vault__Scope
from tests._helpers.vault_test_env                 import Vault__Test_Env

N_COMMITS = SWEEP_AFTER_WAVES + 6


class Test_Pull__Far_Behind_Sweep:

    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_single_vault(files={'first.md': 'first'})

    @classmethod
    def teardown_class(cls):
        cls._env.cleanup_snapshot()

    def setup_method(self):
        self.s = self._env.restore()
        for i in range(N_COMMITS):                                  # a linear history, one file per commit
            with open(os.path.join(self.s.vault_dir, f'note-{i:02}.md'), 'w') as f:
                f.write(f'note {i}')
            self.s.sync.commit(self.s.vault_dir, f'note {i}')
        self.s.sync.push(self.s.vault_dir)
        self.pull = Vault__Sync__Pull(crypto=self.s.crypto, api=self.s.api)
        c         = self.pull._init_components(self.s.vault_dir)
        cfg       = self.pull._read_local_config(self.s.vault_dir, c.storage)
        index     = c.branch_manager.load_branch_index(self.s.vault_dir, c.branch_index_file_id, c.read_key)
        meta      = c.branch_manager.get_branch_by_id(index, str(cfg.my_branch_id))
        self.head     = c.ref_manager.read_ref(str(meta.head_ref_id), c.read_key)
        self.vault_id = str(c.vault_id)
        self.read_key = c.read_key
        self.n_server = sum(1 for k in self.s.api._store if k.startswith(f'{self.vault_id}/bare/data/obj-cas-imm-'))
        tmp           = tempfile.mkdtemp()
        self.sg_dir   = os.path.join(tmp, '.sg_vault')
        os.makedirs(os.path.join(self.sg_dir, 'bare', 'data'))
        self.store    = Vault__Object_Store(vault_path=self.sg_dir, crypto=self.s.crypto)
        self.calls    = dict(list_files=0, batch_read=0)
        api, real_list, real_batch = self.s.api, self.s.api.list_files, self.s.api.batch_read
        api.list_files = lambda vault_id, prefix='': (self.calls.__setitem__('list_files', self.calls['list_files'] + 1), real_list(vault_id, prefix))[1]
        api.batch_read = lambda vault_id, ids, failures=None: (self.calls.__setitem__('batch_read', self.calls['batch_read'] + 1), real_batch(vault_id, ids, failures=failures))[1]

    def teardown_method(self):
        self.s.cleanup()

    def _fetch(self, scope=None):
        return self.pull._fetch_missing_objects(self.vault_id, self.head, self.store, self.read_key, self.sg_dir,
                                                include_blobs=True, scope=scope)

    def test_far_behind_lists_once_and_fetches_in_bulk(self):
        result = self._fetch()
        assert self.calls['list_files'] == 1
        assert self.calls['batch_read'] < N_COMMITS                 # not one request per commit any more
        assert len(os.listdir(os.path.join(self.sg_dir, 'bare', 'data'))) == self.n_server
        assert result['n_commits'] == self._chain_len()                # swept commits still count as new
        assert result['n_blobs'] == N_COMMITS + 1                      # one new blob per commit, plus first.md

    def test_a_short_pull_never_lists(self):
        parent_chain = []
        from sgit_ai.crypto.PKI__Crypto   import PKI__Crypto
        from sgit_ai.storage.Vault__Commit import Vault__Commit
        c  = self.pull._init_components(self.s.vault_dir)
        vc = Vault__Commit(crypto=self.s.crypto, pki=PKI__Crypto(), object_store=c.obj_store, ref_manager=c.ref_manager)
        cid = self.head
        for _ in range(3):                                           # stop three commits back: a short pull
            cid = str(vc.load_commit(cid, c.read_key).parents[0])
        self.pull._fetch_missing_objects(self.vault_id, self.head, self.store, self.read_key, self.sg_dir,
                                         include_blobs=True, stop_at=cid)
        assert self.calls['list_files'] == 0

    def test_a_partial_clone_never_sweeps(self):
        scope = Vault__Scope().with_paths(['docs'])
        assert scope.is_partial()
        self._fetch(scope=scope)
        assert self.calls['list_files'] == 0

    def test_a_host_that_cannot_list_leaves_the_walk_to_finish(self):
        self.s.api.list_files = lambda vault_id, prefix='': (_ for _ in ()).throw(RuntimeError('API Error: HTTP 404'))
        result = self._fetch()
        assert result['n_commits'] == self._chain_len()
        assert len(os.listdir(os.path.join(self.sg_dir, 'bare', 'data'))) == self.n_server

    def _chain_len(self):
        from sgit_ai.crypto.PKI__Crypto   import PKI__Crypto
        from sgit_ai.storage.Vault__Commit import Vault__Commit
        c  = self.pull._init_components(self.s.vault_dir)
        vc = Vault__Commit(crypto=self.s.crypto, pki=PKI__Crypto(), object_store=c.obj_store, ref_manager=c.ref_manager)
        n, cid = 0, self.head
        while cid:
            n += 1
            parents = vc.load_commit(cid, c.read_key).parents or []
            cid = str(parents[0]) if parents else ''
        return n
