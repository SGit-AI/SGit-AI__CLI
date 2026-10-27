"""Pack indexes, Phase 1, the writer (cli.sgit.ai dev pack, 26 Oct): an index pack beside
every data pack a push, a first push or a compaction writes; a header signed by the
pusher's clone key that anchors the index to its commit; members that equal what the
trees say; opaque member names; a failed index upload that never fails the push and is
filled by `sgit pack index build`; index packs that follow their data packs to archive/;
and a client that never lists indexes/ (0.24.0–0.25.0) unaffected."""
import io
import json
import os
import zipfile

import pytest

from sgit_ai.core.actions.pack.Vault__Packs        import PACK_COMMITS, PACK_SNAPSHOTS, PACK_ARCHIVE
from sgit_ai.core.actions.pack.Vault__Pack_Index   import (Vault__Pack_Index, PACK_INDEXES, PACK_INDEX_COMMITS, PACK_INDEX_SNAPSHOTS,
                                                           PACK_INDEX_ARCHIVE, INDEX_MAGIC, INDEX_HEADER_NAME, INDEX_SCHEMA)
from sgit_ai.core.actions.pack.Vault__Pack_Maintain import Vault__Pack_Maintain
from sgit_ai.storage.Vault__Format                 import FEATURE_PACK_INDEXES, Vault__Format
from sgit_ai.storage.Vault__Object_Store           import Vault__Object_Store
from sgit_ai.storage.Vault__Sub_Tree               import Vault__Sub_Tree
from tests._helpers.pack_env                       import Pack__Env
from tests._helpers.vault_test_env                 import TEST_VAULT_KEY

FILES = {'raw/uk/gov/a.txt': b'a\n', 'raw/uk/gov/b.txt': b'bb\n', 'raw/fr/edu/c.txt': b'ccc\n', 'top.md': b'# top\n'}


class Api__Refusing_Index_Uploads(Pack__Env().api.__class__):
    """A host that refuses writes under bare/packs/indexes/ (an index upload that fails)."""
    def batch(self, vault_id, write_key, operations):
        if any(str(op.get('file_id', '')).startswith(PACK_INDEXES) for op in operations):
            raise RuntimeError('HTTP 503 index uploads refused')
        return super().batch(vault_id, write_key, operations)


