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


class Test_Vault__Cache_Manager__Tombstones(_Base):
    """`cache rm` records intent here; push/repair honour and clear it."""

    def setup_method(self):
        super().setup_method()
        os.makedirs(self.storage.local_dir(self.work), exist_ok=True)

    def test_add_and_list(self):
        cid = self.mgr.cache_id(self.rk, self.vid, 'a.txt', Enum__Cache_Kind.VALUE)
        self.mgr.add_tombstone(self.work, Enum__Cache_Kind.VALUE, cid, 'a.txt')
        assert self.mgr.tombstoned_ids(self.work) == {(Enum__Cache_Kind.VALUE, cid)}

    def test_add_is_idempotent(self):
        cid = self.mgr.cache_id(self.rk, self.vid, 'a.txt', Enum__Cache_Kind.VALUE)
        self.mgr.add_tombstone(self.work, Enum__Cache_Kind.VALUE, cid, 'a.txt')
        self.mgr.add_tombstone(self.work, Enum__Cache_Kind.VALUE, cid, 'a.txt')
        assert len(self.mgr.load_tombstones(self.work).removed) == 1

    def test_clear_removes_only_named_ids(self):
        v = self.mgr.cache_id(self.rk, self.vid, 'a.txt', Enum__Cache_Kind.VALUE)
        p = self.mgr.cache_id(self.rk, self.vid, 'dir',   Enum__Cache_Kind.POINTER)
        self.mgr.add_tombstone(self.work, Enum__Cache_Kind.VALUE,   v, 'a.txt')
        self.mgr.add_tombstone(self.work, Enum__Cache_Kind.POINTER, p, 'dir')
        self.mgr.clear_tombstones(self.work, {(Enum__Cache_Kind.VALUE, v)})
        assert self.mgr.tombstoned_ids(self.work) == {(Enum__Cache_Kind.POINTER, p)}

    def test_empty_store_removes_the_file(self):
        cid = self.mgr.cache_id(self.rk, self.vid, 'a.txt', Enum__Cache_Kind.VALUE)
        self.mgr.add_tombstone(self.work, Enum__Cache_Kind.VALUE, cid, 'a.txt')
        self.mgr.clear_tombstones(self.work, {(Enum__Cache_Kind.VALUE, cid)})
        assert not os.path.isfile(self.mgr.tombstones_path(self.work))

    def test_corrupt_tombstone_file_is_tolerated(self):
        with open(self.mgr.tombstones_path(self.work), 'w') as f:
            f.write('not json at all')
        assert self.mgr.tombstoned_ids(self.work) == set()


class Test_Vault__Cache_Manager__Classify(_Base):
    """The undecryptable / unparseable distinction repair depends on (M2)."""

    def test_ok(self):
        obj = self.mgr.build_value('a.txt', b'x', 'obj-cas-imm-aaaaaaaaaaaa',
                                   'text/plain', 'aabbccddeeff')
        blob = self.mgr.encrypt_object(obj, self.rk)
        got, status = self.mgr.classify_ciphertext(blob, self.rk, Enum__Cache_Kind.VALUE)
        assert status == 'ok' and str(got.path) == 'a.txt'

    def test_undecryptable(self):
        got, status = self.mgr.classify_ciphertext(b'garbage bytes here', self.rk,
                                                   Enum__Cache_Kind.VALUE)
        assert (got, status) == (None, 'undecryptable')

    def test_wrong_key_is_undecryptable(self):
        obj  = self.mgr.build_value('a.txt', b'x', 'obj-cas-imm-aaaaaaaaaaaa',
                                    'text/plain', 'aabbccddeeff')
        blob = self.mgr.encrypt_object(obj, self.rk)
        other = self.crypto.derive_read_key('other-pw', 'zzzz9999')
        got, status = self.mgr.classify_ciphertext(blob, other, Enum__Cache_Kind.VALUE)
        assert (got, status) == (None, 'undecryptable')

    def test_decryptable_but_unparseable(self):
        # decrypts under our key (so a key holder wrote it) but violates the
        # schema — e.g. a newer client whose size field we cannot parse
        blob = self.crypto.encrypt(self.rk, json.dumps(
            {'schema': 'cache_value_v2', 'path': 'a.txt', 'size': 'not-an-int'}).encode())
        got, status = self.mgr.classify_ciphertext(blob, self.rk, Enum__Cache_Kind.VALUE)
        assert (got, status) == (None, 'unparseable')


