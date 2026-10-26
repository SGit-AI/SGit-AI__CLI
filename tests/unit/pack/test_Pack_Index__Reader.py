"""Pack indexes, Phase 1, the reader (cli.sgit.ai dev pack 03/04, 26 Oct): a clone and a pull
take the index pack paired with each data pack in the same batch read and keep it
encrypted; a fresh clone's flat map comes from the snapshot index, a pull's fetch plan
and the new head's flat map from the commit indexes, `history log` from `changes` — each
equal to a full walk (T1), with no tree opened but the root anchor. A gap is walked
across and filled by `pack index build` (T3); a lying index is dropped and the command
walks, nothing wrong written (T4); an orphan index is ignored and a data pack without an
index is a gap (T5); a fresh clone after compaction uses the snapshot index alone (T6);
nothing new is in clear under .sg_vault (T10); a client with the reader off never lists
indexes/ and gets the same working copy (C1, the half that runs here)."""
import json
import os
import random

from sgit_ai.core.actions.pack.Vault__Packs              import PACK_COMMITS, PACK_SNAPSHOTS
from sgit_ai.core.actions.pack.Vault__Pack_Index         import (Vault__Pack_Index, PACK_INDEXES, PACK_INDEX_COMMITS,
                                                                 PACK_INDEX_SNAPSHOTS)
from sgit_ai.core.actions.pack.Vault__Pack_Index__Reader import Vault__Pack_Index__Reader, READER_ENV
from sgit_ai.core.actions.pack.Vault__Pack_Maintain      import Vault__Pack_Maintain
from sgit_ai.crypto.PKI__Crypto                          import PKI__Crypto
from sgit_ai.objects.Vault__Inspector                    import Vault__Inspector
from sgit_ai.storage.Vault__Format                       import FEATURE_SIG_REQUIRED
from sgit_ai.storage.Vault__Object_Store                 import Vault__Object_Store
from sgit_ai.storage.Vault__Sub_Tree                     import Vault__Sub_Tree, FLAT_CACHE
from tests._helpers.pack_env                             import Pack__Env
from tests._helpers.vault_test_env                       import TEST_VAULT_KEY

FILES = {'raw/uk/gov/a.txt': b'a\n', 'raw/uk/gov/b.txt': b'bb\n', 'raw/fr/edu/c.txt': b'ccc\n', 'top.md': b'# top\n'}


class Sub_Tree__Counting(Vault__Sub_Tree):
    """A real sub-tree reader that counts the trees it opens."""
    opened : int = 0

    def _load_tree_entries(self, tree_id, read_key):
        self.opened += 1
        return super()._load_tree_entries(tree_id, read_key)