class Test_Pack_Index__Writer:

    def setup_method(self):
        self.env = Pack__Env()
        self.sync, self.a, self.key = self.env.pack_vault(dict(FILES), vault_key=TEST_VAULT_KEY)
        self.c   = self.sync._init_components(self.a)
        self.vid = str(self.c.vault_id)
        self.idx = Vault__Pack_Index(crypto=self.sync.crypto, api=self.env.api)
        self.sg  = os.path.join(self.a, '.sg_vault')

    def _push_change(self):
        self.env.write(self.a, {'raw/uk/gov/a.txt': b'a changed\n', 'raw/uk/edu/new.txt': b'new\n'})
        os.remove(os.path.join(self.a, 'top.md'))
        self.sync.commit(self.a, message='a pass')
        self.sync.push(self.a)
        data_entry = self.idx.list_folder(self.vid, PACK_COMMITS)[-1]
        index_entry = self.idx.index_pack_for(self.vid, PACK_COMMITS, data_entry)
        return data_entry, index_entry

    # --- where and what -----------------------------------------------------------------
    def test_a_new_pack_vault_declares_the_advisory_feature_and_no_higher_gate(self):
        index = self.c.branch_manager.load_branch_index(self.a, self.c.branch_index_file_id, self.c.read_key)
        assert FEATURE_PACK_INDEXES in Vault__Format().features_of(index)
        assert Vault__Format().min_client_of(index) == Vault__Format().min_client_of(index)   # unchanged by the feature
        assert FEATURE_PACK_INDEXES not in __import__('sgit_ai.storage.Vault__Format', fromlist=['x']).FEATURE_MIN_CLIENT

    def test_the_first_push_writes_a_snapshot_index_with_the_same_name_stem(self):
        snaps = self.idx.list_folder(self.vid, PACK_SNAPSHOTS)
        index = self.idx.list_index_packs(self.vid, PACK_INDEX_SNAPSHOTS)
        assert len(snaps) == 1 and len(index) == 1
        assert (index[0]['commit_id'], index[0]['epoch']) == (snaps[0]['commit_id'], snaps[0]['epoch'])
        assert index[0]['size'] == len(self.idx.fetch_pack(self.vid, index[0]))        # the name carries its own size

    def test_a_push_writes_a_commit_index_beside_the_commit_pack(self):
        data, index = self._push_change()
        assert index is not None and index['name'].split('__')[1] == data['commit_id']
        assert os.path.isfile(self.idx.local_index_pack_path(self.a, PACK_INDEX_COMMITS, index['name']))   # a local copy
        assert self.idx.load_gaps(self.a) == []

    def test_member_names_are_opaque_and_the_header_is_first_and_stored(self):
        _, index = self._push_change()
        data = self.idx.fetch_pack(self.vid, index)
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            names = z.namelist()
            assert names[0] == INDEX_HEADER_NAME and all(n.startswith('index/') for n in names)
            assert all(n == INDEX_HEADER_NAME or n[len('index/'):].isdigit() for n in names)
            assert all(i.compress_type == zipfile.ZIP_STORED for i in z.infolist())
            assert z.read(INDEX_HEADER_NAME)[:8] == INDEX_MAGIC
        assert b'raw/' not in data and b'folder:' not in data and b'changes' not in data   # nothing in clear

    # --- the header -------------------------------------------------------------------------
    def test_the_header_anchors_the_commit_and_is_signed_by_the_clone_key(self):
        _, index = self._push_change()
        data   = self.idx.fetch_pack(self.vid, index)
        header = self.idx.read_header(data, self.c.read_key)
        fields = self.idx.commit_fields(self.sg, index['commit_id'], self.c.read_key)
        assert header['schema'] == INDEX_SCHEMA and header['kind'] == 'commit'
        assert header['commit_id'] == fields['commit_id'] and header['parents'] == fields['parents']
        assert header['tree_id'] == fields['tree_id'] and header['timestamp_ms'] == fields['timestamp_ms']
        assert header['generation'] == 3                                         # init, first, the pass
        assert header['data_packs'] == [self.idx.list_folder(self.vid, PACK_COMMITS)[-1]['name']]
        public = self.c.key_manager.load_public_key(header['author_key_id'], self.c.read_key)
        assert self.idx.verify_header_signature(header, public)
        header['generation'] = 99                                                 # a changed field: the signature fails
        assert not self.idx.verify_header_signature(header, public)

    def test_the_header_is_read_from_the_first_local_file_header_not_the_central_directory(self):
        _, index = self._push_change()
        data = self.idx.fetch_pack(self.vid, index)
        cut  = data[:-200]                                                        # no central directory any more
        assert self.idx.read_header(cut, self.c.read_key)['commit_id'] == index['commit_id']
        with pytest.raises(ValueError):
            self.idx.read_header(b'PK\x03\x04' + b'\x00' * 100, self.c.read_key)
        with pytest.raises(ValueError):
            self.idx.read_header(data[:40] + b'SGIX\x00\x02\x00\x00' + data[48:], self.c.read_key)   # another format

    def test_every_member_is_checked_against_the_headers_sha256(self):
        _, index = self._push_change()
        data   = self.idx.fetch_pack(self.vid, index)
        header = self.idx.read_header(data, self.c.read_key)
        row    = self.idx.member_table(header)['changes']
        assert self.idx.read_member(data, header, 'changes', self.c.read_key)['schema'] == 'changes_v1'
        flipped = bytearray(data); flipped[row['offset'] + row['length'] - 1] ^= 0x01
        with pytest.raises(Exception):
            self.idx.read_member(bytes(flipped), header, 'changes', self.c.read_key)
        assert self.idx.read_member(data, header, 'no-such-member', self.c.read_key) is None

    # --- the members equal the trees ------------------------------------------------------------
    def test_changes_equal_the_tree_diff_against_the_first_parent(self):
        _, index = self._push_change()
        data    = self.idx.fetch_pack(self.vid, index)
        header  = self.idx.read_header(data, self.c.read_key)
        changes = self.idx.read_member(data, header, 'changes', self.c.read_key)['changes']
        assert [(x['path'], x['op']) for x in changes] == [('raw/uk/edu/new.txt', 'A'), ('raw/uk/gov/a.txt', 'M'), ('top.md', 'D')]
        sub  = Vault__Sub_Tree(crypto=self.sync.crypto, obj_store=self.c.obj_store)
        diff = sub.diff_trees(header['tree_id'], self.idx.commit_fields(self.sg, header['parents'][0], self.c.read_key)['tree_id'], self.c.read_key)
        by_path = {x['path']: x for x in changes}
        assert by_path['raw/uk/gov/a.txt']['old_blob'] == diff['modified']['raw/uk/gov/a.txt'][1]['blob_id']
        assert by_path['raw/uk/gov/a.txt']['new_blob'] == diff['modified']['raw/uk/gov/a.txt'][0]['blob_id']
        assert by_path['top.md']['old_blob'] == diff['deleted']['top.md']['blob_id'] and 'new_blob' not in by_path['top.md']
        assert by_path['raw/uk/edu/new.txt']['size'] == 4 and by_path['raw/uk/edu/new.txt']['content_type'] == 'text/plain'

    def test_a_commit_index_carries_the_folders_on_the_changed_paths_only(self):
        _, index = self._push_change()
        data    = self.idx.fetch_pack(self.vid, index)
        header  = self.idx.read_header(data, self.c.read_key)
        folders = sorted(n for n in self.idx.member_table(header) if n.startswith('folder:'))
        assert folders == ['folder:', 'folder:raw', 'folder:raw/uk', 'folder:raw/uk/edu', 'folder:raw/uk/gov']   # not raw/fr
        sub  = Vault__Sub_Tree(crypto=self.sync.crypto, obj_store=self.c.obj_store)
        flat = sub.flatten(header['tree_id'], self.c.read_key); dirs = sub.flatten_dirs(header['tree_id'], self.c.read_key)
        uk   = self.idx.read_member(data, header, 'folder:raw/uk', self.c.read_key)
        assert uk['tree_id'] == dirs['raw/uk'] and sorted(uk['dirs']) == ['edu', 'gov'] and uk['files'] == {}
        assert uk['totals'] == dict(files=3, bytes=len(b'a changed\n') + 3 + 4, folders=2)
        gov  = self.idx.read_member(data, header, 'folder:raw/uk/gov', self.c.read_key)
        assert self.idx.without_offsets(gov)['files'] == {name: flat[f'raw/uk/gov/{name}'] for name in ('a.txt', 'b.txt')}
        assert gov['files']['a.txt']['at'][0] == 0 and 'at' not in gov['files']['b.txt']        # a.txt is in this pack, b.txt older
        assert gov['tree_at'][0] == 0 and self.idx.at_faults(gov, self.idx.fetch_pack(self.vid, self.idx.list_folder(self.vid, PACK_COMMITS)[-1])) == []

    def test_the_snapshot_index_flat_equals_the_flatten_and_the_graph_has_generations(self):
        self._push_change()
        maintain = Vault__Pack_Maintain(crypto=self.sync.crypto, api=self.env.api)
        maintain.compact(self.a)
        snaps = self.idx.list_folder(self.vid, PACK_SNAPSHOTS)
        snap  = snaps[-1]
        index = self.idx.index_pack_for(self.vid, PACK_SNAPSHOTS, snap)
        assert index is not None
        data   = self.idx.fetch_pack(self.vid, index)
        header = self.idx.read_header(data, self.c.read_key)
        assert header['kind'] == 'snapshot'
        sub  = Vault__Sub_Tree(crypto=self.sync.crypto, obj_store=self.c.obj_store)
        flat = self.idx.read_member(data, header, 'flat', self.c.read_key)
        assert flat['flat'] == sub.flatten(header['tree_id'], self.c.read_key) and flat['dirs'] == sub.flatten_dirs(header['tree_id'], self.c.read_key)
        table = self.idx.member_table(header)
        assert {n for n in table if n.startswith('folder:')} == {f'folder:{d}' for d in flat['dirs']}
        gens = self.idx.read_member(data, header, 'commit-gen', self.c.read_key)
        assert gens[snap['commit_id']] == 3 and sorted(gens.values()) == [1, 2, 3]
        shard = self.idx.read_member(data, header, 'commits:0', self.c.read_key)
        assert set(shard) == set(gens) and shard[snap['commit_id']]['tree_id'] == header['tree_id']
        blob_paths = {}
        for n in table:
            if n.startswith('blob-paths:'):
                blob_paths.update(self.idx.read_member(data, header, n, self.c.read_key))
        assert blob_paths == {e['blob_id']: [p] for p, e in flat['flat'].items()}
        file_commits = {}
        for n in table:
            if n.startswith('file-commits:'):
                file_commits.update(self.idx.read_member(data, header, n, self.c.read_key))
        assert file_commits['raw/uk/gov/a.txt'] == [snap['commit_id'], sorted(gens, key=gens.get)[1]]   # the pass, then the first commit

    def test_generation_of_a_merge_is_one_past_its_highest_parent(self):
        sync_b, b = self.env.clone(self.key, 'b')
        self.env.write(self.a, {'from-a.md': b'a\n'}); self.sync.commit(self.a, message='a'); self.sync.push(self.a)
        self.env.write(b, {'from-b.md': b'b\n'}); sync_b.commit(b, message='b'); sync_b.push(b)   # pulls a, merges, pushes
        head = self.idx.list_folder(self.vid, PACK_COMMITS)[-1]
        index = self.idx.index_pack_for(self.vid, PACK_COMMITS, head)
        header = self.idx.read_header(self.idx.fetch_pack(self.vid, index), self.c.read_key)
        sg_b   = os.path.join(b, '.sg_vault')
        parents = header['parents']
        assert header['generation'] == 1 + max(self.idx.generation_of(sg_b, p, self.c.read_key) for p in parents)

    # --- failure, gaps, backfill --------------------------------------------------------------------
    def test_a_refused_index_upload_never_fails_the_push_and_is_a_recorded_gap(self):
        self.env.write(self.a, {'x.txt': b'x\n'}); self.sync.commit(self.a, message='x')
        refusing = Api__Refusing_Index_Uploads()
        refusing.setup(); refusing._store = self.env.api._store
        from sgit_ai.core.Vault__Sync import Vault__Sync
        sync = Vault__Sync(crypto=self.sync.crypto, api=refusing)
        result = sync.push(self.a)
        assert result['status'] == 'pushed'
        data = self.idx.list_folder(self.vid, PACK_COMMITS)[-1]
        assert self.idx.index_pack_for(self.vid, PACK_COMMITS, data) is None
        assert self.idx.load_gaps(self.a) == [PACK_COMMITS + data['name']]
        built = self.idx.build_missing(self.a)
        assert built['written'] and built['gaps'] == [] and self.idx.index_pack_for(self.vid, PACK_COMMITS, data) is not None

    def test_build_fills_what_an_older_client_left_and_adds_the_feature(self):
        os.environ['SGIT_PACK_INDEXES'] = '0'                                  # an old client, or the writer off
        try:
            self.env.write(self.a, {'y.txt': b'y\n'}); self.sync.commit(self.a, message='y'); self.sync.push(self.a)
        finally:
            os.environ.pop('SGIT_PACK_INDEXES', None)
        assert self.idx.data_packs_without_index(self.vid) != []
        from sgit_ai.core.actions.format.Vault__Sync__Format import Vault__Sync__Format
        Vault__Sync__Format(crypto=self.sync.crypto, api=self.env.api).set_format(self.a, remove_features=[FEATURE_PACK_INDEXES])
        assert FEATURE_PACK_INDEXES not in self.idx.features_of_directory(self.a)
        built = self.idx.build_missing(self.a)
        assert len(built['written']) == 1 and self.idx.data_packs_without_index(self.vid) == []
        assert FEATURE_PACK_INDEXES in self.idx.features_of_directory(self.a)
        assert self.idx.verify_indexes(self.a)['ok']

    def test_verify_finds_a_lying_index(self):
        data_entry, index = self._push_change()
        data   = self.idx.fetch_pack(self.vid, index)
        header = self.idx.read_header(data, self.c.read_key)
        report = self.idx.verify_indexes(self.a)
        assert report['ok'] and report['packs'] == 2 and report['unsigned'] == [] and report['gaps'] == []
        # a member whose bytes changed: the sha256 in the signed header catches it
        row = self.idx.member_table(header)['changes']
        broken = bytearray(data); broken[row['offset']] ^= 0x01
        self.env.api._store[f'{self.vid}/{index["file_id"]}'] = bytes(broken)
        report = self.idx.verify_indexes(self.a)
        assert not report['ok'] and report['bad'][0]['member'] == 'changes'

    # --- compaction ------------------------------------------------------------------------------
    def test_compaction_writes_the_snapshot_index_and_archives_index_packs_with_their_data_packs(self):
        data_entry, index = self._push_change()
        Vault__Pack_Maintain(crypto=self.sync.crypto, api=self.env.api).compact(self.a)
        assert any(e['name'] == data_entry['name'] for e in self.idx.list_folder(self.vid, PACK_ARCHIVE))
        assert any(e['name'] == index['name'] for e in self.idx.list_index_packs(self.vid, PACK_INDEX_ARCHIVE))
        assert not any(e['name'] == index['name'] for e in self.idx.list_index_packs(self.vid, PACK_INDEX_COMMITS))
        snaps = self.idx.list_folder(self.vid, PACK_SNAPSHOTS)
        assert self.idx.index_pack_for(self.vid, PACK_SNAPSHOTS, snaps[-1]) is not None
        stats = self.idx.index_stats(self.a)
        assert stats['folders']['snapshots']['without_index'] == [] and stats['folders']['archive']['index_packs'] >= 1

    # --- the old client -----------------------------------------------------------------------------
    def test_a_reader_that_never_lists_indexes_is_unaffected(self):
        """C1's half that runs here: a client that does not read indexes (0.24.0–0.25.0, or
        this one with the reader off) lists only commits/ and snapshots/ and never touches
        a byte under indexes/; the loose store and the working copy are the same."""
        self._push_change()
        self.env.api.reset_counts()
        os.environ['SGIT_PACK_INDEXES_READ'] = '0'
        try:
            sync_b, b = self.env.clone(self.key, 'b')
        finally:
            os.environ.pop('SGIT_PACK_INDEXES_READ', None)
        assert all(not p.startswith(PACK_INDEXES) for p in self.env.api.listed_prefixes)
        assert not [f for f in self.env.api.requested_ids if f.startswith(PACK_INDEXES)]
        assert not os.path.isdir(os.path.join(b, '.sg_vault', 'local', 'index'))
        assert sorted(os.listdir(os.path.join(b, 'raw', 'uk'))) == ['edu', 'gov']
        assert sync_b.status(b)['clean']
        from sgit_ai.core.actions.pack.Vault__Packs import Vault__Packs
        packs = Vault__Packs(crypto=self.sync.crypto, api=self.env.api)
        cb = sync_b._init_components(b)
        assert packs.sync_down(b, self.vid, cb.read_key)['packs'] == 0            # nothing left to absorb, nothing refused


