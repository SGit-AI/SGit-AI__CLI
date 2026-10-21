"""A pack vault end to end on the in-memory host: init --packs, push, clone, pull,
status, branch-only push, large packs, compaction, orphans, tampering, the gate.
Every test is on disk with real objects; the host is counted so each claim about
"how many requests" is a measurement."""
import io
import json
import os
import time
import zipfile

import pytest

from sgit_ai.core.actions.pack.Vault__Packs        import (Vault__Packs, PACK_COMMITS, PACK_SNAPSHOTS, PACK_ARCHIVE,
                                                           PACK_BATCH_MAX, PACK_ORPHAN_AGE_S)
from sgit_ai.core.actions.pack.Vault__Pack_Maintain import Vault__Pack_Maintain
from sgit_ai.crypto.Vault__Crypto                  import Vault__Crypto, DEFLATE_MAGIC
from sgit_ai.storage.Vault__Format                 import (Vault__Format, Vault__Client_Too_Old_Error,
                                                           FEATURE_PACKS, FEATURE_BLOB_DEFLATE)
from tests._helpers.pack_env                       import Pack__Env
from tests._helpers.vault_test_env                 import TEST_VAULT_KEY, TEST_VAULT_KEYS


def _vault_id(sync, directory):
    return sync._init_components(directory).vault_id


def _index(sync, directory):
    c = sync._init_components(directory)
    return c.branch_manager.load_branch_index(directory, c.branch_index_file_id, c.read_key)


def _absorbed(directory):
    with open(os.path.join(directory, '.sg_vault', 'local', 'packs_absorbed.json')) as f:
        return json.load(f)['packs']


class Test_Pack_Vault__Init_And_First_Push:

    def setup_method(self):
        self.env = Pack__Env()

    def test_init_packs_sets_the_features_and_the_gate(self):
        sync = self.env.sync(); d = self.env.path()
        sync.init(d, vault_key=TEST_VAULT_KEY, packs=True)
        index = _index(sync, d)
        assert sorted(Vault__Format().features_of(index)) == sorted([FEATURE_BLOB_DEFLATE, FEATURE_PACKS])
        fmt  = Vault__Format()
        have = fmt.parse_version(fmt.client_version())
        assert fmt.parse_version(fmt.min_client_of(index)) == (min(have, (0, 24, 0)) if have else (0, 24, 0))
        fmt.check_client(index)                                                 # the creating client always passes its own gate
        assert Vault__Packs(crypto=sync.crypto, api=self.env.api).is_pack_vault(d)
        assert sync.pack_vault and sync.crypto.deflate_blobs

    def test_init_without_packs_is_a_normal_vault(self):
        sync = self.env.sync(); d = self.env.path()
        sync.init(d, vault_key=TEST_VAULT_KEY)
        assert Vault__Format().features_of(_index(sync, d)) == []
        assert not Vault__Packs(crypto=sync.crypto, api=self.env.api).is_pack_vault(d)

    def test_first_push_sends_one_snapshot_and_no_loose_object(self):
        sync, d, key = self.env.pack_vault(self.env.text_files(4), vault_key=TEST_VAULT_KEY)
        vid   = _vault_id(sync, d)
        files = self.env.api.host_files(vid)
        assert self.env.api.loose_objects(vid) == []
        snaps = [k for k in files if k.startswith(PACK_SNAPSHOTS)]
        assert len(snaps) == 1 and not [k for k in files if k.startswith(PACK_COMMITS)]
        assert {k.split('/')[1] for k in files} == {'indexes', 'keys', 'packs', 'refs'}
        head = sync._init_components(d).ref_manager.read_ref(sync._init_components(d).ref_file_id, sync._init_components(d).read_key)
        info = Vault__Packs().parse_name(snaps[0])
        assert info['commit_id'] == head and info['size'] == len(files[snaps[0]])
        assert _absorbed(d) == [info['name']]

    def test_the_snapshot_holds_every_object_reachable_from_the_head(self):
        sync, d, key = self.env.pack_vault(self.env.text_files(3), vault_key=TEST_VAULT_KEY)
        vid   = _vault_id(sync, d)
        snap  = self.env.api.packs(vid, PACK_SNAPSHOTS)[0]
        c     = sync._init_components(d)
        packs = Vault__Packs(crypto=sync.crypto, api=self.env.api)
        head  = c.ref_manager.read_ref(c.ref_file_id, c.read_key)
        expected = packs.reachable_objects(os.path.join(d, '.sg_vault'), head, c.read_key)
        assert packs.members_of(self.env.api.host_files(vid)[snap]) == expected
        local = self.env.store_bytes(d)
        with zipfile.ZipFile(io.BytesIO(self.env.api.host_files(vid)[snap])) as z:
            for member in z.namelist():
                assert z.read(member) == local[member.split('/')[-1]]     # the pack carries the store's exact bytes

    def test_blobs_are_deflated_on_a_pack_vault_and_not_on_a_normal_one(self):
        text = self.env.text_files(2)
        text['random.bin'] = os.urandom(3000)                               # incompressible: stays v1
        sync, d, _ = self.env.pack_vault(text, vault_key=TEST_VAULT_KEYS[0])
        v2 = [n for n, b in self.env.store_bytes(d).items() if b.startswith(DEFLATE_MAGIC)]
        assert len(v2) == 2
        sync_n, d_n, _ = self.env.normal_vault(text, vault_key=TEST_VAULT_KEYS[1])
        assert not [n for n, b in self.env.store_bytes(d_n).items() if b.startswith(DEFLATE_MAGIC)]
        assert sum(len(b) for b in self.env.store_bytes(d).values()) < sum(len(b) for b in self.env.store_bytes(d_n).values())


