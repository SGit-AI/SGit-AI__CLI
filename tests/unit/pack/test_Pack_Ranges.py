"""Phase 2 (dev pack 01 §4, 03 §5): packs in path order, and a scoped clone of a pack vault
that takes what it holds by byte ranges. T7: `clone --path <folder>` downloads the central
directories and the folder's objects (bounded well under the packs' bytes), never a pack
whole; the working copy equals the full clone's folder; a scoped pull by ranges brings the
in-scope change only; a host without ranged reads falls back to whole packs. T8: the same
commit gives the same pack bytes; members are commits, trees depth-first by path, blobs by
path; the extraction reads a path-ordered pack as before."""
import io
import pytest
import os
import zipfile

from sgit_ai.core.actions.pack.Vault__Packs          import Vault__Packs, PACK_COMMITS, PACK_SNAPSHOTS
from sgit_ai.core.actions.pack.Vault__Pack_Index     import PACK_INDEXES
from sgit_ai.core.actions.pack.Vault__Pack_Ranges    import Vault__Pack_Ranges
from sgit_ai.core.actions.pack.Vault__Pack_Maintain  import Vault__Pack_Maintain
from sgit_ai.core.Vault__Sync                        import Vault__Sync
from sgit_ai.crypto.Vault__Crypto                    import Vault__Crypto
from sgit_ai.storage.Vault__Sub_Tree                 import Vault__Sub_Tree
from tests._helpers.pack_env                         import Pack__Env, Host__Counting
from tests._helpers.vault_test_env                   import TEST_VAULT_KEY


def _files() -> dict:
    files = {}
    for folder in ('raw/uk/gov', 'raw/uk/edu', 'raw/fr/edu', 'raw/de/bund'):
        for i in range(25):
            files[f'{folder}/f{i:02d}.txt'] = (f'{folder} {i}\n' * 40).encode()
    files['top.md'] = b'# top\n'
    return files


class Host__Without_Ranges(Host__Counting):
    """A host with no presigned route: ranged reads are refused."""
    def read_range(self, vault_id, file_id, start, end):
        raise RuntimeError('presigned_not_available: ranged reads unavailable')