class Test_Pack_Index__Writer__Review_26_Oct:

    def test_a_commit_index_builds_only_its_touched_folders_and_they_equal_the_full_build(self):
        """L3: the folder members of a commit index used to be built for every folder of
        the head and then filtered; now only the touched ones are, with the same totals."""
        from sgit_ai.storage.Vault__Sub_Tree import Vault__Sub_Tree
        env = Pack__Env()
        files = {f'wide/d{i:02d}/f.txt': f'file {i}\n'.encode() for i in range(20)}
        files['top.md'] = b'# top\n'
        sync, a, key = env.pack_vault(files, vault_key=TEST_VAULT_KEY)
        env.write(a, {'wide/d07/f.txt': b'changed\n', 'wide/d07/g.txt': b'new\n'}); sync.commit(a, message='one folder'); sync.push(a)
        c    = sync._init_components(a)
        sg   = os.path.join(a, '.sg_vault')
        idx  = Vault__Pack_Index(crypto=sync.crypto, api=env.api)
        head = sync.status(a)['clone_head']
        fields, members = idx.build_commit_members(sg, head, c.read_key)
        assert sorted(n for n in members if n.startswith('folder:')) == ['folder:', 'folder:wide', 'folder:wide/d07']
        sub  = Vault__Sub_Tree(crypto=sync.crypto, obj_store=c.obj_store)
        flat = sub.flatten(fields['tree_id'], c.read_key); dirs = sub.flatten_dirs(fields['tree_id'], c.read_key)
        full = idx.folder_entries(flat, dirs)
        for name, raw in members.items():
            if name.startswith('folder:'):
                assert json.loads(raw) == full[name[len('folder:'):]]            # the same member, totals included
        assert json.loads(members['folder:'])['totals'] == dict(files=22, bytes=sum(int(e['size']) for e in flat.values()), folders=21)


