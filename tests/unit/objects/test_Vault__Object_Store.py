import os
import tempfile
from sg_send_cli.objects.Vault__Object_Store import Vault__Object_Store
from sg_send_cli.crypto.Vault__Crypto        import Vault__Crypto


class Test_Vault__Object_Store:

    def setup_method(self):
        self.tmp_dir    = tempfile.mkdtemp()
        self.vault_path = self.tmp_dir
        self.crypto     = Vault__Crypto()
        self.store      = Vault__Object_Store(vault_path=self.vault_path, crypto=self.crypto)

    def test_store_returns_self_describing_id(self):
        ciphertext = b'some encrypted data'
        object_id  = self.store.store(ciphertext)
        assert object_id.startswith('obj-cas-imm-')
        assert len(object_id) == 24  # 12 prefix + 12 hex

    def test_store_and_load_round_trip(self):
        ciphertext = b'test ciphertext bytes'
        object_id  = self.store.store(ciphertext)
        loaded     = self.store.load(object_id)
        assert loaded == ciphertext

    def test_store_uses_bare_data_directory(self):
        ciphertext = b'bare data test'
        object_id  = self.store.store(ciphertext)
        path       = self.store.object_path(object_id)
        assert '/bare/data/' in path
        assert path.endswith(object_id)
        assert os.path.isfile(path)

    def test_exists_true_after_store(self):
        ciphertext = b'exists test'
        object_id  = self.store.store(ciphertext)
        assert self.store.exists(object_id) is True

    def test_exists_false_for_missing(self):
        assert self.store.exists('obj-cas-imm-aabbccddeeff') is False

    def test_deterministic_id(self):
        ciphertext = b'deterministic test'
        id_1 = self.store.store(ciphertext)
        id_2 = self.crypto.compute_object_id(ciphertext)
        assert id_1 == id_2

    def test_different_data_different_ids(self):
        id_1 = self.store.store(b'data one')
        id_2 = self.store.store(b'data two')
        assert id_1 != id_2

    def test_all_object_ids_empty(self):
        assert self.store.all_object_ids() == []

    def test_all_object_ids_after_store(self):
        self.store.store(b'object 1')
        self.store.store(b'object 2')
        ids = self.store.all_object_ids()
        assert len(ids) == 2
        assert all(i.startswith('obj-cas-imm-') for i in ids)

    def test_object_count(self):
        assert self.store.object_count() == 0
        self.store.store(b'counting')
        assert self.store.object_count() == 1

    def test_total_size(self):
        data = b'size test data'
        self.store.store(data)
        assert self.store.total_size() == len(data)

    def test_verify_integrity_valid(self):
        ciphertext = b'integrity test'
        object_id  = self.store.store(ciphertext)
        assert self.store.verify_integrity(object_id) is True

    def test_verify_integrity_missing(self):
        assert self.store.verify_integrity('obj-cas-imm-aabbccddeeff') is False

    def test_verify_integrity_corrupted(self):
        ciphertext = b'will be corrupted'
        object_id  = self.store.store(ciphertext)
        path       = self.store.object_path(object_id)
        with open(path, 'wb') as f:
            f.write(b'corrupted data!!')
        assert self.store.verify_integrity(object_id) is False

    def test_object_path_format(self):
        path = self.store.object_path('obj-cas-imm-a1b2c3d4e5f6')
        assert path.endswith(os.path.join('bare', 'data', 'obj-cas-imm-a1b2c3d4e5f6'))

    def test_store_raw(self):
        object_id = 'obj-cas-imm-customid12345'
        data      = b'raw store test'
        self.store.store_raw(object_id, data)
        assert self.store.exists(object_id)
        assert self.store.load(object_id) == data
