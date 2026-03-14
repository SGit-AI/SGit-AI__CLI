import json
import os
import tempfile
import shutil
from sg_send_cli.sync.Vault__Fetch           import Vault__Fetch
from sg_send_cli.sync.Vault__Storage         import Vault__Storage
from sg_send_cli.objects.Vault__Object_Store import Vault__Object_Store
from sg_send_cli.objects.Vault__Ref_Manager  import Vault__Ref_Manager
from sg_send_cli.objects.Vault__Commit       import Vault__Commit
from sg_send_cli.crypto.Vault__Crypto        import Vault__Crypto
from sg_send_cli.crypto.PKI__Crypto          import PKI__Crypto
from sg_send_cli.api.Vault__API              import Vault__API
from sg_send_cli.schemas.Schema__Object_Tree       import Schema__Object_Tree
from sg_send_cli.schemas.Schema__Object_Tree_Entry import Schema__Object_Tree_Entry
from sg_send_cli.api.Vault__API__In_Memory         import Vault__API__In_Memory


class Test_Vault__Fetch:

    def setup_method(self):
        self.tmp_dir  = tempfile.mkdtemp()
        self.crypto   = Vault__Crypto()
        self.pki      = PKI__Crypto()
        self.read_key = os.urandom(32)
        self.storage  = Vault__Storage()
        self.storage.create_bare_structure(self.tmp_dir)
        self.sg_dir   = self.storage.sg_vault_dir(self.tmp_dir)
        self.obj_store = Vault__Object_Store(vault_path=self.sg_dir, crypto=self.crypto, use_v2=True)
        self.ref_mgr   = Vault__Ref_Manager(vault_path=self.sg_dir, crypto=self.crypto, use_v2=True)
        self.vc        = Vault__Commit(crypto=self.crypto, pki=self.pki,
                                       object_store=self.obj_store, ref_manager=self.ref_mgr)
        self.fetcher   = Vault__Fetch(crypto=self.crypto, api=Vault__API(), storage=self.storage)

    def teardown_method(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def _create_commit(self, parent_ids=None, files=None):
        tree = Schema__Object_Tree(schema='tree_v1')
        for path, blob_id in (files or {}).items():
            tree.entries.append(Schema__Object_Tree_Entry(path=path, blob_id=blob_id, size=10))
        return self.vc.create_commit(tree=tree, read_key=self.read_key,
                                     parent_ids=parent_ids, message='test',
                                     timestamp_ms=1000)

    def test_fetch_commit_chain_single(self):
        c1 = self._create_commit()
        chain = self.fetcher.fetch_commit_chain(self.obj_store, self.read_key, c1)
        assert chain == [c1]

    def test_fetch_commit_chain_linear(self):
        c1 = self._create_commit()
        c2 = self._create_commit(parent_ids=[c1])
        c3 = self._create_commit(parent_ids=[c2])
        chain = self.fetcher.fetch_commit_chain(self.obj_store, self.read_key, c3)
        assert chain == [c3, c2, c1]

    def test_fetch_commit_chain_stops_at(self):
        c1 = self._create_commit()
        c2 = self._create_commit(parent_ids=[c1])
        c3 = self._create_commit(parent_ids=[c2])
        chain = self.fetcher.fetch_commit_chain(self.obj_store, self.read_key, c3, stop_at=c2)
        assert chain == [c3, c2]

    def test_find_lca_same_commit(self):
        c1 = self._create_commit()
        lca = self.fetcher.find_lca(self.obj_store, self.read_key, c1, c1)
        assert lca == c1

    def test_find_lca_linear(self):
        c1 = self._create_commit()
        c2 = self._create_commit(parent_ids=[c1])
        c3 = self._create_commit(parent_ids=[c2])
        lca = self.fetcher.find_lca(self.obj_store, self.read_key, c2, c3)
        assert lca == c2

    def test_find_lca_forked(self):
        c1 = self._create_commit()
        c2 = self._create_commit(parent_ids=[c1])  # branch A
        c3 = self._create_commit(parent_ids=[c1])  # branch B
        lca = self.fetcher.find_lca(self.obj_store, self.read_key, c2, c3)
        assert lca == c1

    def test_find_lca_deeper_fork(self):
        c1 = self._create_commit()
        c2 = self._create_commit(parent_ids=[c1])
        c3 = self._create_commit(parent_ids=[c2])  # branch A
        c4 = self._create_commit(parent_ids=[c2])  # branch B
        c5 = self._create_commit(parent_ids=[c3])  # branch A continues
        lca = self.fetcher.find_lca(self.obj_store, self.read_key, c5, c4)
        assert lca == c2

    def test_find_lca_no_common_ancestor(self):
        c1 = self._create_commit()
        c2 = self._create_commit()  # totally separate
        lca = self.fetcher.find_lca(self.obj_store, self.read_key, c1, c2)
        assert lca is None

    def test_fetch_commit_chain_limit(self):
        c1 = self._create_commit()
        c2 = self._create_commit(parent_ids=[c1])
        c3 = self._create_commit(parent_ids=[c2])
        chain = self.fetcher.fetch_commit_chain(self.obj_store, self.read_key, c3, limit=2)
        assert len(chain) == 2
        assert chain[0] == c3
        assert chain[1] == c2

    def test_fetch_commit_chain_invalid_commit(self):
        chain = self.fetcher.fetch_commit_chain(self.obj_store, self.read_key, 'nonexistent')
        assert chain == ['nonexistent']

    def test_find_lca_with_none_commits(self):
        lca = self.fetcher.find_lca(self.obj_store, self.read_key, None, None)
        assert lca is None

    def test_fetch_named_branch_state(self):
        ref_id    = 'ref-' + os.urandom(8).hex()
        commit_id = self._create_commit()
        self.ref_mgr.write_ref(ref_id, commit_id, self.read_key)
        api     = Vault__API__In_Memory()
        api.setup()
        fetcher = Vault__Fetch(crypto=self.crypto, api=api, storage=self.storage)
        result  = fetcher.fetch_named_branch_state(self.tmp_dir, 'test-vault',
                                                     self.read_key, 'write-key',
                                                     ref_id)
        assert result['remote_commit_id'] == commit_id
        assert result['named_ref_id']     == ref_id