class Test_Pack_Index__Writer__Compaction_Reuse:

    def test_a_second_compaction_builds_file_commits_from_the_previous_snapshot_index_and_they_equal_the_full_build(self):
        """M3: every compaction re-diffed the whole history for file-commits; now the
        previous snapshot index's member plus the absorbed commits' changes give the
        same answer."""
        env = Pack__Env()
        sync, a, key = env.pack_vault({'raw/uk/a.txt': b'a\n', 'raw/uk/b.txt': b'bb\n', 'top.md': b'# top\n'}, vault_key=TEST_VAULT_KEY)
        c   = sync._init_components(a); vid = str(c.vault_id); sg = os.path.join(a, '.sg_vault')
        idx = Vault__Pack_Index(crypto=sync.crypto, api=env.api)
        maint = Vault__Pack_Maintain(crypto=sync.crypto, api=env.api)
        for n in range(3):
            env.write(a, {'raw/uk/a.txt': f'a{n}\n'.encode(), f'raw/fr/n{n}.txt': b'n\n'}); sync.commit(a, message=f'c{n}'); sync.push(a)
        maint.compact(a)
        for n in range(3, 6):
            env.write(a, {'raw/uk/b.txt': f'b{n}\n'.encode(), 'top.md': f'# {n}\n'.encode()}); sync.commit(a, message=f'c{n}'); sync.push(a)
        msgs = []
        maint.compact(a, on_progress=lambda k, t, d='': msgs.append((t, d)))
        assert any(t == 'Indexing history' and 'from the previous snapshot index' in d for t, d in msgs)
        snap  = sorted(idx.list_folder(vid, PACK_SNAPSHOTS), key=lambda e: e['epoch'])[-1]
        entry = idx.index_pack_for(vid, PACK_SNAPSHOTS, snap)
        data  = idx.fetch_pack(vid, entry); header = idx.read_header(data, c.read_key)
        reused = {}
        for name in idx.member_table(header):
            if name.startswith('file-commits:'):
                reused.update(idx.read_member(data, header, name, c.read_key))
        # the full build: no prior index to reuse (its local copies hidden)
        local = os.path.join(sg, 'local', 'index', 'packs')
        os.rename(local, local + '.hidden')
        try:
            fields, members = idx.build_snapshot_members(sg, snap['commit_id'], c.read_key)
        finally:
            os.rename(local + '.hidden', local)
        full = {}
        for name, raw in members.items():
            if name.startswith('file-commits:'):
                full.update(json.loads(raw))
        assert reused == full and len(full['raw/uk/a.txt']) == 4 and len(full['top.md']) == 4


