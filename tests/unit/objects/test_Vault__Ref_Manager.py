import os
import tempfile
from sg_send_cli.objects.Vault__Ref_Manager import Vault__Ref_Manager
from sg_send_cli.crypto.Vault__Crypto       import Vault__Crypto


class Test_Vault__Ref_Manager:

    def setup_method(self):
        self.tmp_dir    = tempfile.mkdtemp()
        self.vault_path = self.tmp_dir
        self.crypto     = Vault__Crypto()
        self.ref_mgr    = Vault__Ref_Manager(vault_path=self.vault_path, crypto=self.crypto)

    def test_is_initialized_false_initially(self):
        assert self.ref_mgr.is_initialized() is False

    def test_write_and_read_ref_plaintext(self):
        self.ref_mgr.write_ref('ref-pid-muw-aabbccddeeff', 'obj-cas-imm-112233445566')
        result = self.ref_mgr.read_ref('ref-pid-muw-aabbccddeeff')
        assert result == 'obj-cas-imm-112233445566'

    def test_write_and_read_ref_encrypted(self):
        read_key = os.urandom(32)
        self.ref_mgr.write_ref('ref-pid-muw-aabbccddeeff', 'obj-cas-imm-112233445566', read_key)
        result = self.ref_mgr.read_ref('ref-pid-muw-aabbccddeeff', read_key)
        assert result == 'obj-cas-imm-112233445566'

    def test_is_initialized_after_write(self):
        self.ref_mgr.write_ref('ref-pid-muw-aabbccddeeff', 'obj-cas-imm-112233445566')
        assert self.ref_mgr.is_initialized() is True

    def test_write_creates_bare_refs_directory(self):
        self.ref_mgr.write_ref('ref-pid-muw-aabbccddeeff', 'obj-cas-imm-112233445566')
        refs_dir = os.path.join(self.vault_path, 'bare', 'refs')
        assert os.path.isdir(refs_dir)

    def test_overwrite_ref(self):
        read_key = os.urandom(32)
        self.ref_mgr.write_ref('ref-pid-muw-aabbccddeeff', 'obj-cas-imm-111111111111', read_key)
        self.ref_mgr.write_ref('ref-pid-muw-aabbccddeeff', 'obj-cas-imm-222222222222', read_key)
        result = self.ref_mgr.read_ref('ref-pid-muw-aabbccddeeff', read_key)
        assert result == 'obj-cas-imm-222222222222'

    def test_read_ref_missing_returns_none(self):
        assert self.ref_mgr.read_ref('ref-pid-muw-doesnotexist') is None

    def test_ref_exists(self):
        assert self.ref_mgr.ref_exists('ref-pid-muw-aabbccddeeff') is False
        self.ref_mgr.write_ref('ref-pid-muw-aabbccddeeff', 'test')
        assert self.ref_mgr.ref_exists('ref-pid-muw-aabbccddeeff') is True

    def test_list_refs(self):
        self.ref_mgr.write_ref('ref-pid-muw-aabbccddeeff', 'test1')
        self.ref_mgr.write_ref('ref-pid-snw-112233445566', 'test2')
        refs = self.ref_mgr.list_refs()
        assert len(refs) == 2
        assert 'ref-pid-muw-aabbccddeeff' in refs
        assert 'ref-pid-snw-112233445566' in refs

    def test_encrypt_ref_value(self):
        read_key   = os.urandom(32)
        ciphertext = self.ref_mgr.encrypt_ref_value('obj-cas-imm-112233445566', read_key)
        assert isinstance(ciphertext, bytes)
        assert len(ciphertext) > 0

    def test_get_ref_file_hash(self):
        self.ref_mgr.write_ref('ref-pid-muw-aabbccddeeff', 'test-value')
        b64 = self.ref_mgr.get_ref_file_hash('ref-pid-muw-aabbccddeeff')
        assert b64 is not None
        assert isinstance(b64, str)
