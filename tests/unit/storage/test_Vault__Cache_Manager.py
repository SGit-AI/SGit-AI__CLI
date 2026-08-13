import json
import os
import shutil
import tempfile

from sgit_ai.crypto.Vault__Crypto                import Vault__Crypto
from sgit_ai.storage.Vault__Storage              import Vault__Storage
from sgit_ai.storage.Vault__Cache_Manager        import Vault__Cache_Manager
from sgit_ai.storage.Vault__Object_Store         import Vault__Object_Store
from sgit_ai.safe_types.Enum__Cache_Kind         import Enum__Cache_Kind
from sgit_ai.safe_types.Enum__Cache_Mutability   import Enum__Cache_Mutability
from sgit_ai.safe_types.Enum__Cache_Target_Kind  import Enum__Cache_Target_Kind


class _Base:

    def setup_method(self):
        self.tmp     = tempfile.mkdtemp()
        self.work    = os.path.join(self.tmp, 'vault')
        self.storage = Vault__Storage()
        self.storage.create_bare_structure(self.work)
        self.crypto  = Vault__Crypto()
        self.mgr     = Vault__Cache_Manager(crypto=self.crypto, storage=self.storage)
        self.rk      = self.crypto.derive_read_key('pw', 'abcd1234')
        self.vid     = 'abcd1234'

    def teardown_method(self):
        shutil.rmtree(self.tmp, ignore_errors=True)


class Test_Vault__Cache_Manager__Ids(_Base):

    def test_cache_id_shape(self):
        cid = self.mgr.cache_id(self.rk, self.vid, 'a/b.txt', Enum__Cache_Kind.VALUE)
        assert cid.startswith('cch-pid-snw-') and len(cid) == len('cch-pid-snw-') + 12

    def test_muw_label(self):
        cid = self.mgr.cache_id(self.rk, self.vid, 'a/b.txt', Enum__Cache_Kind.VALUE,
                                Enum__Cache_Mutability.MUW)
        assert cid.startswith('cch-pid-muw-')

    def test_label_does_not_change_the_tail(self):
        snw = self.mgr.cache_id(self.rk, self.vid, 'a/b.txt', Enum__Cache_Kind.VALUE)
        muw = self.mgr.cache_id(self.rk, self.vid, 'a/b.txt', Enum__Cache_Kind.VALUE,
                                Enum__Cache_Mutability.MUW)
        assert snw.rsplit('-', 1)[1] == muw.rsplit('-', 1)[1]

    def test_kinds_are_independent(self):
        v = self.mgr.cache_id(self.rk, self.vid, 'a/b.txt', Enum__Cache_Kind.VALUE)
        p = self.mgr.cache_id(self.rk, self.vid, 'a/b.txt', Enum__Cache_Kind.POINTER)
        assert v.rsplit('-', 1)[1] != p.rsplit('-', 1)[1]

    def test_file_id_wire_paths(self):
        cid = self.mgr.cache_id(self.rk, self.vid, 'a/b.txt', Enum__Cache_Kind.VALUE)
        assert self.mgr.file_id(Enum__Cache_Kind.VALUE,   cid) == f'bare/cache/value/{cid}'
        assert self.mgr.file_id(Enum__Cache_Kind.POINTER, cid) == f'bare/cache/pointer/{cid}'

    def test_matches_contract_vector(self):
        # contract §4.1 Chain A, routed through the manager's assembly
        rk  = bytes.fromhex('000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f')
        cid = self.mgr.cache_id(rk, '7y6uk6gj', 'pages/home.md', Enum__Cache_Kind.VALUE)
        assert cid == 'cch-pid-snw-4aa53f5467b6'


class Test_Vault__Cache_Manager__Round_Trip(_Base):

    def test_value_save_load(self):
        cid = self.mgr.cache_id(self.rk, self.vid, 'pages/home.md', Enum__Cache_Kind.VALUE)
        obj = self.mgr.build_value(path='pages/home.md', content=b'# Home\n',
                                   commit_id='obj-cas-imm-aaaaaaaaaaaa',
                                   content_type='text/markdown', content_hash='c8e5a6f1b2d3')
        self.mgr.save(self.work, Enum__Cache_Kind.VALUE, cid, obj, self.rk)
        got = self.mgr.load(self.work, Enum__Cache_Kind.VALUE, cid, self.rk)
        assert got.json() == obj.json()
        assert str(got.path) == 'pages/home.md'
        assert int(got.size) == 7

    def test_pointer_save_load(self):
        cid = self.mgr.cache_id(self.rk, self.vid, 'media/photos', Enum__Cache_Kind.POINTER)
        obj = self.mgr.build_pointer(path='media/photos', target_id='obj-cas-imm-bbbbbbbbbbbb',
                                     target_kind=Enum__Cache_Target_Kind.TREE,
                                     commit_id='obj-cas-imm-aaaaaaaaaaaa',
                                     content_type='application/x-directory')
        self.mgr.save(self.work, Enum__Cache_Kind.POINTER, cid, obj, self.rk)
        got = self.mgr.load(self.work, Enum__Cache_Kind.POINTER, cid, self.rk)
        assert got.json() == obj.json()
        assert got.target_kind == Enum__Cache_Target_Kind.TREE

    def test_stored_bytes_are_ciphertext(self):
        cid = self.mgr.cache_id(self.rk, self.vid, 'secret.txt', Enum__Cache_Kind.VALUE)
        obj = self.mgr.build_value(path='secret.txt', content=b'TOP SECRET VALUE',
                                   commit_id='obj-cas-imm-aaaaaaaaaaaa',
                                   content_type='text/plain', content_hash='aabbccddeeff')
        p = self.mgr.save(self.work, Enum__Cache_Kind.VALUE, cid, obj, self.rk)
        with open(p, 'rb') as f:
            raw = f.read()
        assert b'TOP SECRET VALUE' not in raw          # content encrypted
        assert b'secret.txt'       not in raw          # path encrypted too

    def test_random_iv__same_object_yields_different_ciphertext(self):
        # contract §5: cache objects MUST NOT be deterministically encrypted
        cid = self.mgr.cache_id(self.rk, self.vid, 'a.txt', Enum__Cache_Kind.VALUE)
        obj = self.mgr.build_value(path='a.txt', content=b'x', commit_id='obj-cas-imm-aaaaaaaaaaaa',
                                   content_type='text/plain', content_hash='aabbccddeeff')
        assert self.mgr.encrypt_object(obj, self.rk) != self.mgr.encrypt_object(obj, self.rk)

    def test_load_missing_returns_none(self):
        assert self.mgr.load(self.work, Enum__Cache_Kind.VALUE, 'cch-pid-snw-000000000000', self.rk) is None


