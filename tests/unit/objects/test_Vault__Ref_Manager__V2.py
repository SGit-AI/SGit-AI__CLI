import os
import tempfile
import shutil
from sgit_ai.objects.Vault__Ref_Manager import Vault__Ref_Manager
from sgit_ai.crypto.Vault__Crypto       import Vault__Crypto


class Test_Vault__Ref_Manager__V2:

    def setup_method(self):
        self.tmp_dir  = tempfile.mkdtemp()
        self.sg_dir   = os.path.join(self.tmp_dir, '.sg_vault')
        os.makedirs(os.path.join(self.sg_dir, 'bare', 'refs'), exist_ok=True)
        self.crypto   = Vault__Crypto()
        self.read_key = os.urandom(32)
        self.refs     = Vault__Ref_Manager(vault_path=self.sg_dir, crypto=self.crypto)

    def teardown_method(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_write_and_read_encrypted_ref(self):
        self.refs.write_ref('ref-pid-muw-a1b2c3d4e5f6', 'obj-cas-imm-112233445566', self.read_key)
        commit_id = self.refs.read_ref('ref-pid-muw-a1b2c3d4e5f6', self.read_key)
        assert commit_id == 'obj-cas-imm-112233445566'

    def test_write_and_read_plaintext_ref(self):
        self.refs.write_ref('ref-pid-snw-aabbccddeeff', 'obj-cas-imm-112233445566')
        commit_id = self.refs.read_ref('ref-pid-snw-aabbccddeeff')
        assert commit_id == 'obj-cas-imm-112233445566'

    def test_list_refs(self):
        self.refs.write_ref('ref-pid-muw-aaaabbbbcccc', 'commit1', self.read_key)
        self.refs.write_ref('ref-pid-snw-ccccddddeeee', 'commit2', self.read_key)
        refs = self.refs.list_refs()
        assert len(refs) == 2
        assert 'ref-pid-muw-aaaabbbbcccc' in refs
        assert 'ref-pid-snw-ccccddddeeee' in refs

    def test_ref_exists(self):
        self.refs.write_ref('ref-pid-muw-exists111111', 'commit1', self.read_key)
        assert self.refs.ref_exists('ref-pid-muw-exists111111') is True
        assert self.refs.ref_exists('ref-pid-muw-missing11111') is False

    def test_read_nonexistent_returns_none(self):
        assert self.refs.read_ref('ref-pid-muw-nope12345678', self.read_key) is None

    def test_is_initialized(self):
        assert self.refs.is_initialized() is False
        self.refs.write_ref('ref-pid-muw-init12345678', 'commit1', self.read_key)
        assert self.refs.is_initialized() is True

    def test_encrypt_ref_value_round_trip(self):
        ciphertext = self.refs.encrypt_ref_value('obj-cas-imm-112233445566', self.read_key)
        assert isinstance(ciphertext, bytes)
        # Write encrypted bytes directly, then read back
        ref_path = os.path.join(self.sg_dir, 'bare', 'refs', 'ref-pid-muw-roundtrip111')
        with open(ref_path, 'wb') as f:
            f.write(ciphertext)
        result = self.refs.read_ref('ref-pid-muw-roundtrip111', self.read_key)
        assert result == 'obj-cas-imm-112233445566'