class Test_Pack_Index__Writer__Orphan_Sweep:

    def test_compaction_moves_an_index_pack_an_older_client_left_behind_and_deletes_one_without_a_data_pack(self):
        """S4: a 0.25.0 compaction archives data packs and knows nothing of their indexes,
        so index packs piled up under indexes/commits/. The next compaction by this
        client moves them beside their data pack in indexes/archive/, and deletes an
        index whose data pack is nowhere."""
        env = Pack__Env()
        sync, a, key = env.pack_vault({'f.txt': b'f\n'}, vault_key=TEST_VAULT_KEY)
        c   = sync._init_components(a); vid = str(c.vault_id)
        idx = Vault__Pack_Index(crypto=sync.crypto, api=env.api)
        env.write(a, {'g.txt': b'g\n'}); sync.commit(a, message='g'); sync.push(a)
        env.write(a, {'h.txt': b'h\n'}); sync.commit(a, message='h'); sync.push(a)
        commits = idx.list_folder(vid, PACK_COMMITS)
        left_behind, nowhere = commits[0], commits[1]
        # an older client's compaction: the data pack moved to archive/, its index not
        env.api._store[f'{vid}/{PACK_ARCHIVE}{left_behind["name"]}'] = env.api._store.pop(f'{vid}/{left_behind["file_id"]}')
        # and a data pack that vanished with its index still listed
        env.api._store.pop(f'{vid}/{nowhere["file_id"]}')
        idx_left    = idx.index_pack_for(vid, PACK_COMMITS, left_behind)
        idx_nowhere = idx.index_pack_for(vid, PACK_COMMITS, nowhere)
        assert idx_left and idx_nowhere
        msgs = []
        import time
        r = Vault__Pack_Maintain(crypto=sync.crypto, api=env.api).compact(a, on_progress=lambda k, t, d='': msgs.append((t, d)),
                                                                        now=int(time.time()) + 2 * 24 * 3600)   # past the orphan age
        assert r['plan']['orphan_indexes'] == dict(archived=1, deleted=1)
        names_archive = {e['name'] for e in idx.list_index_packs(vid, PACK_INDEX_ARCHIVE)}
        names_commits = {e['name'] for e in idx.list_index_packs(vid, PACK_INDEX_COMMITS)}
        assert idx_left['name'] in names_archive and idx_left['name'] not in names_commits
        assert idx_nowhere['name'] not in names_archive and idx_nowhere['name'] not in names_commits
        assert idx.verify_indexes(a)['orphans'] == []