class Test_Pack_Ranges:

    def setup_method(self):
        self.env = Pack__Env()
        self.sync, self.a, self.key = self.env.pack_vault(_files(), vault_key=TEST_VAULT_KEY)
        self._push({'raw/uk/gov/f00.txt': b'uk changed\n', 'raw/fr/edu/f00.txt': b'fr changed\n'}, 'p1')
        self._push({'raw/uk/gov/new.txt': b'new\n'}, 'p2')
        self.c   = self.sync._init_components(self.a)
        self.vid = str(self.c.vault_id)

    def _push(self, files, message):
        self.env.write(self.a, files); self.sync.commit(self.a, message=message); self.sync.push(self.a)

    def _packed_bytes(self) -> int:
        return sum(len(v) for k, v in self.env.api._store.items() if '/packs/' in k and '/indexes/' not in k)

    def _scope_of(self, tree: dict, folder: str) -> dict:
        return {k: v for k, v in tree.items() if k.startswith(folder + '/')}

    def _assert_bounded(self, s: str) -> None:
        """T7's bound: what came by ranges is the objects the clone holds (its store, exactly
        the scope's), with the per-member slack and the directories on top, and less than
        the packs whole."""
        held   = sum(len(v) for v in self.env.store_bytes(s).values())
        n_packs = len([k for k in self.env.api._store if '/packs/' in k and '/indexes/' not in k])
        got    = self.env.api.range_bytes
        assert got < self._packed_bytes(), (got, self._packed_bytes())
        assert got <= held * 1.3 + 4096 * n_packs + 100 * len(self.env.store_bytes(self.a)), (got, held)

    def _whole_packs(self) -> list:
        """Data packs asked for whole (a batch read or a large read), as opposed to by range."""
        api   = self.env.api
        whole = [f for batch in api.batch_reads for f in batch if f.startswith('bare/packs/') and not f.startswith(PACK_INDEXES)]
        return whole + ([f for f in api.requested_ids if f.startswith('bare/packs/') and not f.startswith(PACK_INDEXES)]
                        if api.calls['read_large'] else [])

    # --- T7: the scoped clone and its pulls by ranges --------------------------------------------------
    def test_a_scoped_clone_takes_its_folder_by_ranges_and_never_a_pack_whole(self):
        self.env.api.reset_counts()
        msgs = []
        sync_s, s = self.env.clone(self.key, 's', scope_paths=['raw/uk'], on_progress=lambda k, t, d='': msgs.append((k, t, d)))
        assert any(t == 'Scoped fetch by ranges' for _, t, _ in msgs) and not any('whole' in t for _, t, _ in msgs)
        assert not self._whole_packs() and not [f for f in self.env.api.requested_ids if f.startswith('bare/data/')]   # no pack whole, no loose object
        assert self.env.api.calls['read_range'] > 0
        self._assert_bounded(s)                                                        # the folder's bytes, not the packs'
        sync_f, f = self.env.clone(self.key, 'f')
        assert self.env.tree(s) == self._scope_of(self.env.tree(f), 'raw/uk')
        assert sync_s.status(s)['clean']
        assert os.path.isdir(os.path.join(s, '.sg_vault', 'local', 'index', 'cd'))     # the directories, kept

    def test_a_scoped_clone_holds_the_folders_history_like_a_loose_scoped_clone(self):
        sync_s, s = self.env.clone(self.key, 's', scope_paths=['raw/uk'])
        cs   = sync_s._init_components(s)
        sub  = Vault__Sub_Tree(crypto=sync_s.crypto, obj_store=cs.obj_store)
        from sgit_ai.objects.Vault__Inspector import Vault__Inspector
        chain = Vault__Inspector(crypto=sync_s.crypto).inspect_commit_chain(s, read_key=cs.read_key, limit=10)
        assert [c['message'] for c in chain] == ['p2', 'p1', 'first', 'init']           # every commit of the history
        p1 = next(c for c in chain if c['message'] == 'p1')
        assert cs.obj_store.exists(p1['tree_id'])                                       # its spine ...
        old = sub._entries_by_name(p1['tree_id'], cs.read_key)['raw']
        uk  = sub._entries_by_name(str(old['tree_id']), cs.read_key)['uk']
        assert cs.obj_store.exists(str(uk['tree_id']))                                  # ... and its held folder
        assert not cs.obj_store.exists(str(sub._entries_by_name(str(old['tree_id']), cs.read_key)['fr']['tree_id']))   # not the siblings

    def test_a_scoped_pull_by_ranges_brings_the_in_scope_change_only(self):
        sync_s, s = self.env.clone(self.key, 's', scope_paths=['raw/uk'])
        self._push({'raw/uk/gov/f01.txt': b'uk again\n'}, 'p3')
        self._push({'raw/fr/edu/f01.txt': b'fr again\n'}, 'p4')
        self.env.api.reset_counts()
        r = sync_s.pull(s)
        assert r['status'] == 'merged' and r['modified'] == ['raw/uk/gov/f01.txt']
        assert self.env.tree(s)['raw/uk/gov/f01.txt'] == b'uk again\n' and 'raw/fr/edu/f01.txt' not in self.env.tree(s)
        assert self.env.api.calls['read_range'] > 0 and not self._whole_packs()
        assert sync_s.status(s)['clean']
        self.env.write(s, {'raw/uk/gov/mine.txt': b'mine\n'}); sync_s.commit(s, message='mine'); sync_s.push(s)
        sync_f, f = self.env.clone(self.key, 'f')
        assert self.env.tree(f)['raw/uk/gov/mine.txt'] == b'mine\n' and self.env.tree(f)['raw/fr/edu/f01.txt'] == b'fr again\n'

    def test_a_scoped_clone_after_compaction_reads_the_snapshot_by_ranges(self):
        Vault__Pack_Maintain(crypto=self.sync.crypto, api=self.env.api).compact(self.a)
        self.env.api.reset_counts()
        sync_s, s = self.env.clone(self.key, 's', scope_paths=['raw/de'])
        sync_f, f = self.env.clone(self.key, 'f')
        assert self.env.tree(s) == self._scope_of(self.env.tree(f), 'raw/de')
        self._assert_bounded(s)

    def test_a_depth_limited_scoped_clone_walks_that_many_commits(self):
        sync_s, s = self.env.clone(self.key, 's', scope_paths=['raw/uk'], depth=1)
        cs = sync_s._init_components(s)
        from sgit_ai.objects.Vault__Inspector import Vault__Inspector
        chain = Vault__Inspector(crypto=sync_s.crypto).inspect_commit_chain(s, read_key=cs.read_key, limit=10)
        assert [c.get('message') for c in chain][:1] == ['p2'] and len([c for c in chain if 'error' not in c]) == 1
        assert self.env.tree(s) == self._scope_of(self.env.tree(self.a), 'raw/uk')

    def test_a_host_without_ranged_reads_takes_the_packs_whole_and_the_clone_is_the_same(self):
        api = Host__Without_Ranges().setup(); api._store = self.env.api._store
        sync = Vault__Sync(crypto=Vault__Crypto(), api=api)
        msgs = []
        s = self.env.path('s')
        sync.clone(self.key, s, scope_paths=['raw/uk'], on_progress=lambda k, t, d='': msgs.append((k, t, d)))
        assert any('taking the packs whole' in t for _, t, _ in msgs)
        assert self.env.tree(s) == self._scope_of(self.env.tree(self.a), 'raw/uk') and sync.status(s)['clean']

    # --- the directory read -------------------------------------------------------------------------------
    def test_the_central_directory_is_read_once_and_matches_the_zip(self):
        ranges = Vault__Pack_Ranges(crypto=self.sync.crypto, api=self.env.api)
        entry  = self.env.api.packs(self.vid, PACK_SNAPSHOTS)[0]
        entry  = next(e for e in ranges.list_folder(self.vid, PACK_SNAPSHOTS) if e['file_id'] == entry)
        self.env.api.reset_counts()
        members = ranges.central_directory(self.a, self.vid, entry)
        reads = self.env.api.calls['read_range']
        data  = self.env.api.host_files(self.vid)[entry['file_id']]
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            expect = {i.filename.rsplit('/', 1)[-1]: (i.header_offset, len(i.filename), i.file_size) for i in z.infolist()}
        assert members == expect and 1 <= reads <= 2
        assert ranges.central_directory(self.a, self.vid, entry) == expect and self.env.api.calls['read_range'] == reads   # cached

    # --- T8: path order and determinism ----------------------------------------------------------------------
    def test_a_commit_pack_is_deterministic_and_in_path_order(self):
        packs = Vault__Packs(crypto=self.sync.crypto, api=self.env.api)
        sg    = os.path.join(self.a, '.sg_vault')
        from sgit_ai.core.actions.sparse.Vault__Sync__Sparse import Vault__Sync__Sparse
        head_id = Vault__Sync__Sparse(crypto=self.sync.crypto, api=self.env.api)._local_head_commit(self.a, self.c)
        head  = next(e for e in packs.list_folder(self.vid, PACK_COMMITS) if e['commit_id'] == head_id)   # p2, by commit
        work  = os.path.join(self.env.root, 'work'); os.makedirs(work, exist_ok=True)
        p1, n1 = packs.build_commit_pack(sg, head['commit_id'], self.c.read_key, work)
        b1 = open(p1, 'rb').read(); os.remove(p1)
        p2, n2 = packs.build_commit_pack(sg, head['commit_id'], self.c.read_key, work)
        b2 = open(p2, 'rb').read()
        assert b1 == b2 and n1 == n2 and b1 == self.env.api.host_files(self.vid)[head['file_id']]   # the host holds the same bytes
        with zipfile.ZipFile(io.BytesIO(b1)) as z:
            names = [i.filename.rsplit('/', 1)[-1] for i in z.infolist()]
        assert names[0] == head['commit_id']                                             # the commit first
        from sgit_ai.core.actions.pack.Vault__Pack_Index import Vault__Pack_Index
        sub  = Vault__Sub_Tree(crypto=self.sync.crypto, obj_store=self.c.obj_store)
        tree = Vault__Pack_Index(crypto=self.sync.crypto, api=self.env.api).commit_fields(sg, head['commit_id'], self.c.read_key)['tree_id']
        dirs = sub.flatten_dirs(tree, self.c.read_key)
        trees_in_order = [n for n in names if n in set(dirs.values())]
        assert trees_in_order == [dirs[''], dirs['raw'], dirs['raw/uk'], dirs['raw/uk/gov']]   # depth first, root first
        assert packs.extract_pack(b1, os.path.join(self.env.root, 'x'), self.c.read_key)['extracted'] == len(names)   # read as before

    def test_a_snapshot_pack_is_in_path_order_with_older_versions_last(self):
        packs = Vault__Packs(crypto=self.sync.crypto, api=self.env.api)
        sg    = os.path.join(self.a, '.sg_vault')
        snap  = packs.list_folder(self.vid, PACK_SNAPSHOTS)[0]
        data  = self.env.api.host_files(self.vid)[snap['file_id']]
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            names = [i.filename.rsplit('/', 1)[-1] for i in z.infolist()]
        commits = packs.reachable_commits(sg, snap['commit_id'], self.c.read_key)
        n = len(commits)
        assert set(names[:n]) == commits and names[:n] == sorted(commits)                # the commits by id, first
        from sgit_ai.core.actions.pack.Vault__Pack_Index import Vault__Pack_Index
        tree = Vault__Pack_Index(crypto=self.sync.crypto, api=self.env.api).commit_fields(sg, snap['commit_id'], self.c.read_key)['tree_id']
        sub  = Vault__Sub_Tree(crypto=self.sync.crypto, obj_store=self.c.obj_store)
        flat = sub.flatten(tree, self.c.read_key)
        blob_order = [n for n in names if n in {e['blob_id'] for e in flat.values()}]

        def walk(prefix):                                                                # the writer's order: a folder's
            here  = sorted(p for p in flat if p.rpartition('/')[0] == prefix)            # files by name, then its
            subs  = sorted({p[len(prefix) + 1 if prefix else 0:].split('/')[0]              # subfolders by name
                            for p in flat if (p.startswith(prefix + '/') if prefix else True) and '/' in p[len(prefix) + 1 if prefix else 0:]})
            out   = [flat[p]['blob_id'] for p in here]
            for sub in subs:
                out += walk(f'{prefix}/{sub}' if prefix else sub)
            return out
        seen, expect = set(), []
        for b in walk(''):                                                               # each blob once, by first use
            if b not in seen:
                seen.add(b); expect.append(b)
        assert blob_order == expect


