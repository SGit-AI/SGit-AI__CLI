import json
import os
import tempfile
from sgit_ai.storage.Vault__Commit       import Vault__Commit
from sgit_ai.storage.Vault__Object_Store import Vault__Object_Store
from sgit_ai.storage.Vault__Ref_Manager  import Vault__Ref_Manager
from sgit_ai.crypto.Vault__Crypto        import Vault__Crypto
from sgit_ai.crypto.PKI__Crypto          import PKI__Crypto
from sgit_ai.storage.Vault__Sub_Tree        import Vault__Sub_Tree
from sgit_ai.schemas.Schema__Object_Tree import Schema__Object_Tree


class Test_Vault__Commit:

    def setup_method(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.sg_dir  = os.path.join(self.tmp_dir, '.sg_vault')
        os.makedirs(os.path.join(self.sg_dir, 'bare', 'data'), exist_ok=True)
        os.makedirs(os.path.join(self.sg_dir, 'bare', 'refs'), exist_ok=True)
        self.crypto    = Vault__Crypto()
        self.pki       = PKI__Crypto()
        self.read_key  = os.urandom(32)
        self.obj_store = Vault__Object_Store(vault_path=self.sg_dir, crypto=self.crypto)
        self.ref_mgr   = Vault__Ref_Manager(vault_path=self.sg_dir, crypto=self.crypto)
        self.vc        = Vault__Commit(crypto=self.crypto, pki=self.pki,
                                       object_store=self.obj_store, ref_manager=self.ref_mgr)
        self.sub_tree  = Vault__Sub_Tree(crypto=self.crypto, obj_store=self.obj_store)

    def _store_blob(self, content: bytes) -> str:
        encrypted = self.crypto.encrypt(self.read_key, content)
        return self.obj_store.store(encrypted)

    def _build_tree(self, files: dict) -> str:
        """Build a tree from {path: content_bytes} and return root tree ID."""
        flat_map = {}
        for path, content in files.items():
            blob_id = self._store_blob(content)
            flat_map[path] = {'blob_id': blob_id, 'size': len(content),
                              'content_hash': self.crypto.content_hash(content)}
        return self.sub_tree.build_from_flat(flat_map, self.read_key)

    def test_create_unsigned_commit(self):
        tree_id   = self._build_tree({'hello.txt': b'hello world'})
        commit_id = self.vc.create_commit(read_key=self.read_key, tree_id=tree_id,
                                           message='test commit')
        assert commit_id.startswith('obj-cas-imm-')
        commit = self.vc.load_commit(commit_id, self.read_key)
        assert str(commit.tree_id) == tree_id
        assert commit.message_enc is not None

    def test_create_signed_commit(self):
        tree_id = self._build_tree({'data.txt': b'signed data'})
        private_key, public_key = self.pki.generate_signing_key_pair()
        commit_id = self.vc.create_commit(read_key=self.read_key, tree_id=tree_id,
                                           message='signed', signing_key=private_key)
        commit = self.vc.load_commit(commit_id, self.read_key)
        assert commit.signature is not None
        assert self.vc.verify_commit_signature(commit, public_key) is True

    def test_verify_signature(self):
        tree_id = self._build_tree({'v.txt': b'verify me'})
        priv, pub = self.pki.generate_signing_key_pair()
        commit_id = self.vc.create_commit(read_key=self.read_key, tree_id=tree_id,
                                           message='verify', signing_key=priv)
        commit = self.vc.load_commit(commit_id, self.read_key)
        assert self.vc.verify_commit_signature(commit, pub) is True

        _, wrong_pub = self.pki.generate_signing_key_pair()
        assert self.vc.verify_commit_signature(commit, wrong_pub) is False

    def test_commit_with_parent(self):
        tree1_id  = self._build_tree({'a.txt': b'first'})
        commit1   = self.vc.create_commit(read_key=self.read_key, tree_id=tree1_id, message='first')

        tree2_id  = self._build_tree({'a.txt': b'first', 'b.txt': b'second'})
        commit2   = self.vc.create_commit(read_key=self.read_key, tree_id=tree2_id,
                                           parent_ids=[commit1], message='second')
        loaded = self.vc.load_commit(commit2, self.read_key)
        assert len(loaded.parents) == 1
        assert str(loaded.parents[0]) == commit1

    def test_load_tree(self):
        tree_id = self._build_tree({'readme.md': b'# Hello'})
        tree    = self.vc.load_tree(tree_id, self.read_key)
        assert len(tree.entries) == 1
        assert tree.entries[0].blob_id is not None
        assert tree.entries[0].name_enc is not None
