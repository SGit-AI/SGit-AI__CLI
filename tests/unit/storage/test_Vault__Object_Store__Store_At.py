"""Tests for Vault__Object_Store.store_at() — force=False no-overwrite guard."""
import os
import shutil
import tempfile

from sgit_ai.crypto.Vault__Crypto        import Vault__Crypto
from sgit_ai.safe_types.Safe_Str__Vault_Path import Safe_Str__Vault_Path
from sgit_ai.storage.Vault__Object_Store import Vault__Object_Store


def _make_store(tmp_dir: str) -> Vault__Object_Store:
    sg_dir = os.path.join(tmp_dir, '.sg_vault')
    return Vault__Object_Store(vault_path=Safe_Str__Vault_Path(sg_dir),
                               crypto=Vault__Crypto())


class Test_Vault__Object_Store__Store_At:

    def setup_method(self):
        self.tmp = tempfile.mkdtemp()
        self.store = _make_store(self.tmp)

    def teardown_method(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_store_at_writes_ciphertext(self):
        obj_id = 'obj-cas-imm-deadbeef0001'
        self.store.store_at(obj_id, b'ciphertext-v1')
        assert self.store.load(obj_id) == b'ciphertext-v1'

    def test_store_at_returns_object_id(self):
        obj_id = 'obj-cas-imm-deadbeef0002'
        result = self.store.store_at(obj_id, b'data')
        assert result == obj_id

    def test_store_at_does_not_overwrite_by_default(self):
        obj_id = 'obj-cas-imm-deadbeef0003'
        self.store.store_at(obj_id, b'original')
        self.store.store_at(obj_id, b'updated')        # force=False default
        assert self.store.load(obj_id) == b'original'  # unchanged

    def test_store_at_overwrites_with_force_true(self):
        obj_id = 'obj-cas-imm-deadbeef0004'
        self.store.store_at(obj_id, b'original')
        self.store.store_at(obj_id, b'updated', force=True)
        assert self.store.load(obj_id) == b'updated'

    def test_store_at_does_not_validate_hash(self):
        obj_id   = 'obj-cas-imm-deadbeef0005'
        junk     = b'bytes that do not hash to deadbeef0005'
        self.store.store_at(obj_id, junk)
        assert self.store.load(obj_id) == junk          # no ValidationError raised

    def test_store_at_creates_parent_directories(self):
        obj_id = 'obj-cas-imm-deadbeef0006'
        self.store.store_at(obj_id, b'hello')
        assert self.store.exists(obj_id)
