import os
import tempfile
import shutil
from sg_send_cli.sync.Vault__Branch_Manager import Vault__Branch_Manager
from sg_send_cli.sync.Vault__Storage        import Vault__Storage
from sg_send_cli.objects.Vault__Ref_Manager import Vault__Ref_Manager
from sg_send_cli.crypto.Vault__Crypto       import Vault__Crypto
from sg_send_cli.crypto.PKI__Crypto         import PKI__Crypto
from sg_send_cli.crypto.Vault__Key_Manager  import Vault__Key_Manager
from sg_send_cli.schemas.Schema__Branch_Index import Schema__Branch_Index
from sg_send_cli.safe_types.Enum__Branch_Type import Enum__Branch_Type


class Test_Vault__Branch_Manager:

    def setup_method(self):
        self.tmp_dir  = tempfile.mkdtemp()
        self.crypto   = Vault__Crypto()
        self.pki      = PKI__Crypto()
        self.read_key = os.urandom(32)
        self.storage  = Vault__Storage()
        self.storage.create_bare_structure(self.tmp_dir)
        sg_dir        = self.storage.sg_vault_dir(self.tmp_dir)
        self.km       = Vault__Key_Manager(vault_path=sg_dir, crypto=self.crypto, pki=self.pki)
        self.ref_mgr  = Vault__Ref_Manager(vault_path=sg_dir, crypto=self.crypto, use_v2=True)
        self.bm       = Vault__Branch_Manager(vault_path=sg_dir, crypto=self.crypto,
                                              key_manager=self.km, ref_manager=self.ref_mgr,
                                              storage=self.storage)

    def teardown_method(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_create_named_branch(self):
        meta = self.bm.create_named_branch(self.tmp_dir, 'current', self.read_key,
                                           timestamp_ms=1710412800000)
        assert str(meta.branch_id).startswith('branch-named-')
        assert str(meta.name)           == 'current'
        assert meta.branch_type         == Enum__Branch_Type.NAMED
        assert str(meta.head_ref_id).startswith('ref-')
        assert str(meta.public_key_id).startswith('key-')
        assert str(meta.private_key_id).startswith('key-')
        assert int(meta.created_at)     == 1710412800000

    def test_create_clone_branch(self):
        meta = self.bm.create_clone_branch(self.tmp_dir, 'local', self.read_key,
                                           creator_branch_id='branch-named-a1b2c3d4',
                                           timestamp_ms=1710412800000)
        assert str(meta.branch_id).startswith('branch-clone-')
        assert meta.branch_type          == Enum__Branch_Type.CLONE
        assert meta.private_key_id       is None
        assert str(meta.creator_branch)  == 'branch-named-a1b2c3d4'

    def test_save_and_load_branch_index(self):
        named = self.bm.create_named_branch(self.tmp_dir, 'current', self.read_key,
                                            timestamp_ms=1000)
        clone = self.bm.create_clone_branch(self.tmp_dir, 'local', self.read_key,
                                            creator_branch_id=str(named.branch_id),
                                            timestamp_ms=1000)
        index = Schema__Branch_Index(schema='branch_index_v1', branches=[named, clone])
        self.bm.save_branch_index(self.tmp_dir, index, self.read_key)

        index_id = self.bm.find_branch_index_id(self.tmp_dir)
        assert index_id is not None
        loaded = self.bm.load_branch_index(self.tmp_dir, index_id, self.read_key)
        assert len(loaded.branches) == 2

    def test_get_branch_by_id(self):
        named = self.bm.create_named_branch(self.tmp_dir, 'current', self.read_key, timestamp_ms=1000)
        index = Schema__Branch_Index(schema='branch_index_v1', branches=[named])

        found = self.bm.get_branch_by_id(index, str(named.branch_id))
        assert found is not None
        assert str(found.name) == 'current'

        assert self.bm.get_branch_by_id(index, 'branch-named-00000000') is None

    def test_get_branch_by_name(self):
        named = self.bm.create_named_branch(self.tmp_dir, 'current', self.read_key, timestamp_ms=1000)
        index = Schema__Branch_Index(schema='branch_index_v1', branches=[named])

        found = self.bm.get_branch_by_name(index, 'current')
        assert found is not None
        assert self.bm.get_branch_by_name(index, 'missing') is None