class Test_Vault__Cache_Manager__Rebuild_Guards(_Base):
    """Size and missing-blob guards in rebuild_for_path (review 08/14 H1/H2/#5)."""

    def _flat(self, blob_id='obj-cas-imm-aaaaaaaaaaaa'):
        return {'a.txt': {'blob_id': blob_id, 'size': 1, 'content_type': 'text/plain',
                          'content_hash': 'aabbccddeeff'}}

    def test_missing_blob_raises_the_specific_error(self):
        from sgit_ai.storage.Vault__Cache_Manager import Vault__Cache_Blob_Missing_Error
        store = Vault__Object_Store(vault_path=os.path.join(self.work, '.sg_vault'),
                                    crypto=self.crypto)
        try:
            self.mgr.rebuild_for_path(kind=Enum__Cache_Kind.VALUE, path='a.txt',
                                      commit_id='obj-cas-imm-cccccccccccc', tree_id='t',
                                      flat=self._flat(), obj_store=store, sub_tree=None,
                                      read_key=self.rk)
            assert False, 'expected Vault__Cache_Blob_Missing_Error'
        except Vault__Cache_Blob_Missing_Error:
            pass

    def test_blob_fetcher_rescues_a_missing_blob(self):
        store   = Vault__Object_Store(vault_path=os.path.join(self.work, '.sg_vault'),
                                      crypto=self.crypto)
        fetched = self.crypto.encrypt(self.rk, b'from the server')
        obj = self.mgr.rebuild_for_path(kind=Enum__Cache_Kind.VALUE, path='a.txt',
                                        commit_id='obj-cas-imm-cccccccccccc', tree_id='t',
                                        flat=self._flat(), obj_store=store, sub_tree=None,
                                        read_key=self.rk,
                                        blob_fetcher=lambda bid: fetched)
        import base64
        assert base64.b64decode(str(obj.value_b64)) == b'from the server'

    def test_value_grown_past_the_cap_rebuilds_to_none(self):
        from sgit_ai.storage.Vault__Cache_Manager import CACHE_VALUE_HARD_CAP
        store = Vault__Object_Store(vault_path=os.path.join(self.work, '.sg_vault'),
                                    crypto=self.crypto)
        big   = self.crypto.encrypt(self.rk, b'x' * (CACHE_VALUE_HARD_CAP + 1))
        obj = self.mgr.rebuild_for_path(kind=Enum__Cache_Kind.VALUE, path='a.txt',
                                        commit_id='obj-cas-imm-cccccccccccc', tree_id='t',
                                        flat=self._flat(), obj_store=store, sub_tree=None,
                                        read_key=self.rk,
                                        blob_fetcher=lambda bid: big)
        assert obj is None                       # cannot fit a batch write — drop it

    def test_pointer_for_a_file_larger_than_100mb_builds(self):
        # Safe_UInt__File_Size capped at 100 MB and made this raise (H1)
        obj = self.mgr.build_pointer(path='video.mp4', target_id='obj-cas-imm-dddddddddddd',
                                     target_kind=Enum__Cache_Target_Kind.BLOB,
                                     commit_id='obj-cas-imm-cccccccccccc',
                                     content_type='video/mp4',
                                     size=150 * 1024 * 1024, content_hash='aabbccddeeff')
        assert int(obj.size) == 150 * 1024 * 1024


class Test_Vault__Cache_Manager__Resolve_Duplicates(_Base):
    """The shared D4 rule (push reconcile + repair use the same code)."""

    def _pair(self, path='a.txt', value_commit='obj-cas-imm-aaaaaaaaaaaa',
              pointer_commit='obj-cas-imm-aaaaaaaaaaaa'):
        v_id = self.mgr.cache_id(self.rk, self.vid, path, Enum__Cache_Kind.VALUE)
        p_id = self.mgr.cache_id(self.rk, self.vid, path, Enum__Cache_Kind.POINTER)
        v = self.mgr.build_value(path, b'x', value_commit, 'text/plain', 'aabbccddeeff')
        p = self.mgr.build_pointer(path, 'obj-cas-imm-bbbbbbbbbbbb',
                                   Enum__Cache_Target_Kind.BLOB, pointer_commit, '')
        return [(Enum__Cache_Kind.VALUE, v_id, v), (Enum__Cache_Kind.POINTER, p_id, p)]

    def test_fresh_object_wins(self):
        head   = 'obj-cas-imm-ffffffffffff'
        loaded = self._pair(pointer_commit=head)               # pointer fresh, value stale
        drops  = self.mgr.resolve_duplicates(loaded, {'a.txt': {}}, head)
        assert [(k.value, p) for k, _c, p in drops] == [('value', 'a.txt')]

    def test_tie_breaks_to_natural_kind(self):
        loaded = self._pair()                                  # both stale, path is a file
        drops  = self.mgr.resolve_duplicates(loaded, {'a.txt': {}}, 'obj-cas-imm-ffffffffffff')
        assert [k.value for k, _c, _p in drops] == ['pointer'] # value natural for a file

    def test_snw_preferred_over_muw_same_kind(self):
        # M4: the old sort kept muw (sorts first), stranding snw-probing readers
        snw_id = self.mgr.cache_id(self.rk, self.vid, 'a.txt', Enum__Cache_Kind.VALUE)
        muw_id = self.mgr.cache_id(self.rk, self.vid, 'a.txt', Enum__Cache_Kind.VALUE,
                                   Enum__Cache_Mutability.MUW)
        obj    = self.mgr.build_value('a.txt', b'x', 'obj-cas-imm-aaaaaaaaaaaa',
                                      'text/plain', 'aabbccddeeff')
        loaded = [(Enum__Cache_Kind.VALUE, muw_id, obj), (Enum__Cache_Kind.VALUE, snw_id, obj)]
        drops  = self.mgr.resolve_duplicates(loaded, {'a.txt': {}}, 'obj-cas-imm-ffffffffffff')
        assert [c for _k, c, _p in drops] == [muw_id]          # snw survives

    def test_singletons_are_untouched(self):
        loaded = self._pair()[:1]
        assert self.mgr.resolve_duplicates(loaded, {'a.txt': {}}, 'x') == []
