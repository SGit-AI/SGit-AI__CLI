import os
import tempfile
import shutil
from sg_send_cli.objects.Vault__Object_Store import Vault__Object_Store
from sg_send_cli.crypto.Vault__Crypto        import Vault__Crypto


class Test_Vault__Object_Store__V2:

    def setup_method(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.sg_dir  = os.path.join(self.tmp_dir, '.sg_vault')
        os.makedirs(os.path.join(self.sg_dir, 'bare', 'data'), exist_ok=True)
        self.crypto  = Vault__Crypto()
        self.store   = Vault__Object_Store(vault_path=self.sg_dir, crypto=self.crypto, use_v2=True)

    def teardown_method(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_store_and_load(self):
        data      = os.urandom(64)
        object_id = self.store.store(data)
        assert object_id.startswith('obj-')
        loaded = self.store.load(object_id)
        assert loaded == data

    def test_exists(self):
        data      = os.urandom(64)
        object_id = self.store.store(data)
        assert self.store.exists(object_id) is True
        assert self.store.exists('obj-000000000000') is False

    def test_all_object_ids(self):
        self.store.store(os.urandom(32))
        self.store.store(os.urandom(64))
        ids = self.store.all_object_ids()
        assert len(ids) >= 2
        assert all(oid.startswith('obj-') for oid in ids)

    def test_object_count(self):
        self.store.store(os.urandom(32))
        assert self.store.object_count() >= 1

    def test_verify_integrity(self):
        data      = os.urandom(64)
        object_id = self.store.store(data)
        assert self.store.verify_integrity(object_id) is True

    def test_v1_backward_compat_still_works(self):
        v1_store = Vault__Object_Store(vault_path=self.sg_dir, crypto=self.crypto, use_v2=False)
        data      = os.urandom(64)
        v1_id     = v1_store.store(data)
        assert not v1_id.startswith('obj-')
        assert v1_store.exists(v1_id) is True
        assert v1_store.load(v1_id) == data
