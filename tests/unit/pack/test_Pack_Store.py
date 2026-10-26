"""The pack store (dev pack 03 §6, Phase 3; architecture note of 26 Oct §2): a clone made
with --pack-store keeps every data pack it takes in place and reads objects from them by
offset; nothing is extracted into bare/data/. T9: a pack-store clone and an ordinary one
give identical working copies and identical answers from status, log and fsck; a byte
flipped in a kept pack is caught on the first read of that object. Also: every member is
verified at intake and a bad one refused (never "here"); a push from a pack-store clone
takes its own new objects into the uploaded pack and drops the loose copies; compaction
swaps the absorbed packs for the snapshot locally; `pack store extract` makes an ordinary
clone; the handle rule; a selective pack-store clone checks files out from the packs."""
import io
import os
import sqlite3
import zipfile

import pytest

from sgit_ai.core.actions.pack.Vault__Packs          import PACK_COMMITS, PACK_SNAPSHOTS
from sgit_ai.core.actions.pack.Vault__Pack_Maintain  import Vault__Pack_Maintain
from sgit_ai.objects.Vault__Inspector                import Vault__Inspector
from sgit_ai.storage.Vault__Object_Store             import Vault__Object_Store, Vault__Object_Corrupt_Error, Vault__Object_Missing_Error
from sgit_ai.storage.Vault__Pack_Store               import Vault__Pack_Store
from tests._helpers.pack_env                         import Pack__Env
from tests._helpers.vault_test_env                   import TEST_VAULT_KEY

FILES = {'raw/uk/gov/a.txt': b'a\n', 'raw/uk/gov/b.txt': b'bb\n', 'raw/fr/edu/c.txt': b'ccc\n', 'top.md': b'# top\n'}