class Test_Pack_Index__Reader:

    def setup_method(self):
        self.env = Pack__Env()
        self.sync, self.a, self.key = self.env.pack_vault(dict(FILES), vault_key=TEST_VAULT_KEY)
        self.c   = self.sync._init_components(self.a)
        self.vid = str(self.c.vault_id)
        self.idx = Vault__Pack_Index(crypto=self.sync.crypto, api=self.env.api)
        self.msgs = []
        FLAT_CACHE.clear()

    def teardown_method(self):
        os.environ.pop(READER_ENV, None)
        os.environ.pop('SGIT_PACK_INDEXES', None)

    # --- helpers ----------------------------------------------------------------------------------
    def _progress(self, kind, title, detail=''):
        self.msgs.append((kind, title, detail))

    def _titled(self, text: str) -> list:
        return [m for m in self.msgs if text in m[1]]

    def _push(self, files: dict = None, deletes: list = (), message: str = 'a pass'):
        if files:
            self.env.write(self.a, files)
        for rel in deletes:
            os.remove(os.path.join(self.a, rel))
        self.sync.commit(self.a, message=message)
        self.sync.push(self.a)

    def _two_passes(self):
        self._push({'raw/uk/gov/a.txt': b'a changed\n', 'raw/uk/edu/new.txt': b'new\n'}, deletes=['top.md'], message='pass one')
        self._push({'raw/fr/edu/d.txt': b'dd\n', 'raw/uk/gov/a.txt': b'a again\n'}, message='pass two')

    def _clone(self, name='b'):
        self.msgs.clear()
        sync_b, b = self.env.clone(self.key, name, on_progress=self._progress)
        return sync_b, b

    def _reader(self, sync, directory):
        c = sync._init_components(directory)
        return Vault__Pack_Index__Reader(crypto=sync.crypto, api=self.env.api).setup_for(directory, c.read_key, c=c), c

    def _walk(self, c, tree_id):
        """A full flatten through a fresh reader (no cache): the oracle."""
        sub  = Vault__Sub_Tree(crypto=self.sync.crypto, obj_store=c.obj_store)
        dirs = {}
        return sub._flatten_walk(tree_id, c.read_key, '', dirs=dirs), dirs

    def _head(self) -> str:
        """A's head commit: the pack to look at (two pushes in one second give pack names
        that sort by commit id, so a listing's last entry is not always the newest)."""
        from sgit_ai.core.actions.sparse.Vault__Sync__Sparse import Vault__Sync__Sparse
        return Vault__Sync__Sparse(crypto=self.sync.crypto, api=self.env.api)._local_head_commit(self.a, self.sync._init_components(self.a))

    def _head_pack(self) -> dict:
        head = self._head()
        return next(e for e in self.idx.list_folder(self.vid, PACK_COMMITS) if e['commit_id'] == head)

    def _other_pack(self) -> dict:
        head = self._head()
        return next(e for e in self.idx.list_folder(self.vid, PACK_COMMITS) if e['commit_id'] != head)

    def _local_index_files(self, directory: str) -> list:
        root = os.path.join(directory, '.sg_vault', 'local', 'index', 'packs')
        return sorted(os.path.relpath(os.path.join(r, f), root) for r, _, fs in os.walk(root) for f in fs)

    def _replace_host_index(self, data_folder: str, data_entry: dict, build) -> dict:
        """Rewrite the index pack beside a data pack on the host with `build(out_path) -> size`,
        under the name its new size gives; returns the new entry."""
        old = self.idx.index_pack_for(self.vid, data_folder, data_entry)
        self.env.api._store.pop(f'{self.vid}/{old["file_id"]}', None)
        out  = os.path.join(self.env.root, 'lying.zip')
        size = build(out)
        name = self.idx.pack_name(data_entry['commit_id'], size, epoch_s=data_entry['epoch'])
        with open(out, 'rb') as f:
            self.env.api._store[f'{self.vid}/{self.idx.index_folder_of(data_folder)}{name}'] = f.read()
        return self.idx.index_pack_for(self.vid, data_folder, data_entry)

    def _lying_index(self, data_folder: str, data_entry: dict, alter, signing=None):
        """A re-signed index pack for a data pack whose fields/members `alter(fields, members)`
        changed; `signing` is (private key, key id), the pusher's by default."""
        sg   = os.path.join(self.a, '.sg_vault')
        cid  = data_entry['commit_id']
        kind = 'snapshot' if data_folder == PACK_SNAPSHOTS else 'commit'
        fields, members = (self.idx.build_snapshot_members(sg, cid, self.c.read_key) if kind == 'snapshot'
                           else self.idx.build_commit_members(sg, cid, self.c.read_key))
        alter(fields, members)
        key, key_id = signing or self.idx.signing_identity(self.a)
        return self._replace_host_index(data_folder, data_entry, lambda out: self.idx.write_index_pack(
            out, self.c.read_key, kind, fields, members, [data_entry['name']], signing_key=key, author_key_id=key_id))

    # --- finding: the index packs travel with the data packs and stay encrypted ------------------
    def test_a_clone_takes_each_index_pack_in_the_batch_read_of_its_data_pack_and_keeps_it_encrypted(self):
        self._two_passes()
        self.env.api.reset_counts()
        sync_b, b = self._clone()
        assert self.env.tree(b) == self.env.tree(self.a)
        batches = [batch for batch in self.env.api.batch_reads if any('packs/' in f for f in batch)]
        assert len(batches) == 2                                                   # the snapshot, then the commit packs
        for batch in batches:
            data  = [f for f in batch if not f.startswith(PACK_INDEXES)]
            index = [f for f in batch if f.startswith(PACK_INDEXES)]
            assert len(data) == len(index) >= 1                                    # paired, in the same request
        assert sorted(self.env.api.listed_prefixes) == sorted([PACK_SNAPSHOTS, PACK_COMMITS, PACK_INDEX_SNAPSHOTS, PACK_INDEX_COMMITS])
        local = self._local_index_files(b)
        assert len([n for n in local if n.startswith('snapshots/')]) == 1 and len([n for n in local if n.startswith('commits/')]) == 2
        for rel in local:
            with open(os.path.join(b, '.sg_vault', 'local', 'index', 'packs', rel), 'rb') as f:
                blob = f.read()
            host = self.env.api.host_files(self.vid)[PACK_INDEXES + rel]
            assert blob == host and b'raw/uk' not in blob and b'a.txt' not in blob    # as downloaded: still encrypted

    # --- T6 / clone: the first flat map from the snapshot index ----------------------------------
    def test_a_fresh_clone_after_compaction_seeds_its_flat_map_from_the_snapshot_index_alone(self):
        self._two_passes()
        Vault__Pack_Maintain(crypto=self.sync.crypto, api=self.env.api).compact(self.a)
        self.env.api.reset_counts()
        sync_b, b = self._clone()
        assert self.env.tree(b) == self.env.tree(self.a)
        assert self._titled('Flat map from the pack indexes')[0][2].startswith('from the snapshot')
        assert not [f for f in self.env.api.requested_ids if f.startswith(PACK_INDEX_COMMITS)]     # the snapshot index alone
        assert self._local_index_files(b) and all(n.startswith('snapshots/') for n in self._local_index_files(b))
        reader, cb = self._reader(sync_b, b)
        head  = self.idx.list_folder(self.vid, PACK_SNAPSHOTS)[-1]['commit_id']
        tree  = self.idx.commit_fields(os.path.join(b, '.sg_vault'), head, cb.read_key)['tree_id']
        FLAT_CACHE.clear()
        counting = Sub_Tree__Counting(crypto=sync_b.crypto, obj_store=cb.obj_store)
        flat, dirs = reader.seed_head_flat(b, head, cb.read_key, counting, self._progress)
        assert counting.opened == 1 and reader.last_seed == 'snapshot'                # the root anchor, nothing else
        assert (flat, dirs) == self._walk(cb, tree)                                 # T1: equals the full walk

    def test_a_clone_of_a_head_past_the_snapshot_assembles_the_map_from_the_commit_indexes(self):
        self._two_passes()
        sync_b, b = self._clone()
        assert self.env.tree(b) == self.env.tree(self.a)
        assert self._titled('Flat map from the pack indexes')[0][2].startswith('from the deltas')
        reader, cb = self._reader(sync_b, b)
        head = self._head()
        tree = self.idx.commit_fields(os.path.join(b, '.sg_vault'), head, cb.read_key)['tree_id']
        FLAT_CACHE.clear()
        for name in os.listdir(os.path.join(b, '.sg_vault', 'local', 'flat-cache')):
            os.remove(os.path.join(b, '.sg_vault', 'local', 'flat-cache', name))
        counting = Sub_Tree__Counting(crypto=sync_b.crypto, obj_store=cb.obj_store)
        flat, dirs = reader.seed_head_flat(b, head, cb.read_key, counting, self._progress)
        assert reader.last_seed == 'deltas' and counting.opened == 2                 # the snapshot's anchor and the head's
        assert (flat, dirs) == self._walk(cb, tree)

    # --- pull: the fetch plan and the new head's map ------------------------------------------------
    def test_a_pull_plans_from_the_indexes_walks_no_tree_and_caches_the_new_head(self):
        sync_b, b = self._clone()
        self._two_passes()
        self.msgs.clear()
        FLAT_CACHE.clear()
        sync_b.pull(b, on_progress=self._progress)
        assert self.env.tree(b) == self.env.tree(self.a) and sync_b.status(b)['clean']
        plan = self._titled('Fetch plan from the pack indexes')
        assert plan and plan[0][2].startswith('2 commit(s)') and plan[0][2].endswith('all local; no tree walk')
        assert self._titled('Flat map of the new head from the pack indexes')
        assert not self._titled('Index pack dropped')
        reader, cb = self._reader(sync_b, b)
        head = self._head()
        tree = self.idx.commit_fields(os.path.join(b, '.sg_vault'), head, cb.read_key)['tree_id']
        cached = Vault__Sub_Tree(crypto=sync_b.crypto, obj_store=cb.obj_store)._flat_cached(tree, cb.read_key)
        assert cached is not None and cached == self._walk(cb, tree)                 # the merge and the status found it cached

    def test_a_three_way_pull_through_the_index_plan_merges_as_before(self):
        sync_b, b = self._clone()
        self.env.write(b, {'raw/fr/edu/mine.txt': b'mine\n'})
        sync_b.commit(b, message='mine')
        self._two_passes()
        self.msgs.clear()
        sync_b.pull(b, on_progress=self._progress)
        merged = self.env.tree(b)
        assert merged['raw/fr/edu/mine.txt'] == b'mine\n' and merged['raw/uk/gov/a.txt'] == b'a again\n' and 'top.md' not in merged
        assert self._titled('Fetch plan from the pack indexes')

    # --- T1: index equals walk over a fuzzed history ------------------------------------------------
    def test_changes_and_assembled_maps_equal_the_walk_for_every_commit_of_a_fuzzed_history(self):
        rnd    = random.Random(26)
        folders = ['raw/uk/gov', 'raw/uk/edu', 'raw/fr/edu', 'raw/fr/gov/old', 'notes']
        live   = dict(FILES)
        for n in range(12):
            files, deletes = {}, []
            for _ in range(rnd.randint(1, 4)):
                op = rnd.choice(['add', 'mod', 'del', 'rename'])
                if op == 'add' or not live:
                    path = f'{rnd.choice(folders)}/f{n}-{rnd.randint(0, 99)}.txt'
                    files[path] = f'content {n} {rnd.random()}\n'.encode()
                elif op == 'mod':
                    path = rnd.choice(sorted(live))
                    files[path] = live[path] + f'edit {n}\n'.encode()
                elif op == 'del':
                    path = rnd.choice(sorted(live))
                    if path not in files:
                        deletes.append(path)
                else:                                                         # rename: same bytes, new path
                    path = rnd.choice(sorted(live))
                    if path not in files and path not in deletes:
                        files[f'{rnd.choice(folders)}/moved{n}.txt'] = live[path]
                        deletes.append(path)
            self._push(files, deletes=[d for d in deletes if d in live], message=f'fuzz {n}')
            live.update(files)
            for d in deletes:
                live.pop(d, None)
        sync_b, b = self._clone()
        assert self.env.tree(b) == live
        reader, cb = self._reader(sync_b, b)
        sg  = os.path.join(b, '.sg_vault')
        sub = Vault__Sub_Tree(crypto=sync_b.crypto, obj_store=cb.obj_store)
        for entry in self.idx.list_folder(self.vid, PACK_COMMITS):
            cid    = entry['commit_id']
            fields = self.idx.commit_fields(sg, cid, cb.read_key)
            parent = self.idx.commit_fields(sg, fields['parents'][0], cb.read_key)['tree_id']
            diff   = sub.diff_trees(fields['tree_id'], parent, cb.read_key)
            info   = reader.changes_of_commit(b, cid, cb.read_key)
            assert info is not None
            assert {(r['path'], r['op']) for r in info['changes']} == \
                   {(p, 'A') for p in diff['added']} | {(p, 'M') for p in diff['modified']} | {(p, 'D') for p in diff['deleted']}
            FLAT_CACHE.clear()
            for name in os.listdir(os.path.join(sg, 'local', 'flat-cache')):
                os.remove(os.path.join(sg, 'local', 'flat-cache', name))
            assembled = reader.seed_head_flat(b, cid, cb.read_key, sub)
            assert assembled is not None and assembled == self._walk(cb, fields['tree_id'])
        assert reader.notes == []

    # --- history log ------------------------------------------------------------------------------
    def test_history_log_takes_counts_and_stat_from_the_indexes_and_they_equal_the_walk(self):
        self._push({'raw/uk/gov/renamed.txt': FILES['raw/uk/gov/b.txt']}, deletes=['raw/uk/gov/b.txt', 'top.md'], message='rename and delete')
        self._push({'raw/fr/edu/d.txt': b'dd\n', 'raw/uk/gov/a.txt': b'a again\n'}, message='pass two')
        sync_b, b = self._clone()
        reader, cb = self._reader(sync_b, b)
        asked    = []
        provider = reader.changes_provider(b, cb.read_key, c=cb)
        assert provider is not None
        counted  = lambda cid: (asked.append(cid), provider(cid))[1]
        inspector = Vault__Inspector(crypto=sync_b.crypto)
        with_index = inspector.inspect_commit_chain(b, read_key=cb.read_key, limit=10, changes_provider=counted)
        walked     = inspector.inspect_commit_chain(b, read_key=cb.read_key, limit=10)
        assert len(asked) == len(with_index) == 4                                   # init, first, rename, pass two
        for i, w in zip(with_index, walked):
            for key in ('commit_id', 'added', 'modified', 'deleted', 'total_files', 'stat', 'is_head'):
                assert i[key] == w[key], key
        assert with_index[1]['stat'] == [('R', 'raw/uk/gov/renamed.txt', 'raw/uk/gov/b.txt'), ('D', 'top.md', '')]

    # --- T3: gaps -----------------------------------------------------------------------------------
    def test_a_gap_is_walked_across_and_pack_index_build_fills_it(self):
        sync_b, b = self._clone()
        os.environ['SGIT_PACK_INDEXES'] = '0'                                      # an older client's pushes: no index
        try:
            self._two_passes()
        finally:
            os.environ.pop('SGIT_PACK_INDEXES', None)
        assert len(self.idx.data_packs_without_index(self.vid)) == 2
        self.msgs.clear()
        sync_b.pull(b, on_progress=self._progress)
        assert self.env.tree(b) == self.env.tree(self.a) and sync_b.status(b)['clean']
        assert not self._titled('Fetch plan from the pack indexes') and not self._titled('Flat map of the new head')
        reader, cb = self._reader(sync_b, b)
        head = self._head()
        assert reader.changes_of_commit(b, head, cb.read_key) is None               # a gap: the caller walks
        chain = Vault__Inspector(crypto=sync_b.crypto).inspect_commit_chain(b, read_key=cb.read_key, limit=3,
                                                                           changes_provider=reader.changes_provider(b, cb.read_key, c=cb))
        assert [(c['added'], c['modified'], c['deleted']) for c in chain] == [(1, 1, 0), (1, 1, 1), (4, 0, 0)]
        report = self.idx.build_missing(self.a)
        assert len(report['written']) == 2 and self.idx.data_packs_without_index(self.vid) == []
        sync_c, c = self._clone('c')                                                # the filled index serves the next clone
        assert self.env.tree(c) == self.env.tree(self.a) and self._titled('Flat map from the pack indexes')

    # --- T4: a lying index is dropped, the command walks, nothing wrong is written ----------------
    def test_a_member_whose_hash_differs_is_dropped_and_the_pull_walks(self):
        sync_b, b = self._clone()
        self._two_passes()
        entry = self._head_pack()
        index = self.idx.index_pack_for(self.vid, PACK_COMMITS, entry)
        data  = bytearray(self.idx.fetch_pack(self.vid, index))
        row   = self.idx.member_table(self.idx.read_header(bytes(data), self.c.read_key))['changes']
        data[row['offset'] + 3] ^= 0x01
        self.env.api._store[f'{self.vid}/{index["file_id"]}'] = bytes(data)
        self.msgs.clear()
        sync_b.pull(b, on_progress=self._progress)
        assert self.env.tree(b) == self.env.tree(self.a) and sync_b.status(b)['clean']
        assert self._titled('Index pack dropped') and not self._titled('Fetch plan from the pack indexes')

    def test_a_truncated_header_is_dropped_and_the_clone_walks(self):
        self._two_passes()
        Vault__Pack_Maintain(crypto=self.sync.crypto, api=self.env.api).compact(self.a)
        snap  = self.idx.list_folder(self.vid, PACK_SNAPSHOTS)[-1]
        index = self.idx.index_pack_for(self.vid, PACK_SNAPSHOTS, snap)
        data  = self.idx.fetch_pack(self.vid, index)
        self.env.api._store[f'{self.vid}/{index["file_id"]}'] = data[:60] + b'\x00' * (len(data) - 60)   # the same size, no header
        sync_b, b = self._clone()
        assert self.env.tree(b) == self.env.tree(self.a)
        assert self._titled('Index pack dropped') and not self._titled('Flat map from the pack indexes')

    def test_a_flat_whose_root_file_names_another_blob_is_dropped_by_the_anchor(self):
        self._two_passes()
        self._push({'top.md': b'# back\n'}, message='top back')
        Vault__Pack_Maintain(crypto=self.sync.crypto, api=self.env.api).compact(self.a)
        snap = self.idx.list_folder(self.vid, PACK_SNAPSHOTS)[-1]

        def alter(fields, members):
            doc = json.loads(members['flat'])
            doc['flat']['top.md']['blob_id'] = doc['flat']['raw/uk/gov/a.txt']['blob_id']     # top.md -> a.txt's bytes
            members['flat'] = self.idx.canonical_json(doc)
        self._lying_index(PACK_SNAPSHOTS, snap, alter)
        sync_b, b = self._clone()
        assert self.env.tree(b) == self.env.tree(self.a)                            # nothing wrong written
        assert self._titled('Index pack dropped')[0][2].endswith('flat member does not match the root tree')

    def test_a_header_whose_tree_id_differs_from_the_commit_is_dropped(self):
        sync_b, b = self._clone()
        self._two_passes()
        entry = self._head_pack()
        other = self._other_pack()
        sg    = os.path.join(self.a, '.sg_vault')

        def alter(fields, members):
            fields['tree_id'] = self.idx.commit_fields(sg, other['commit_id'], self.c.read_key)['tree_id']
        self._lying_index(PACK_COMMITS, entry, alter)
        self.msgs.clear()
        sync_b.pull(b, on_progress=self._progress)
        assert self.env.tree(b) == self.env.tree(self.a)
        assert self._titled('Index pack dropped')[0][2].endswith('tree_id differs from the commit object')

    def test_a_bad_signature_is_always_dropped_and_an_unsigned_index_only_under_signatures_required(self):
        sync_b, b = self._clone()
        self._two_passes()
        entry  = self._head_pack()
        _, key_id = self.idx.signing_identity(self.a)
        wrong, _  = PKI__Crypto().generate_signing_key_pair()
        self._lying_index(PACK_COMMITS, entry, lambda f, m: None, signing=(wrong, key_id))     # the pusher's key id, another key
        self.msgs.clear()
        sync_b.pull(b, on_progress=self._progress)
        assert self.env.tree(b) == self.env.tree(self.a)
        assert self._titled('Index pack dropped')[0][2].endswith('signature does not verify')
        # unsigned (no key at all): accepted on this vault, dropped once the vault requires signatures
        self._push({'raw/uk/gov/b.txt': b'b3\n'}, message='pass three')
        entry = self._head_pack()
        self._lying_index(PACK_COMMITS, entry, lambda f, m: None, signing=(None, ''))
        self.msgs.clear()
        sync_b.pull(b, on_progress=self._progress)
        assert self._titled('Fetch plan from the pack indexes') and not self._titled('Index pack dropped')
        self.sync.set_format(self.a, add_features=[FEATURE_SIG_REQUIRED])
        self._push({'raw/uk/gov/b.txt': b'b4\n'}, message='pass four')
        entry = self._head_pack()
        self._lying_index(PACK_COMMITS, entry, lambda f, m: None, signing=(None, ''))
        self.msgs.clear()
        sync_b.pull(b, on_progress=self._progress)
        assert self.env.tree(b) == self.env.tree(self.a)
        assert self._titled('Index pack dropped')[0][2].endswith('unsigned, and this vault requires signatures')

    # --- T5: orphans ---------------------------------------------------------------------------------
    def test_an_orphan_index_is_ignored_and_a_data_pack_without_one_is_a_gap(self):
        self._two_passes()
        entry = self._head_pack()
        index = self.idx.index_pack_for(self.vid, PACK_COMMITS, entry)
        data  = self.idx.fetch_pack(self.vid, index)
        orphan = self.idx.pack_name('obj-cas-imm-0000000000aa', len(data), epoch_s=entry['epoch'])
        self.env.api._store[f'{self.vid}/{PACK_INDEX_COMMITS}{orphan}'] = data            # an index with no data pack
        first = self._other_pack()
        self.env.api._store.pop(f'{self.vid}/{self.idx.index_pack_for(self.vid, PACK_COMMITS, first)["file_id"]}')   # a data pack with no index
        self.env.api.reset_counts()
        sync_b, b = self._clone()
        assert self.env.tree(b) == self.env.tree(self.a)
        assert not [f for f in self.env.api.requested_ids if f.endswith(orphan)]
        assert [os.path.basename(n) for n in self._local_index_files(b) if n.startswith('commits/')] == [index['name']]
        report = self.idx.verify_indexes(self.a)
        assert report['orphans'] == [PACK_INDEX_COMMITS + orphan] and report['gaps'] == [first['file_id']]
        assert [e['name'] for _, e in self.idx.data_packs_without_index(self.vid)] == [first['name']]

    # --- T10: nothing new in clear ------------------------------------------------------------------
    def test_nothing_new_is_in_clear_under_the_vault_folder(self):
        sync_b, b = self._clone()
        self._two_passes()
        sync_b.pull(b)
        reader, cb = self._reader(sync_b, b)
        Vault__Inspector(crypto=sync_b.crypto).inspect_commit_chain(b, read_key=cb.read_key, limit=10,
                                                                    changes_provider=reader.changes_provider(b, cb.read_key, c=cb))
        allowed = {'flat-cache', 'scan-cache.json'}                                 # what 0.25.0 already held in clear (TM-R41)
        for root, _, files in os.walk(os.path.join(b, '.sg_vault')):
            if os.path.basename(root) in allowed:
                continue
            for name in files:
                if name in allowed:
                    continue
                with open(os.path.join(root, name), 'rb') as f:
                    blob = f.read()
                assert b'raw/uk' not in blob and b'a.txt' not in blob and b'new.txt' not in blob, os.path.join(root, name)

    # --- C1 (the half that runs here): the reader off --------------------------------------------------
    def test_with_the_reader_off_nothing_under_indexes_is_listed_and_the_working_copy_is_the_same(self):
        self._two_passes()
        os.environ[READER_ENV] = '0'
        self.env.api.reset_counts()
        sync_b, b = self._clone()
        self._push({'raw/uk/gov/b.txt': b'b3\n'}, message='pass three')
        sync_b.pull(b, on_progress=self._progress)
        assert self.env.tree(b) == self.env.tree(self.a) and sync_b.status(b)['clean']
        assert not [p for p in self.env.api.listed_prefixes if p.startswith(PACK_INDEXES)]
        assert not [f for f in self.env.api.requested_ids if f.startswith(PACK_INDEXES)]
        assert not self._titled('Fetch plan') and not self._titled('Flat map')
        assert not os.path.isdir(os.path.join(b, '.sg_vault', 'local', 'index'))