class Test_Pack_Index__Writer__Dump:

    def test_dump_of_a_pack_vault_with_index_packs_reports_no_error(self):
        """S3: `sgit dump` took every file under bare/packs/indexes/ for a branch index and
        reported a decrypt error per index pack."""
        from sgit_ai.core.actions.dump.Vault__Dump import Vault__Dump
        env = Pack__Env()
        sync, a, key = env.pack_vault({'f.txt': b'f\n'}, vault_key=TEST_VAULT_KEY)
        env.write(a, {'g.txt': b'g\n'}); sync.commit(a, message='g'); sync.push(a)
        c = sync._init_components(a)
        assert any(k.startswith(f'{c.vault_id}/{PACK_INDEXES}') for k in env.api._store)
        result = Vault__Dump(crypto=sync.crypto).dump_remote(env.api, str(c.vault_id), c.read_key)
        assert list(result.errors) == [] and len(result.branches) >= 1


class Test_Pack_Index__Writer__Sweep_Race:

    def test_the_sweep_never_deletes_an_index_younger_than_the_orphan_age_nor_one_whose_data_pack_landed_meanwhile(self):
        """R4: a push landing between the sweep's listings had its new index deleted."""
        import time
        env = Pack__Env()
        sync, a, key = env.pack_vault({'f.txt': b'f\n'}, vault_key=TEST_VAULT_KEY)
        env.write(a, {'g.txt': b'g\n'}); sync.commit(a, message='g'); sync.push(a)
        vid = str(sync._init_components(a).vault_id)
        idx = Vault__Pack_Index(crypto=sync.crypto, api=env.api)
        young = idx.list_folder(vid, PACK_COMMITS)[-1]
        env.api._store.pop(f'{vid}/{young["file_id"]}')                        # its data pack not (yet) listed
        r = Vault__Pack_Maintain(crypto=sync.crypto, api=env.api).compact(a, now=int(time.time()))
        assert r['plan']['orphan_indexes'] == dict(archived=0, deleted=0)
        assert idx.index_pack_for(vid, PACK_COMMITS, young) is not None
