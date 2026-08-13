"""Collision safeguard: store() must never silently overwrite a different
ciphertext sharing a 48-bit object id."""
import os
import shutil
import tempfile
import pytest

from sgit_ai.crypto.Vault__Crypto        import Vault__Crypto
from sgit_ai.storage.Vault__Object_Store import Vault__Object_Store, Vault__Object_Collision_Error


class Test_Vault__Object_Store__Collision:

    def setup_method(self):
        self.tmp   = tempfile.mkdtemp()
        self.sg    = os.path.join(self.tmp, '.sg_vault')
        os.makedirs(os.path.join(self.sg, 'bare', 'data'), exist_ok=True)
        self.store = Vault__Object_Store(vault_path=self.sg, crypto=Vault__Crypto())

    def teardown_method(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_store_is_idempotent_for_identical_content(self):
        oid1 = self.store.store(b'hello world')
        oid2 = self.store.store(b'hello world')          # same bytes, same id
        assert oid1 == oid2
        assert self.store.load(oid1) == b'hello world'

    def test_store_raises_on_genuine_collision(self):
        oid  = self.store.store(b'original content')
        # Simulate a 48-bit collision: force different bytes at the same id path.
        path = self.store.object_path(oid)
        with open(path, 'wb') as f:
            f.write(b'DIFFERENT content that maps to the same truncated id')
        with pytest.raises(Vault__Object_Collision_Error):
            self.store.store(b'original content')         # recompute id == oid, bytes differ on disk
        # the on-disk (foreign) content is not clobbered
        with open(path, 'rb') as f:
            assert f.read() == b'DIFFERENT content that maps to the same truncated id'

    def test_store_raw_raises_on_collision(self):
        self.store.store_raw('obj-cas-imm-aaaaaaaaaaaa', b'first')
        with pytest.raises(Vault__Object_Collision_Error):
            self.store.store_raw('obj-cas-imm-aaaaaaaaaaaa', b'second')

    def test_store_raw_idempotent_identical(self):
        self.store.store_raw('obj-cas-imm-bbbbbbbbbbbb', b'same')
        self.store.store_raw('obj-cas-imm-bbbbbbbbbbbb', b'same')   # no raise
        assert self.store.load('obj-cas-imm-bbbbbbbbbbbb') == b'same'