class Test_Vault__Cache_Manager__Mutation(_Base):
    """The behaviour D10 exists to protect: a cache object is updated in place."""

    def _obj(self, content):
        return self.mgr.build_value(path='k.json', content=content,
                                    commit_id='obj-cas-imm-aaaaaaaaaaaa',
                                    content_type='application/json', content_hash='aabbccddeeff')

    def test_overwrite_same_id_with_different_content_succeeds(self):
        cid = self.mgr.cache_id(self.rk, self.vid, 'k.json', Enum__Cache_Kind.VALUE)
        self.mgr.save(self.work, Enum__Cache_Kind.VALUE, cid, self._obj(b'v1'), self.rk)
        self.mgr.save(self.work, Enum__Cache_Kind.VALUE, cid, self._obj(b'v2'), self.rk)   # must not raise
        import base64
        got = self.mgr.load(self.work, Enum__Cache_Kind.VALUE, cid, self.rk)
        assert base64.b64decode(str(got.value_b64)) == b'v2'

    def test_object_store_would_have_rejected_this(self):
        # Documents WHY D10 exists: the CAS guard rejects same-id/different-bytes.
        from sgit_ai.storage.Vault__Object_Store import Vault__Object_Collision_Error
        store = Vault__Object_Store(vault_path=self.storage.sg_vault_dir(self.work), crypto=self.crypto)
        store.store_raw('obj-cas-imm-aaaaaaaaaaaa', b'first')
        try:
            store.store_raw('obj-cas-imm-aaaaaaaaaaaa', b'second')
            assert False, 'expected the object store to reject a differing rewrite'
        except Vault__Object_Collision_Error:
            pass

    def test_delete(self):
        cid = self.mgr.cache_id(self.rk, self.vid, 'k.json', Enum__Cache_Kind.VALUE)
        self.mgr.save(self.work, Enum__Cache_Kind.VALUE, cid, self._obj(b'v'), self.rk)
        assert self.mgr.exists(self.work, Enum__Cache_Kind.VALUE, cid) is True
        assert self.mgr.delete(self.work, Enum__Cache_Kind.VALUE, cid) is True
        assert self.mgr.exists(self.work, Enum__Cache_Kind.VALUE, cid) is False
        assert self.mgr.delete(self.work, Enum__Cache_Kind.VALUE, cid) is False   # idempotent


class Test_Vault__Cache_Manager__Enumeration(_Base):

    def test_list_all_empty_by_default(self):
        assert self.mgr.list_all(self.work) == []

    def test_list_all_finds_both_kinds(self):
        v = self.mgr.cache_id(self.rk, self.vid, 'a.txt', Enum__Cache_Kind.VALUE)
        p = self.mgr.cache_id(self.rk, self.vid, 'dir',   Enum__Cache_Kind.POINTER)
        self.mgr.save(self.work, Enum__Cache_Kind.VALUE, v,
                      self.mgr.build_value('a.txt', b'x', 'obj-cas-imm-aaaaaaaaaaaa',
                                           'text/plain', 'aabbccddeeff'), self.rk)
        self.mgr.save(self.work, Enum__Cache_Kind.POINTER, p,
                      self.mgr.build_pointer('dir', 'obj-cas-imm-bbbbbbbbbbbb',
                                             Enum__Cache_Target_Kind.TREE,
                                             'obj-cas-imm-aaaaaaaaaaaa', 'application/x-directory'),
                      self.rk)
        found = self.mgr.list_all(self.work)
        assert (Enum__Cache_Kind.VALUE, v)   in found
        assert (Enum__Cache_Kind.POINTER, p) in found

    def test_missing_cache_dir_is_tolerated(self):
        # old vaults have no bare/cache/ at all — must not raise
        shutil.rmtree(self.storage.bare_cache_dir(self.work))
        assert self.mgr.list_all(self.work) == []