class Test_Pack_Ranges__Review_26_Oct:
    """The build agent's and the quality round's findings on Phase 2."""

    def _files(self):
        return {f'{folder}/f{i:02d}.txt': (f'{folder} {i}\n' * 40).encode() for folder in ('raw/uk/gov', 'raw/fr/edu') for i in range(5)}

    def test_a_pack_with_a_refused_ranged_member_is_read_again_on_the_next_pull(self):
        """F6: a corrupt range from the host used to leave the pack recorded as absorbed
        and the head commit local, so every later pull said 'Pull incomplete' for good."""
        import json, zipfile
        from sgit_ai.core.actions.pack.Vault__Packs import PACK_COMMITS
        env = Pack__Env()
        sync, a, key = env.pack_vault(self._files(), vault_key=TEST_VAULT_KEY)
        sync_s, s = env.clone(key, 's', scope_paths=['raw/uk'])
        env.write(a, {'raw/uk/gov/new.txt': b'new content here, long enough to be a member over sixty bytes\n' * 3})
        sync.commit(a, message='p3'); sync.push(a)
        vid   = str(sync._init_components(a).vault_id)
        key_p = sorted(k for k in env.api._store if k.startswith(f'{vid}/{PACK_COMMITS}'))[-1]
        name  = key_p.rsplit('/', 1)[-1]
        data  = bytearray(env.api._store[key_p])
        with zipfile.ZipFile(io.BytesIO(bytes(data))) as z:
            blob = z.infolist()[-1]                                            # path order: the blob is last
        off = blob.header_offset + 30 + len(blob.filename) + len(blob.extra)
        original = bytes(data); data[off + 5] ^= 0xFF; env.api._store[key_p] = bytes(data)
        with pytest.raises(RuntimeError, match='Pull incomplete'):
            sync_s.pull(s)
        absorbed = os.path.join(s, '.sg_vault', 'local', 'packs_absorbed.json')
        assert name not in json.load(open(absorbed))['packs']                   # not absorbed: read again
        env.api._store[key_p] = original                                       # the host is repaired
        r = sync_s.pull(s)
        assert r['added'] == ['raw/uk/gov/new.txt'] and env.tree(s)['raw/uk/gov/new.txt'].startswith(b'new content')
        assert name in json.load(open(absorbed))['packs']
        assert sync_s.pull(s)['status'] == 'up_to_date'

    def test_path_order_opens_only_the_trees_in_the_pack(self):
        """B1: ordering a commit pack's few objects used to walk the whole head (13 s
        cold on the 76,000-file vault for 9 objects). Only a tree in the pack is opened:
        a tree the pack does not carry is unchanged, so nothing under it is new."""
        from sgit_ai.core.actions.pack.Vault__Packs import PACK_COMMITS
        from sgit_ai.crypto.Vault__Crypto import Vault__Crypto

        class Crypto__Counting(Vault__Crypto):
            decrypts : int = 0

            def decrypt(self, key, data):
                self.decrypts += 1
                return super().decrypt(key, data)

        env   = Pack__Env()
        files = {f'wide/d{i:03d}/f.txt': f'file {i}\n'.encode() for i in range(60)}
        sync, a, key = env.pack_vault(files, vault_key=TEST_VAULT_KEY)
        env.write(a, {'wide/d007/f.txt': b'changed\n'}); sync.commit(a, message='one folder'); sync.push(a)
        c      = sync._init_components(a)
        sg     = os.path.join(a, '.sg_vault')
        crypto = Crypto__Counting()
        packs  = Vault__Packs(crypto=crypto, api=env.api)
        head   = next(e for e in packs.list_folder(str(c.vault_id), PACK_COMMITS) if e['commit_id'] == sync.status(a)['clone_head'])
        ids    = packs.objects_introduced(sg, head['commit_id'], c.read_key)
        crypto.decrypts = 0
        order  = packs.path_order(sg, head['commit_id'], c.read_key, ids, commits=[head['commit_id']])
        assert sorted(order) == sorted(ids) and order[0] == head['commit_id']
        assert crypto.decrypts <= 1 + 3 + 62                                   # the commit, 3 trees and the names in them:
        full = packs.path_order(sg, head['commit_id'], c.read_key, ids)        # not the 60 sibling folders
        assert full == order                                                   # the same order with the commits walked

    def test_fetch_packs_keys_by_file_id_so_a_same_sized_index_pack_cannot_shadow_its_data_pack(self):
        """F12: a data pack and its index pack of the same byte size share the name key."""
        env = Pack__Env()
        sync, a, key = env.pack_vault({'f.txt': b'x\n'}, vault_key=TEST_VAULT_KEY)
        vid   = str(sync._init_components(a).vault_id)
        packs = Vault__Packs(crypto=sync.crypto, api=env.api)
        env.api._store[f'{vid}/bare/packs/commits/0000000001__obj-cas-imm-{"a" * 32}__3.zip'] = b'one'
        env.api._store[f'{vid}/bare/packs/indexes/commits/0000000001__obj-cas-imm-{"a" * 32}__3.zip'] = b'two'
        name = f'0000000001__obj-cas-imm-{"a" * 32}__3.zip'
        got  = packs.fetch_packs(vid, [dict(name=name, size=3, file_id='bare/packs/commits/' + name),
                                       dict(name=name, size=3, file_id='bare/packs/indexes/commits/' + name)])
        assert got['bare/packs/commits/' + name] == b'one' and got['bare/packs/indexes/commits/' + name] == b'two'
