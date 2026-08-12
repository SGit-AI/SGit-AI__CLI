"""Path-traversal regression: a malicious tree entry name must not escape the
working directory during checkout. Guards the core clone/pull extraction path
(Vault__Sub_Tree.checkout), independent of the transfer/archive feature."""
import json
import os
import shutil
import tempfile
import pytest

from sgit_ai.crypto.Vault__Crypto        import Vault__Crypto
from sgit_ai.storage.Vault__Object_Store import Vault__Object_Store
from sgit_ai.storage.Vault__Sub_Tree     import Vault__Sub_Tree
from sgit_ai.schemas.Schema__Object_Tree       import Schema__Object_Tree
from sgit_ai.schemas.Schema__Object_Tree_Entry import Schema__Object_Tree_Entry
from sgit_ai.core.Vault__Errors                import Vault__Unsafe_Path_Error


class Test_AppSec__Checkout_Path_Traversal:

    def setup_method(self):
        self.tmp     = tempfile.mkdtemp()
        self.crypto  = Vault__Crypto()
        self.sg_dir  = os.path.join(self.tmp, 'work', '.sg_vault')
        os.makedirs(os.path.join(self.sg_dir, 'bare', 'data'), exist_ok=True)
        self.store   = Vault__Object_Store(vault_path=self.sg_dir, crypto=self.crypto)
        self.rk      = self.crypto.derive_read_key('pw', 'abcd1234')
        self.subtree = Vault__Sub_Tree(crypto=self.crypto, obj_store=self.store)

    def teardown_method(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _malicious_tree(self, evil_name: str) -> str:
        # store a blob, then a tree whose single entry name is attacker-chosen
        blob_id = self.store.store(self.crypto.encrypt(self.rk, b'pwned'))
        entry   = Schema__Object_Tree_Entry(
            blob_id  = blob_id,
            name_enc = self.crypto.encrypt_metadata_deterministic(self.rk, evil_name),
        )
        tree = Schema__Object_Tree(schema='tree_v1', entries=[entry])
        return self.store.store(
            self.crypto.encrypt_deterministic(self.rk, json.dumps(tree.json()).encode()))

    def test_checkout__rejects_parent_traversal_name(self):
        work    = os.path.join(self.tmp, 'work')
        outside = os.path.join(self.tmp, 'pwned.txt')
        tree_id = self._malicious_tree('../pwned.txt')

        with pytest.raises(Vault__Unsafe_Path_Error):
            self.subtree.checkout(work, tree_id, self.rk)
        assert not os.path.exists(outside)          # nothing written outside the working dir

    def test_checkout__rejects_absolute_name(self):
        work   = os.path.join(self.tmp, 'work')
        target = os.path.join(self.tmp, 'abs-escape.txt')
        tree_id = self._malicious_tree(target)      # absolute path as the entry name

        with pytest.raises(Vault__Unsafe_Path_Error):
            self.subtree.checkout(work, tree_id, self.rk)
        assert not os.path.exists(target)

    def test_checkout__benign_name_still_works(self):
        work    = os.path.join(self.tmp, 'work')
        tree_id = self._malicious_tree('safe/doc.txt')
        self.subtree.checkout(work, tree_id, self.rk)
        assert os.path.isfile(os.path.join(work, 'safe', 'doc.txt'))
