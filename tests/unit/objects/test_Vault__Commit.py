import os
import tempfile
import shutil
from sg_send_cli.objects.Vault__Commit       import Vault__Commit
from sg_send_cli.objects.Vault__Object_Store import Vault__Object_Store
from sg_send_cli.objects.Vault__Ref_Manager  import Vault__Ref_Manager
from sg_send_cli.crypto.Vault__Crypto        import Vault__Crypto
from sg_send_cli.crypto.PKI__Crypto          import PKI__Crypto
from sg_send_cli.schemas.Schema__Object_Tree       import Schema__Object_Tree
from sg_send_cli.schemas.Schema__Object_Tree_Entry import Schema__Object_Tree_Entry


class Test_Vault__Commit:

    def setup_method(self):
        self.tmp_dir  = tempfile.mkdtemp()
        self.sg_dir   = os.path.join(self.tmp_dir, '.sg_vault')
        os.makedirs(os.path.join(self.sg_dir, 'bare', 'data'), exist_ok=True)
        os.makedirs(os.path.join(self.sg_dir, 'bare', 'refs'), exist_ok=True)
        self.crypto   = Vault__Crypto()
        self.pki      = PKI__Crypto()
        self.read_key = os.urandom(32)
        self.obj_store = Vault__Object_Store(vault_path=self.sg_dir, crypto=self.crypto, use_v2=True)
        self.ref_mgr   = Vault__Ref_Manager(vault_path=self.sg_dir, crypto=self.crypto, use_v2=True)
        self.vc        = Vault__Commit(crypto=self.crypto, pki=self.pki,
                                       object_store=self.obj_store, ref_manager=self.ref_mgr)

    def teardown_method(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_create_unsigned_commit(self):
        tree = Schema__Object_Tree(schema='tree_v1')
        commit_id = self.vc.create_commit(tree=tree, read_key=self.read_key,
                                          message='test commit', timestamp_ms=1710412800000)
        assert commit_id.startswith('obj-')

        loaded = self.vc.load_commit(commit_id, self.read_key)
        assert str(loaded.message)   == 'test commit'
        assert int(loaded.timestamp_ms) == 1710412800000
        assert str(loaded.schema)    == 'commit_v1'

    def test_create_signed_commit(self):
        private_key, public_key = self.pki.generate_signing_key_pair()
        tree = Schema__Object_Tree(schema='tree_v1')
        commit_id = self.vc.create_commit(tree=tree, read_key=self.read_key,
                                          message='signed commit',
                                          branch_id='branch-clone-a1b2c3d4',
                                          signing_key=private_key,
                                          timestamp_ms=1710412800000)
        loaded = self.vc.load_commit(commit_id, self.read_key)
        assert loaded.signature is not None
        assert str(loaded.signature) != ''

    def test_verify_signature(self):
        private_key, public_key = self.pki.generate_signing_key_pair()
        tree = Schema__Object_Tree(schema='tree_v1')
        commit_id = self.vc.create_commit(tree=tree, read_key=self.read_key,
                                          message='verify me',
                                          signing_key=private_key,
                                          timestamp_ms=1710412800000)
        loaded = self.vc.load_commit(commit_id, self.read_key)
        assert self.vc.verify_commit_signature(loaded, public_key) is True

    def test_commit_with_parent(self):
        tree1     = Schema__Object_Tree(schema='tree_v1')
        commit_id1 = self.vc.create_commit(tree=tree1, read_key=self.read_key,
                                           message='first', timestamp_ms=1000)

        tree2     = Schema__Object_Tree(schema='tree_v1')
        tree2.entries.append(Schema__Object_Tree_Entry(path='hello.txt', blob_id='obj-aabbccddeeff', size=5))
        commit_id2 = self.vc.create_commit(tree=tree2, read_key=self.read_key,
                                           parent_ids=[commit_id1],
                                           message='second', timestamp_ms=2000)

        loaded = self.vc.load_commit(commit_id2, self.read_key)
        assert str(loaded.parent) != ''
        assert len(loaded.parents) == 1

    def test_load_tree(self):
        tree = Schema__Object_Tree(schema='tree_v1')
        tree.entries.append(Schema__Object_Tree_Entry(path='file.txt', blob_id='obj-aabbccddeeff', size=10))
        commit_id = self.vc.create_commit(tree=tree, read_key=self.read_key,
                                          message='tree test', timestamp_ms=1000)

        loaded_commit = self.vc.load_commit(commit_id, self.read_key)
        loaded_tree   = self.vc.load_tree(str(loaded_commit.tree_id), self.read_key)
        assert len(loaded_tree.entries) == 1
        assert loaded_tree.entries[0].path == 'file.txt'
