import os
import tempfile
import shutil
from sg_send_cli.objects.Vault__Ref_Manager import Vault__Ref_Manager
from sg_send_cli.crypto.Vault__Crypto       import Vault__Crypto


class Test_Vault__Ref_Manager__V2:

    def setup_method(self):
        self.tmp_dir  = tempfile.mkdtemp()
        self.sg_dir   = os.path.join(self.tmp_dir, '.sg_vault')
        os.makedirs(os.path.join(self.sg_dir, 'bare', 'refs'), exist_ok=True)
        self.crypto   = Vault__Crypto()
        self.read_key = os.urandom(32)
        self.refs     = Vault__Ref_Manager(vault_path=self.sg_dir, crypto=self.crypto, use_v2=True)

    def teardown_method(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_write_and_read_encrypted_ref(self):
        self.refs.write_ref('ref-a1b2c3d4', 'abc123def456', self.read_key)
        commit_id = self.refs.read_ref('ref-a1b2c3d4', self.read_key)
        assert commit_id == 'abc123def456'

    def test_write_and_read_plaintext_ref(self):
        self.refs.write_ref('ref-plain1234', 'abc123def456')
        commit_id = self.refs.read_ref('ref-plain1234')
        assert commit_id == 'abc123def456'

    def test_list_refs(self):
        self.refs.write_ref('ref-aaaabbbb', 'commit1', self.read_key)
        self.refs.write_ref('ref-ccccdddd', 'commit2', self.read_key)
        refs = self.refs.list_refs()
        assert len(refs) == 2
        assert 'ref-aaaabbbb' in refs
        assert 'ref-ccccdddd' in refs

    def test_ref_exists(self):
        self.refs.write_ref('ref-exists11', 'commit1', self.read_key)
        assert self.refs.ref_exists('ref-exists11') is True
        assert self.refs.ref_exists('ref-missing11') is False

    def test_read_nonexistent_returns_none(self):
        assert self.refs.read_ref('ref-nope1234', self.read_key) is None

    def test_is_initialized_v2(self):
        assert self.refs.is_initialized() is False
        self.refs.write_ref('ref-init1234', 'commit1', self.read_key)
        assert self.refs.is_initialized() is True

    def test_legacy_head_still_works(self):
        self.refs.write_head('abc123def456')
        assert self.refs.read_head() == 'abc123def456'