class Test_Pack_Store:

    def setup_method(self):
        self.env = Pack__Env()
        self.sync, self.a, self.key = self.env.pack_vault(dict(FILES), vault_key=TEST_VAULT_KEY)
        self.env.write(self.a, {'raw/uk/gov/a.txt': b'a changed\n'}); self.sync.commit(self.a, message='p1'); self.sync.push(self.a)

    def _store(self, directory):
        return Vault__Object_Store(vault_path=os.path.join(directory, '.sg_vault'), crypto=self.sync.crypto)

    def _kept(self, directory):
        root = os.path.join(directory, '.sg_vault', 'bare', 'packs')
        return sorted(os.path.relpath(os.path.join(r, f), root).replace(os.sep, '/') for r, _, fs in os.walk(root) for f in fs)

    def _loose(self, directory):
        return self._store(directory).loose_object_ids()

    def _chain(self, sync, directory):
        c = sync._init_components(directory)
        return [(e['message'], e['added'], e['modified'], e['deleted'], e['total_files'])
                for e in Vault__Inspector(crypto=sync.crypto).inspect_commit_chain(directory, read_key=c.read_key, limit=20)]

    # --- T9: identical to an ordinary clone; a flipped byte is caught on read -----------------------------
    def test_a_pack_store_clone_equals_an_ordinary_clone_and_extracts_nothing(self):
        msgs = []
        sync_b, b = self.env.clone(self.key, 'b', pack_store=True, on_progress=lambda k, t, d='': msgs.append(t))
        sync_c, c = self.env.clone(self.key, 'c')
        assert 'Packs kept in place' in msgs and 'Packs extracted' not in msgs
        assert self.env.tree(b) == self.env.tree(c) == self.env.tree(self.a)
        assert self._loose(b) == [] and len(self._kept(b)) == 2                       # the snapshot and one commit pack
        assert self._store(b).all_object_ids() == self._store(c).all_object_ids()
        assert self._store(b).total_size() == self._store(c).total_size()
        assert sync_b.status(b)['clean'] and sync_c.status(c)['clean']
        assert self._chain(sync_b, b) == self._chain(sync_c, c)
        assert sync_b.fsck(b)['ok'] and sync_c.fsck(c)['ok']
        assert sync_b._read_local_config(b, sync_b._init_components(b).storage).pack_store is True

    def test_a_byte_flipped_in_a_kept_pack_is_caught_on_the_first_read(self):
        sync_b, b = self.env.clone(self.key, 'b', pack_store=True)
        sg   = os.path.join(b, '.sg_vault')
        rel  = next(r for r in self._kept(b) if r.startswith('commits/'))
        conn = sqlite3.connect(os.path.join(sg, 'local', 'pack-store.sqlite'))
        oid, offset = conn.execute('SELECT object_id, offset FROM members WHERE rel = ? ORDER BY object_id', (rel,)).fetchone()
        conn.close()
        path = os.path.join(sg, 'bare', 'packs', *rel.split('/'))
        with open(path, 'rb') as f:
            data = bytearray(f.read())
        data[offset + 2] ^= 0x01
        with open(path, 'wb') as f:
            f.write(bytes(data))
        store = self._store(b)
        assert store.exists(oid)
        with pytest.raises(Vault__Object_Corrupt_Error):
            store.load(oid)
        assert isinstance(Vault__Object_Corrupt_Error('x'), Vault__Object_Missing_Error)   # every fail-soft handler applies
        assert store.verify_integrity(oid) is False
        assert sync_b.fsck(b)['ok'] is False                                       # named, as a corrupt loose object is
        others = [o for o in store.all_object_ids() if o != oid]
        assert all(store.verify_integrity(o) for o in others)                       # one object, not the pack

    # --- intake: verified, refused members never "here" ---------------------------------------------------
    def test_a_member_that_fails_its_content_address_is_refused_at_intake_and_the_pack_is_not_recorded(self):
        sync_b, b = self.env.clone(self.key, 'b', pack_store=True)
        self.env.write(self.a, {'raw/fr/edu/d.txt': b'dd\n'}); self.sync.commit(self.a, message='p2'); self.sync.push(self.a)
        from sgit_ai.core.actions.sparse.Vault__Sync__Sparse import Vault__Sync__Sparse
        ca    = self.sync._init_components(self.a)
        head  = Vault__Sync__Sparse(crypto=self.sync.crypto, api=self.env.api)._local_head_commit(self.a, ca)
        entry = next(p for p in self.env.api.packs(str(ca.vault_id), PACK_COMMITS) if head in p)   # the head's pack, not [-1]:
        key   = f'{ca.vault_id}/{entry}'                                                           # same-second names sort by hex
        data  = self.env.api._store[key]
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            names = z.namelist()
        info_name = names[-1]                                                      # path order: the last member is a blob
        tampered = bytearray(data)
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            ho = z.getinfo(info_name).header_offset
        name_len = int.from_bytes(data[ho + 26:ho + 28], 'little'); extra = int.from_bytes(data[ho + 28:ho + 30], 'little')
        tampered[ho + 30 + name_len + extra + 1] ^= 0x01
        self.env.api._store[key] = bytes(tampered)
        bad = info_name.rsplit('/', 1)[-1]
        with pytest.raises(RuntimeError) as err:                                   # the pull says so: the file is not here
            sync_b.pull(b)
        assert 'Pull incomplete' in str(err.value) and bad in str(err.value)
        assert not self._store(b).exists(bad)                                      # refused: never here
        from tests.unit.pack.test_Pack_Vault__Sync import _absorbed
        assert entry.rsplit('/', 1)[-1] not in _absorbed(b)                         # not recorded: fetched again next time
        from sgit_ai.core.actions.pack.Vault__Packs import Vault__Packs
        msgs, cb = [], sync_b._init_components(b)
        r = Vault__Packs(crypto=sync_b.crypto, api=self.env.api).sync_down(b, str(cb.vault_id), cb.read_key,
                                                                          lambda k, t, d='': msgs.append((k, t, d)))
        assert r['refused'] == [bad] and any('failed the integrity check' in t for _, t, _ in msgs)
        assert not self._store(b).exists(bad)

    # --- push, pull and compaction on a pack-store clone -------------------------------------------------------
    def test_a_push_takes_the_clones_new_objects_into_the_kept_pack_and_drops_the_loose_copies(self):
        sync_b, b = self.env.clone(self.key, 'b', pack_store=True)
        self.env.write(b, {'raw/uk/edu/new.txt': b'new\n'}); sync_b.commit(b, message='from b')
        assert len(self._loose(b)) > 0                                              # a clone's own objects stay loose
        sync_b.push(b)
        assert self._loose(b) == [] and len([r for r in self._kept(b) if r.startswith('commits/')]) == 2
        assert sync_b.status(b)['clean'] and sync_b.fsck(b)['ok']
        sync_c, c = self.env.clone(self.key, 'c')
        assert self.env.tree(c)['raw/uk/edu/new.txt'] == b'new\n'

    def test_a_pull_keeps_the_new_pack_in_place(self):
        sync_b, b = self.env.clone(self.key, 'b', pack_store=True)
        self.env.write(self.a, {'raw/fr/edu/d.txt': b'dd\n'}); self.sync.commit(self.a, message='p2'); self.sync.push(self.a)
        sync_b.pull(b)
        assert self.env.tree(b) == self.env.tree(self.a) and self._loose(b) == []
        assert len([r for r in self._kept(b) if r.startswith('commits/')]) == 2

    def test_compaction_by_a_pack_store_clone_swaps_the_absorbed_packs_for_the_snapshot(self):
        sync_b, b = self.env.clone(self.key, 'b', pack_store=True)
        self.env.write(b, {'raw/uk/edu/new.txt': b'new\n'}); sync_b.commit(b, message='from b'); sync_b.push(b)
        msgs = []
        Vault__Pack_Maintain(crypto=sync_b.crypto, api=self.env.api).compact(b, on_progress=lambda k, t, d='': msgs.append((k, t, d)))
        assert any(t == 'Pack store swapped' for _, t, _ in msgs)
        kept = self._kept(b)
        assert len([r for r in kept if r.startswith('snapshots/')]) == 1 and not [r for r in kept if r.startswith('commits/')]
        assert sync_b.status(b)['clean'] and sync_b.fsck(b)['ok']
        store = self._store(b)
        assert all(store.verify_integrity(o) for o in store.all_object_ids())

    def test_a_pack_store_clone_left_behind_by_compaction_takes_the_snapshot_in_place(self):
        sync_b, b = self.env.clone(self.key, 'b', pack_store=True)
        for i in range(2):
            self.env.write(self.a, {f'raw/fr/edu/d{i}.txt': b'dd\n'}); self.sync.commit(self.a, message=f'p{i}'); self.sync.push(self.a)
        Vault__Pack_Maintain(crypto=self.sync.crypto, api=self.env.api).compact(self.a)
        sync_b.pull(b)
        assert self.env.tree(b) == self.env.tree(self.a) and self._loose(b) == []
        assert len([r for r in self._kept(b) if r.startswith('snapshots/')]) == 2

    # --- the store itself ------------------------------------------------------------------------------------------
    def test_remove_pack_keeps_an_object_another_kept_pack_holds_and_closes_the_handle_first(self):
        sync_b, b = self.env.clone(self.key, 'b', pack_store=True)
        self.env.write(b, {'raw/uk/edu/new.txt': b'new\n'}); sync_b.commit(b, message='from b'); sync_b.push(b)
        Vault__Pack_Maintain(crypto=sync_b.crypto, api=self.env.api).compact(b)   # the snapshot holds everything
        self.env.write(self.a, {'raw/fr/edu/d.txt': b'dd\n'}); self.sync.commit(self.a, message='p2'); self.sync.push(self.a)
        sync_b.pull(b)
        store = Vault__Pack_Store(vault_path=os.path.join(b, '.sg_vault'), crypto=sync_b.crypto).setup()
        snapshot = next(p['rel'] for p in store.packs() if p['rel'].startswith('snapshots/'))
        commit   = next(p['rel'] for p in store.packs() if p['rel'].startswith('commits/'))
        only_snap = next(o for o in store.members_of(snapshot) if o not in set(store.members_of(commit)))
        in_commit = next(iter(store.members_of(commit)))
        store.load(only_snap)                                                       # a handle is open on the snapshot
        assert snapshot in store.handles
        store.remove_pack(snapshot)
        assert snapshot not in store.handles and not os.path.isfile(store.pack_path(snapshot))
        assert not store.exists(only_snap) and store.exists(in_commit)              # an object is held by the packs that hold it
        store.close()

    def test_rebuild_recovers_the_table_from_the_kept_packs(self):
        sync_b, b = self.env.clone(self.key, 'b', pack_store=True)
        before = self._store(b).all_object_ids()
        store  = Vault__Pack_Store(vault_path=os.path.join(b, '.sg_vault'), crypto=sync_b.crypto).setup()
        with store.conn:
            store.conn.execute('DELETE FROM members')
        assert store.object_count() == 0
        r = store.rebuild()
        assert r['packs'] == 2 and r['refused'] == [] and store.all_object_ids() == before
        store.close()

    def test_extract_makes_an_ordinary_clone(self):
        sync_b, b = self.env.clone(self.key, 'b', pack_store=True)
        store = Vault__Pack_Store(vault_path=os.path.join(b, '.sg_vault'), crypto=sync_b.crypto).setup()
        before = self._store(b).all_object_ids()
        n = store.extract_all(self._store(b))
        assert n == len(before) and not store.enabled() and self._kept(b) == []
        fresh = Vault__Object_Store(vault_path=os.path.join(b, '.sg_vault'), crypto=sync_b.crypto)
        assert fresh.loose_object_ids() == before and fresh.packs() is None
        assert sync_b.status(b)['clean'] and sync_b.fsck(b)['ok']

    def test_a_selective_pack_store_clone_checks_files_out_from_the_packs(self):
        sync_b, b = self.env.clone(self.key, 'b', pack_store=True, no_checkout=True)
        assert self.env.tree(b) == {} and self._loose(b) == []
        self.env.api.reset_counts()
        r = sync_b.checkout(b, paths=['raw/uk'])
        assert r['written'] == ['raw/uk/gov/a.txt', 'raw/uk/gov/b.txt'] and r['fetched'] == 0
        assert self.env.api.requests() == 0 or not [f for f in self.env.api.requested_ids if f.startswith('bare/data/')]
        assert self.env.tree(b) == {'raw/uk/gov/a.txt': b'a changed\n', 'raw/uk/gov/b.txt': b'bb\n'}

    def test_the_table_is_private_and_a_clone_without_one_has_no_pack_store(self):
        sync_b, b = self.env.clone(self.key, 'b', pack_store=True)
        sync_c, c = self.env.clone(self.key, 'c')
        db = os.path.join(b, '.sg_vault', 'local', 'pack-store.sqlite')
        assert (os.stat(db).st_mode & 0o777) == 0o600
        assert self._store(c).packs() is None and not os.path.isdir(os.path.join(c, '.sg_vault', 'bare', 'packs'))
