"""End-to-end behaviour of the post-ref cache reconcile (contract 08/12 v0 §3).

Exercised through real push cycles against the in-memory API, because the
properties that matter are sequencing ones: caches follow content, track the new
head, are deleted when their path disappears, and never break a push.
"""
import base64
import os
import shutil
import tempfile

from sgit_ai.core.Vault__Sync                    import Vault__Sync
from sgit_ai.crypto.Vault__Crypto                import Vault__Crypto
from sgit_ai.network.api.Vault__API__In_Memory   import Vault__API__In_Memory
from sgit_ai.storage.Vault__Storage              import Vault__Storage
from sgit_ai.storage.Vault__Cache_Manager        import Vault__Cache_Manager
from sgit_ai.safe_types.Enum__Cache_Kind         import Enum__Cache_Kind
from sgit_ai.safe_types.Enum__Cache_Target_Kind  import Enum__Cache_Target_Kind


class _Base:

    def setup_method(self):
        self.tmp     = tempfile.mkdtemp()
        self.vault   = os.path.join(self.tmp, 'vault')
        self.crypto  = Vault__Crypto()
        self.api     = Vault__API__In_Memory().setup()
        self.sync    = Vault__Sync(crypto=self.crypto, api=self.api)
        self.storage = Vault__Storage()
        self.manager = Vault__Cache_Manager(crypto=self.crypto, storage=self.storage)

        init = self.sync.init(self.vault)
        self.vault_key = init['vault_key']
        self.vault_id  = init['vault_id']
        keys           = self.crypto.derive_keys_from_vault_key(self.vault_key)
        self.rk        = keys['read_key_bytes']

        self._write('pages/home.md',  '# Home\n')
        self._write('media/a.txt',    'photo-a')
        self.sync.commit(self.vault, 'initial')
        self.sync.push(self.vault)

    def teardown_method(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write(self, rel, text):
        p = os.path.join(self.vault, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, 'w') as f:
            f.write(text)

    def _cid(self, path, kind):
        return self.manager.cache_id(self.rk, self.vault_id, path, kind)

    def _seed_value(self, path, content, commit_id='obj-cas-imm-000000000000'):
        cid = self._cid(path, Enum__Cache_Kind.VALUE)
        obj = self.manager.build_value(path=path, content=content, commit_id=commit_id,
                                       content_type='text/markdown', content_hash='aabbccddeeff')
        self.manager.save(self.vault, Enum__Cache_Kind.VALUE, cid, obj, self.rk)
        return cid

    def _seed_pointer(self, path, commit_id='obj-cas-imm-000000000000'):
        cid = self._cid(path, Enum__Cache_Kind.POINTER)
        obj = self.manager.build_pointer(path=path, target_id='obj-cas-imm-000000000000',
                                         target_kind=Enum__Cache_Target_Kind.TREE,
                                         commit_id=commit_id, content_type='')
        self.manager.save(self.vault, Enum__Cache_Kind.POINTER, cid, obj, self.rk)
        return cid


class Test_Cache_Reconcile__No_Cache(_Base):

    def test_push_without_cache_is_a_noop(self):
        self._write('pages/home.md', '# Home v2\n')
        self.sync.commit(self.vault, 'edit')
        r = self.sync.push(self.vault)
        assert r['status']        == 'pushed'
        assert r['cache_updated'] == 0
        assert r['cache_deleted'] == 0


class Test_Cache_Reconcile__Value(_Base):

    def test_value_cache_tracks_new_content_and_head(self):
        cid = self._seed_value('pages/home.md', b'# Home\n')
        self._write('pages/home.md', '# Home v2\n')
        c = self.sync.commit(self.vault, 'edit')
        r = self.sync.push(self.vault)

        assert r['cache_updated'] >= 1
        got = self.manager.load(self.vault, Enum__Cache_Kind.VALUE, cid, self.rk)
        assert base64.b64decode(str(got.value_b64)) == b'# Home v2\n'    # content followed
        assert str(got.commit_id) == c['commit_id']                      # freshness marker moved

    def test_value_cache_uploaded_to_server(self):
        cid = self._seed_value('pages/home.md', b'# Home\n')
        self._write('pages/home.md', '# Home v3\n')
        self.sync.commit(self.vault, 'edit')
        self.sync.push(self.vault)

        file_id = self.manager.file_id(Enum__Cache_Kind.VALUE, cid)
        data    = self.api.batch_read(self.vault_id, [file_id])
        assert data.get(file_id), 'cache object was not published to the server'
        obj = self.manager.decrypt_object(data[file_id], self.rk, Enum__Cache_Kind.VALUE)
        assert base64.b64decode(str(obj.value_b64)) == b'# Home v3\n'

    def test_deleted_path_removes_its_cache(self):
        cid = self._seed_value('pages/home.md', b'# Home\n')
        os.remove(os.path.join(self.vault, 'pages/home.md'))
        self.sync.commit(self.vault, 'delete page', allow_deletions=True)
        r = self.sync.push(self.vault)

        assert r['cache_deleted'] >= 1
        assert self.manager.exists(self.vault, Enum__Cache_Kind.VALUE, cid) is False


class Test_Cache_Reconcile__Pointer(_Base):

    def test_folder_pointer_resolves_to_tree_id(self):
        cid = self._seed_pointer('media')
        self._write('media/b.txt', 'photo-b')
        self.sync.commit(self.vault, 'add photo')
        r = self.sync.push(self.vault)

        assert r['cache_updated'] >= 1
        got = self.manager.load(self.vault, Enum__Cache_Kind.POINTER, cid, self.rk)
        assert got.target_kind == Enum__Cache_Target_Kind.TREE
        assert str(got.target_id).startswith('obj-cas-imm-')
        assert str(got.target_id) != 'obj-cas-imm-000000000000'          # actually resolved

    def test_file_pointer_resolves_to_blob_id(self):
        path = 'media/a.txt'
        cid  = self._cid(path, Enum__Cache_Kind.POINTER)
        obj  = self.manager.build_pointer(path=path, target_id='obj-cas-imm-000000000000',
                                          target_kind=Enum__Cache_Target_Kind.BLOB,
                                          commit_id='obj-cas-imm-000000000000', content_type='')
        self.manager.save(self.vault, Enum__Cache_Kind.POINTER, cid, obj, self.rk)

        self._write('media/a.txt', 'photo-a-v2')
        self.sync.commit(self.vault, 'edit photo')
        self.sync.push(self.vault)

        got = self.manager.load(self.vault, Enum__Cache_Kind.POINTER, cid, self.rk)
        assert got.target_kind == Enum__Cache_Target_Kind.BLOB
        assert str(got.target_id) != 'obj-cas-imm-000000000000'


class Test_Cache_Reconcile__Fail_Soft(_Base):

    def test_push_still_succeeds_when_the_cache_layer_breaks(self):
        # The §3 invariant: content and ref are durable before the cache runs, so a
        # cache failure must degrade to staleness, never fail the push.
        self._seed_value('pages/home.md', b'# Home\n')
        self._write('pages/home.md', '# Home v4\n')
        self.sync.commit(self.vault, 'edit')

        import sgit_ai.core.actions.push.Vault__Sync__Push as push_mod
        original = push_mod.Vault__Sync__Push._rebuild_cache_object
        push_mod.Vault__Sync__Push._rebuild_cache_object = \
            lambda *a, **k: (_ for _ in ()).throw(RuntimeError('boom'))
        try:
            r = self.sync.push(self.vault)
        finally:
            push_mod.Vault__Sync__Push._rebuild_cache_object = original

        assert r['status']        == 'pushed'        # push survived
        assert r['cache_updated'] == 0               # cache simply lagged