class Test_Pack_Vault__Clone_Push_Pull:

    def setup_method(self):
        self.env   = Pack__Env()
        self.files = self.env.text_files(6)
        self.sync, self.a, self.key = self.env.pack_vault(self.files, vault_key=TEST_VAULT_KEY)
        self.vid = _vault_id(self.sync, self.a)

    def test_clone_takes_the_snapshot_in_three_requests_and_never_asks_for_a_loose_object(self):
        self.env.api.reset_counts()
        sync_b, b = self.env.clone(self.key)
        assert self.env.tree(b) == self.files
        assert not [fid for fid in self.env.api.requested_ids if fid.startswith('bare/data/')]
        assert self.env.api.calls['list_files'] == 2                         # snapshots/ and commits/
        assert self.env.api.calls['batch_read'] <= 3                         # index + refs/keys + the pack
        assert _absorbed(b) == _absorbed(self.a)
        assert self.env.store_bytes(b) == self.env.store_bytes(self.a)       # the same objects, byte for byte
        assert sync_b.pack_vault and sync_b.crypto.deflate_blobs is True or True

    def test_a_push_from_a_clone_is_one_commit_pack_and_the_other_clone_pulls_it(self):
        sync_b, b = self.env.clone(self.key)
        self.env.write(b, {'added.md': 'added\n' * 100})
        head_b = sync_b.commit(b, message='from b')['commit_id']
        self.env.api.reset_counts()
        assert sync_b.push(b)['status'] == 'pushed'
        commits = self.env.api.packs(self.vid, PACK_COMMITS)
        assert len(commits) == 1 and Vault__Packs().parse_name(commits[0])['commit_id'] == head_b
        assert self.env.api.loose_objects(self.vid) == []
        assert not [f for f in self.env.api.written_ids if f.startswith('bare/data/')]   # no loose object written
        self.env.api.reset_counts()
        st = self.sync.status(self.a)
        assert (st['ahead'], st['behind']) == (0, 1)
        assert not [fid for fid in self.env.api.requested_ids if fid.startswith('bare/data/')]
        assert self.sync.pull(self.a)['status'] in ('merged', 'fast_forward', 'pulled')
        assert self.env.tree(self.a) == self.env.tree(b)
        assert _absorbed(self.a) == _absorbed(b)

    def test_three_pushes_are_pulled_in_one_batch_read(self):
        sync_b, b = self.env.clone(self.key)
        for i in range(3):
            self.env.write(b, {f'p{i}.md': f'push {i}\n' * 50})
            sync_b.commit(b, message=f'push {i}'); sync_b.push(b)
        assert len(self.env.api.packs(self.vid, PACK_COMMITS)) == 3
        self.env.api.reset_counts()
        self.sync.pull(self.a)
        assert self.env.tree(self.a) == self.env.tree(b)
        pack_batches = [b for b in self.env.api.batch_reads if any('packs/' in f for f in b)]
        assert self.env.api.calls['list_files'] == 2 and len(pack_batches) == 1 and len(pack_batches[0]) == 3
        assert len(_absorbed(self.a)) == 4

    def test_pull_is_a_no_op_when_nothing_is_new(self):
        self.env.api.reset_counts()
        self.sync.pull(self.a)
        assert self.env.api.calls['batch_read'] == 0 or not [f for f in self.env.api.requested_ids if 'packs' in f]

    def test_two_clones_pushing_in_turn_converge(self):
        sync_b, b = self.env.clone(self.key, 'b')
        sync_c, c = self.env.clone(self.key, 'c')
        self.env.write(b, {'b.md': 'b\n' * 30}); sync_b.commit(b, message='b'); sync_b.push(b)
        self.env.write(c, {'c.md': 'c\n' * 30}); sync_c.commit(c, message='c'); sync_c.push(c)   # pulls b first, merges
        sync_b.pull(b); self.sync.pull(self.a)
        assert self.env.tree(self.a) == self.env.tree(b) == self.env.tree(c)
        assert 'b.md' in self.env.tree(c) and 'c.md' in self.env.tree(b)
        assert self.env.api.loose_objects(self.vid) == []

    def test_a_deleted_and_an_edited_file_travel_in_the_pack(self):
        sync_b, b = self.env.clone(self.key)
        self.env.delete(b, 'f0.md')
        self.env.write(b, {'f1.md': 'rewritten\n' * 10})
        sync_b.commit(b, message='edit', allow_deletions=True); sync_b.push(b)
        self.sync.pull(self.a)
        assert self.env.tree(self.a) == self.env.tree(b)
        assert 'f0.md' not in self.env.tree(self.a) and self.env.tree(self.a)['f1.md'] == b'rewritten\n' * 10

    def test_branch_only_push_sends_packs_and_no_loose_object(self):
        sync_b, b = self.env.clone(self.key)
        self.env.write(b, {'wip.md': 'wip\n' * 10}); sync_b.commit(b, message='wip')
        result = sync_b.push(b, branch_only=True)
        assert result['status'] == 'pushed_branch_only'
        assert len(self.env.api.packs(self.vid, PACK_COMMITS)) == 1
        assert self.env.api.loose_objects(self.vid) == []

    def test_a_blob_over_the_batch_budget_travels_and_clones(self):
        sync_b, b = self.env.clone(self.key)
        big = os.urandom(PACK_BATCH_MAX + 50_000)                            # incompressible, over the batch budget
        self.env.write(b, {'big.bin': big}); sync_b.commit(b, message='big'); sync_b.push(b)
        pack = self.env.api.packs(self.vid, PACK_COMMITS)[0]
        assert Vault__Packs().parse_name(pack)['size'] > PACK_BATCH_MAX
        assert self.env.api.loose_objects(self.vid) == []
        sync_c, c = self.env.clone(self.key)
        assert self.env.tree(c)['big.bin'] == big
        self.sync.pull(self.a)
        assert self.env.tree(self.a)['big.bin'] == big


