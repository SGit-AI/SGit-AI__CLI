import os
import tempfile
import shutil
from sg_send_cli.crypto.Vault__Key_Manager import Vault__Key_Manager
from sg_send_cli.crypto.Vault__Crypto      import Vault__Crypto
from sg_send_cli.crypto.PKI__Crypto        import PKI__Crypto


class Test_Vault__Key_Manager:

    def setup_method(self):
        self.tmp_dir  = tempfile.mkdtemp()
        self.sg_dir   = os.path.join(self.tmp_dir, '.sg_vault')
        os.makedirs(os.path.join(self.sg_dir, 'bare', 'keys'), exist_ok=True)
        self.crypto   = Vault__Crypto()
        self.pki      = PKI__Crypto()
        self.read_key = os.urandom(32)
        self.km       = Vault__Key_Manager(vault_path=self.sg_dir, crypto=self.crypto, pki=self.pki)

    def teardown_method(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_generate_key_id(self):
        kid = self.km.generate_key_id()
        assert kid.startswith('key-')
        assert len(kid) == 20  # 'key-' + 16 hex chars

    def test_generate_branch_key_pair(self):
        private, public = self.km.generate_branch_key_pair()
        assert private is not None
        assert public  is not None

    def test_store_and_load_public_key(self):
        private, public = self.km.generate_branch_key_pair()
        kid = self.km.generate_key_id()
        self.km.store_public_key(kid, public, self.read_key)

        loaded = self.km.load_public_key(kid, self.read_key)
        assert self.pki.compute_fingerprint(loaded) == self.pki.compute_fingerprint(public)

    def test_store_and_load_private_key(self):
        private, public = self.km.generate_branch_key_pair()
        kid = self.km.generate_key_id()
        self.km.store_private_key(kid, private, self.read_key)

        loaded = self.km.load_private_key(kid, self.read_key)
        test_data = b'test signing data'
        sig = self.pki.sign(loaded, test_data)
        assert self.pki.verify(public, sig, test_data)

    def test_store_and_load_private_key_locally(self):
        private, public = self.km.generate_branch_key_pair()
        kid       = self.km.generate_key_id()
        local_dir = os.path.join(self.tmp_dir, 'local')
        self.km.store_private_key_locally(kid, private, local_dir)

        loaded = self.km.load_private_key_locally(kid, local_dir)
        test_data = b'test signing data'
        sig = self.pki.sign(loaded, test_data)
        assert self.pki.verify(public, sig, test_data)

    def test_key_exists(self):
        private, public = self.km.generate_branch_key_pair()
        kid = self.km.generate_key_id()
        assert self.km.key_exists(kid) is False
        self.km.store_public_key(kid, public, self.read_key)
        assert self.km.key_exists(kid) is True

    def test_list_keys(self):
        private, public = self.km.generate_branch_key_pair()
        kid1 = self.km.generate_key_id()
        kid2 = self.km.generate_key_id()
        self.km.store_public_key(kid1, public, self.read_key)
        self.km.store_public_key(kid2, public, self.read_key)
        keys = self.km.list_keys()
        assert len(keys) == 2
