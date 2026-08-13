"""Vault__Cache_Repair — the recovery path.

Each test recreates a failure mode repair exists for: drift left by a client that
stopped pushing, orphans whose path an unaware client deleted, corrupt objects,
and duplicate declarations violating one-object-per-path (D4).
"""
import base64
import os
import shutil
import tempfile

from sgit_ai.core.Vault__Sync                       import Vault__Sync
from sgit_ai.core.actions.cache.Vault__Cache_Repair import Vault__Cache_Repair
from sgit_ai.crypto.Vault__Crypto                   import Vault__Crypto
from sgit_ai.network.api.Vault__API__In_Memory      import Vault__API__In_Memory
from sgit_ai.storage.Vault__Storage                 import Vault__Storage
from sgit_ai.storage.Vault__Cache_Manager           import Vault__Cache_Manager
from sgit_ai.safe_types.Enum__Cache_Kind            import Enum__Cache_Kind
from sgit_ai.safe_types.Enum__Cache_Target_Kind     import Enum__Cache_Target_Kind


class _Base:

    def setup_method(self):
        self.tmp     = tempfile.mkdtemp()
        self.vault   = os.path.join(self.tmp, 'vault')
        self.crypto  = Vault__Crypto()
        self.api     = Vault__API__In_Memory().setup()
        self.sync    = Vault__Sync(crypto=self.crypto, api=self.api)
        self.storage = Vault__Storage()
        self.manager = Vault__Cache_Manager(crypto=self.crypto, storage=self.storage)
        self.repair  = Vault__Cache_Repair(crypto=self.crypto, api=self.api)

        init          = self.sync.init(self.vault)
        self.vault_id = init['vault_id']
        self.rk       = self.crypto.derive_keys_from_vault_key(init['vault_key'])['read_key_bytes']

        self._write('pages/home.md', '# Home\n')
        self._write('media/a.txt',   'photo')
        self.commit = self.sync.commit(self.vault, 'initial')['commit_id']
        self.sync.push(self.vault)

    def teardown_method(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write(self, rel, text):
        p = os.path.join(self.vault, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, 'w') as f:
            f.write(text)

    def _seed_value(self, path, content, commit_id):
        cid = self.manager.cache_id(self.rk, self.vault_id, path, Enum__Cache_Kind.VALUE)
        obj = self.manager.build_value(path=path, content=content, commit_id=commit_id,
                                       content_type='text/markdown', content_hash='aabbccddeeff')
        self.manager.save(self.vault, Enum__Cache_Kind.VALUE, cid, obj, self.rk)
        return cid

    def _seed_pointer(self, path, commit_id):
        cid = self.manager.cache_id(self.rk, self.vault_id, path, Enum__Cache_Kind.POINTER)
        obj = self.manager.build_pointer(path=path, target_id='obj-cas-imm-000000000000',
                                         target_kind=Enum__Cache_Target_Kind.TREE,
                                         commit_id=commit_id, content_type='')
        self.manager.save(self.vault, Enum__Cache_Kind.POINTER, cid, obj, self.rk)
        return cid


class Test_Cache_Repair__Nothing_To_Do(_Base):

    def test_no_cache_objects(self):
        r = self.repair.repair(self.vault)
        assert r['checked'] == 0 and r['repaired'] == 0

    def test_current_object_is_left_alone(self):
        # seed an object that already matches the head exactly
        cid = self.manager.cache_id(self.rk, self.vault_id, 'pages/home.md', Enum__Cache_Kind.VALUE)
        entry = {'blob_id': None}
        self._seed_value('pages/home.md', b'# Home\n', self.commit)
        self.repair.repair(self.vault)                       # first pass normalises it
        r = self.repair.repair(self.vault)                   # second pass must be a no-op
        assert r['repaired']  == 0
        assert r['unchanged'] == 1


class Test_Cache_Repair__Drift(_Base):

    def test_stale_object_is_rewritten(self):
        cid = self._seed_value('pages/home.md', b'OLD CONTENT', 'obj-cas-imm-000000000000')
        r   = self.repair.repair(self.vault)
        assert r['repaired'] == 1
        got = self.manager.load(self.vault, Enum__Cache_Kind.VALUE, cid, self.rk)
        assert base64.b64decode(str(got.value_b64)) == b'# Home\n'   # content healed
        assert str(got.commit_id) == self.commit                      # marker healed

    def test_dry_run_changes_nothing(self):
        cid = self._seed_value('pages/home.md', b'OLD CONTENT', 'obj-cas-imm-000000000000')
        r   = self.repair.repair(self.vault, dry_run=True)
        assert r['repaired'] == 1 and r['dry_run'] is True
        got = self.manager.load(self.vault, Enum__Cache_Kind.VALUE, cid, self.rk)
        assert base64.b64decode(str(got.value_b64)) == b'OLD CONTENT'  # untouched

    def test_pointer_drift_is_rewritten(self):
        cid = self._seed_pointer('media', 'obj-cas-imm-000000000000')
        r   = self.repair.repair(self.vault)
        assert r['repaired'] == 1
        got = self.manager.load(self.vault, Enum__Cache_Kind.POINTER, cid, self.rk)
        assert str(got.target_id) != 'obj-cas-imm-000000000000'


class Test_Cache_Repair__Orphans(_Base):

    def test_orphan_is_deleted(self):
        # a cache for a path an unaware client later removed
        cid = self._seed_value('pages/gone.md', b'ghost', self.commit)
        r   = self.repair.repair(self.vault)
        assert r['deleted'] == 1
        assert self.manager.exists(self.vault, Enum__Cache_Kind.VALUE, cid) is False
        assert any(a[0] == 'orphan-deleted' for a in r['actions'])

    def test_corrupt_object_is_dropped(self):
        cid  = self._seed_value('pages/home.md', b'x', self.commit)
        path = self.storage.cache_path(self.vault, 'value', cid)
        with open(path, 'wb') as f:
            f.write(b'not decryptable')
        r = self.repair.repair(self.vault)
        assert r['deleted'] == 1
        assert any(a[0] == 'unreadable-dropped' for a in r['actions'])


class Test_Cache_Repair__Duplicates(_Base):
    """D4 — a path is cached as value OR pointer, never both."""

    def test_duplicate_declaration_is_resolved(self):
        v = self._seed_value('pages/home.md',  b'# Home\n', self.commit)
        p = self.manager.cache_id(self.rk, self.vault_id, 'pages/home.md', Enum__Cache_Kind.POINTER)
        obj = self.manager.build_pointer(path='pages/home.md', target_id='obj-cas-imm-000000000000',
                                         target_kind=Enum__Cache_Target_Kind.BLOB,
                                         commit_id='obj-cas-imm-000000000000', content_type='')
        self.manager.save(self.vault, Enum__Cache_Kind.POINTER, p, obj, self.rk)

        r = self.repair.repair(self.vault)
        assert r['deduped'] == 1
        # the fresh one (matching head) survives; the stale duplicate is dropped
        assert self.manager.exists(self.vault, Enum__Cache_Kind.VALUE,   v) is True
        assert self.manager.exists(self.vault, Enum__Cache_Kind.POINTER, p) is False
        assert any(a[0] == 'duplicate-dropped' for a in r['actions'])

    def test_tie_breaks_to_the_natural_kind_for_a_file(self):
        # both stale => natural kind for a file path is VALUE
        v = self._seed_value('pages/home.md', b'old', 'obj-cas-imm-000000000000')
        p = self.manager.cache_id(self.rk, self.vault_id, 'pages/home.md', Enum__Cache_Kind.POINTER)
        obj = self.manager.build_pointer(path='pages/home.md', target_id='obj-cas-imm-000000000000',
                                         target_kind=Enum__Cache_Target_Kind.BLOB,
                                         commit_id='obj-cas-imm-000000000000', content_type='')
        self.manager.save(self.vault, Enum__Cache_Kind.POINTER, p, obj, self.rk)

        self.repair.repair(self.vault)
        assert self.manager.exists(self.vault, Enum__Cache_Kind.VALUE,   v) is True
        assert self.manager.exists(self.vault, Enum__Cache_Kind.POINTER, p) is False


class Test_Cache_Repair__Publishes(_Base):

    def test_repaired_object_reaches_the_server(self):
        cid = self._seed_value('pages/home.md', b'OLD', 'obj-cas-imm-000000000000')
        self.repair.repair(self.vault)
        file_id = self.manager.file_id(Enum__Cache_Kind.VALUE, cid)
        data    = self.api.batch_read(self.vault_id, [file_id])
        assert data.get(file_id)
        obj = self.manager.decrypt_object(data[file_id], self.rk, Enum__Cache_Kind.VALUE)
        assert base64.b64decode(str(obj.value_b64)) == b'# Home\n'