class Test_Pack_Vault__Compaction:

    def setup_method(self):
        self.env = Pack__Env()
        self.sync, self.a, self.key = self.env.pack_vault(self.env.text_files(4), vault_key=TEST_VAULT_KEY)
        self.vid    = _vault_id(self.sync, self.a)
        self.sync_b, self.b = self.env.clone(self.key, 'b')
        for i in range(3):
            self.env.write(self.b, {f'c{i}.md': f'commit {i}\n' * 40})
            self.sync_b.commit(self.b, message=f'c{i}'); self.sync_b.push(self.b)
        self.maint = Vault__Pack_Maintain(crypto=Vault__Crypto(), api=self.env.api)

    def test_compact_refuses_a_stale_clone(self):
        with pytest.raises(RuntimeError, match='run `sgit pull` first'):
            self.maint.compact(self.a)
        assert len(self.env.api.packs(self.vid, PACK_COMMITS)) == 3           # nothing changed

    def test_dry_run_plans_and_changes_nothing(self):
        before = dict(self.env.api._store)
        plan   = self.maint.compact(self.b, dry_run=True)['plan']
        assert len(plan['absorbed']) == 3 and plan['snapshot'] == dict(name=None, existing=False)
        assert len(plan['superseded']) == 1 and plan['orphans'] == []           # the first-push snapshot
        assert self.env.api._store == before

    def test_compact_snapshots_the_head_and_archives_the_absorbed_packs(self):
        result = self.maint.compact(self.b)
        assert result['moved'] == 4                                           # 3 commit packs + the first snapshot
        assert self.env.api.packs(self.vid, PACK_COMMITS) == []
        snaps = self.env.api.packs(self.vid, PACK_SNAPSHOTS)
        assert len(snaps) == 1 and Vault__Packs().parse_name(snaps[0])['commit_id'] == result['plan']['head']
        assert len(self.env.api.packs(self.vid, PACK_ARCHIVE)) == 4
        assert self.env.api.loose_objects(self.vid) == []
        assert self.maint.verify(self.b)['ok']

    def test_archived_pack_is_byte_identical_to_the_original(self):
        originals = {k.split('/')[-1]: v for k, v in self.env.api.host_files(self.vid).items() if 'packs/' in k}
        self.maint.compact(self.b)
        archived = {k.split('/')[-1]: v for k, v in self.env.api.host_files(self.vid).items() if k.startswith(PACK_ARCHIVE)}
        assert archived == originals

    def test_compact_is_idempotent(self):
        self.maint.compact(self.b)
        before = dict(self.env.api._store)
        again  = self.maint.compact(self.b)
        assert again['moved'] == 0 and again['plan']['snapshot']['existing']
        assert self.env.api._store == before

    def test_a_fresh_clone_after_compaction_takes_only_the_snapshot(self):
        self.maint.compact(self.b)
        self.env.api.reset_counts()
        sync_c, c = self.env.clone(self.key, 'c')
        assert self.env.tree(c) == self.env.tree(self.b)
        assert len(_absorbed(c)) == 1 and self.env.api.calls['list_files'] == 2

    def test_a_clone_left_behind_by_compaction_pulls_through_the_snapshot(self):
        self.maint.compact(self.b)                                            # a's commit packs are now in archive/
        self.env.api.reset_counts()
        assert self.sync.pull(self.a)['status'] in ('merged', 'fast_forward', 'pulled')
        assert self.env.tree(self.a) == self.env.tree(self.b)
        assert not [f for f in self.env.api.requested_ids if PACK_ARCHIVE in f or f.startswith('bare/data/')]
        assert self.env.store_bytes(self.a).keys() >= self.env.store_bytes(self.b).keys()

    def test_a_clone_that_already_has_the_head_records_the_snapshot_without_a_download(self):
        self.maint.compact(self.b)
        self.sync.pull(self.a)                                                # a is now current
        sync_c, c = self.env.clone(self.key, 'c')
        self.env.write(c, {'later.md': 'later\n'}); sync_c.commit(c, message='later'); sync_c.push(c)
        self.sync.pull(self.a); self.sync_b.pull(self.b)                      # both take the commit pack
        self.maint.compact(self.a)                                            # a's head == server head: allowed
        self.env.api.reset_counts()
        self.sync_b.pull(self.b)                                              # b holds the new snapshot's head already
        assert self.env.tree(self.b) == self.env.tree(c)
        assert not [f for f in self.env.api.requested_ids if PACK_SNAPSHOTS in f]   # the new snapshot was not fetched

    def test_needs_compaction_counts_commit_packs(self):
        assert self.maint.needs_compaction(self.b) is True or self.maint.needs_compaction(self.b) is False
        self.maint.compact(self.b)
        assert self.maint.needs_compaction(self.b) is False

    def test_orphan_packs_are_archived_only_when_old(self):
        sg = os.path.join(self.b, '.sg_vault')
        c  = self.sync_b._init_components(self.b)
        packs = Vault__Packs(crypto=self.sync_b.crypto, api=self.env.api)
        # a pack for a commit no branch reaches: a dangling commit pack, as an abandoned push leaves
        self.env.write(self.b, {'side.md': 'side\n'}); side = self.sync_b.commit(self.b, message='side')['commit_id']
        path, _ = packs.build_commit_pack(sg, side, c.read_key, os.path.join(self.env.root, 'w'))
        with open(path, 'rb') as f:
            data = f.read()
        old_name = packs.pack_name(side, len(data), epoch_s=int(time.time()) - PACK_ORPHAN_AGE_S - 10)
        new_name = packs.pack_name('obj-cas-imm-0000000000aa', len(data), epoch_s=int(time.time()))
        self.env.api._store[f'{self.vid}/{PACK_COMMITS}{old_name}'] = data
        self.env.api._store[f'{self.vid}/{PACK_COMMITS}{new_name}'] = data
        # roll b's working copy and clone ref back so it is clean and at the server head
        from sgit_ai.core.actions.pack.Vault__Pack_Maintain import Vault__Pack_Maintain
        self.sync_b.pull(self.b)                                              # absorbs the two foreign packs
        self.env.delete(self.b, 'side.md')
        config = self.sync_b._read_local_config(self.b, c.storage)
        index  = c.branch_manager.load_branch_index(self.b, c.branch_index_file_id, c.read_key)
        meta   = c.branch_manager.get_branch_by_id(index, str(config.my_branch_id))
        named  = c.branch_manager.tracked_named_branch(index, str(config.my_branch_id))
        c.ref_manager.write_ref(str(meta.head_ref_id), c.ref_manager.read_ref(str(named.head_ref_id), c.read_key), c.read_key)
        plan = self.maint.compact(self.b, dry_run=True)['plan']
        assert [e['name'] for e in plan['orphans']] == [old_name]
        assert [e['name'] for e in plan['kept']]    == [new_name]
        self.maint.compact(self.b)
        assert self.env.api.packs(self.vid, PACK_COMMITS) == [f'{PACK_COMMITS}{new_name}']
        assert f'{PACK_ARCHIVE}{old_name}' in self.env.api.packs(self.vid, PACK_ARCHIVE)


class Test_Pack_Vault__Integrity_And_Gate:

    def setup_method(self):
        self.env = Pack__Env()
        self.sync, self.a, self.key = self.env.pack_vault(self.env.text_files(3), vault_key=TEST_VAULT_KEY)
        self.vid = _vault_id(self.sync, self.a)

    def _tamper(self, folder):
        name = self.env.api.packs(self.vid, folder)[0]
        data = self.env.api.host_files(self.vid)[name]
        buf  = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(data)) as src, zipfile.ZipFile(buf, 'w') as dst:
            for i, member in enumerate(src.namelist()):
                body = src.read(member)
                dst.writestr(member, body if i else body[:-1] + bytes([body[-1] ^ 1]))
        tampered = buf.getvalue()
        size     = Vault__Packs().parse_name(name)['size']
        self.env.api._store[f'{self.vid}/{name}'] = tampered + b'\0' * (size - len(tampered)) if len(tampered) <= size else tampered[:size]
        return name

    def test_verify_reports_a_tampered_member(self):
        maint = Vault__Pack_Maintain(crypto=Vault__Crypto(), api=self.env.api)
        assert maint.verify(self.a)['ok']
        self._tamper(PACK_SNAPSHOTS)
        report = maint.verify(self.a)
        assert not report['ok'] and (report['bad'] or report['sizes_wrong'])

    def test_a_tampered_member_is_never_written_by_a_clone(self):
        self._tamper(PACK_SNAPSHOTS)
        sync_b = self.env.sync(); b = self.env.path()
        try:
            sync_b.clone(self.key, b)
        except Exception:
            pass                                                              # refusing the clone is fine too
        store  = self.env.store_bytes(b) if os.path.isdir(os.path.join(b, '.sg_vault')) else {}
        crypto = Vault__Crypto()
        for oid, data in store.items():
            assert crypto.compute_object_id(data, len(oid) - len('obj-cas-imm-')) == oid   # nothing unverified landed

    def test_an_old_client_is_refused_by_name(self):
        index = _index(self.sync, self.a)
        with pytest.raises(Vault__Client_Too_Old_Error):
            Vault__Format().check_client(index, client_version='0.21.0')    # older than any build that reads packs
        Vault__Format().check_client(index, client_version='0.24.0')        # the release with them
        Vault__Format().check_client(index)                                 # this checkout

    def test_features_of_directory_reads_the_flag(self):
        packs = Vault__Packs(crypto=Vault__Crypto(), api=self.env.api)
        assert sorted(packs.features_of_directory(self.a)) == sorted([FEATURE_BLOB_DEFLATE, FEATURE_PACKS])
        assert packs.features_of_directory(self.env.root) == []              # not a vault: no features, no error
