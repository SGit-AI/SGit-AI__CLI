"""The QA review of the performance branch (cli.sgit.ai, 26 Oct): one blocker and the
holes around it, each with the repro the review gave. The scan cache now keys on git's
index key (mtime, ctime, size, inode, device), records an entry only under the stat
taken before the read when the stat after the read is the same and the file was not
modified within two seconds of the scan's start, and the pull's dirty-tree guard reads
the files the merge would change whatever the cache says."""
import json
import os
import time

import pytest

from sgit_ai.core.Vault__Errors          import Vault__Dirty_Working_Tree_Error
from sgit_ai.core.Vault__Sync            import Vault__Sync
from sgit_ai.core.Vault__Sync__Base      import SCAN_CACHE_VERSION
from sgit_ai.crypto.Vault__Crypto        import Vault__Crypto
from sgit_ai.storage.Vault__Path_Guard   import Vault__Path_Guard
from tests._helpers.pack_env             import Pack__Env
from tests._helpers.vault_test_env       import TEST_VAULT_KEY


def _age(path, seconds=10):
    old = time.time() - seconds
    os.utime(path, (old, old))


def _write_keeping_mtime(path, data: bytes):
    st = os.stat(path)
    with open(path, 'wb') as f:
        f.write(data)
    os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns))           # the mtime restored: only ctime moves


def _cache(d):
    with open(os.path.join(d, '.sg_vault', 'local', 'scan-cache.json')) as f:
        return json.load(f)


class Test_Finding_1__Masked_Edits:

    def setup_method(self):
        self.env = Pack__Env()
        self.sync, self.d, self.key = self.env.normal_vault({'a.txt': b'password=hunter2\n', 'sub/b.txt': b'hello\n'},
                                                            vault_key=TEST_VAULT_KEY)
        for rel in ('a.txt', 'sub/b.txt'):
            _age(os.path.join(self.d, rel))
        assert self.sync.status(self.d)['clean']                                   # fills the cache

    def test_repro_1__a_same_size_edit_with_the_mtime_restored_is_seen_and_committed(self):
        _write_keeping_mtime(os.path.join(self.d, 'a.txt'), b'password=XXXXXXX\n')  # same size, same mtime
        st = self.sync.status(self.d)
        assert st['modified'] == ['a.txt'] and not st['clean']
        assert self.sync.commit(self.d, message='second')['files_changed'] == 1
        assert self.sync.status(self.d)['clean']

    def test_repro_2__extraction_style_mtimes_and_a_same_size_mv(self):
        epoch_1980 = 315532800
        self.env.write(self.d, {'build/v.txt': b'version=1.0.1\n', 'x.txt': b'AAAA\n', 'y.txt': b'BBBB\n'})
        for rel in ('build/v.txt', 'x.txt', 'y.txt'):
            os.utime(os.path.join(self.d, rel), (epoch_1980, epoch_1980))
        self.sync.commit(self.d, message='first')
        assert self.sync.status(self.d)['clean']
        with open(os.path.join(self.d, 'build/v.txt'), 'wb') as f:
            f.write(b'version=1.0.2\n')
        os.utime(os.path.join(self.d, 'build/v.txt'), (epoch_1980, epoch_1980))   # as a zip would leave it
        os.replace(os.path.join(self.d, 'y.txt'), os.path.join(self.d, 'x.txt'))   # same size, same mtime, other inode
        st = self.sync.status(self.d)
        assert st['modified'] == ['build/v.txt', 'x.txt'] and st['deleted'] == ['y.txt']
        self.sync.commit(self.d, message='second')
        c    = self.sync._init_components(self.d)
        from sgit_ai.core.Vault__Head_Paths import Vault__Head_Paths
        head = Vault__Head_Paths(crypto=self.sync.crypto).flat(self.d)
        assert head['x.txt']['content_hash'] == Vault__Crypto().content_hash(b'BBBB\n')
        assert head['build/v.txt']['content_hash'] == Vault__Crypto().content_hash(b'version=1.0.2\n')

    def test_repro_3__a_pull_over_a_masked_edit_refuses_and_keeps_it(self):
        sync_b, b = self.env.clone(self.key, 'b')
        self.env.write(b, {'a.txt': b'password=from-bob\n'})
        sync_b.commit(b, message='bob'); sync_b.push(b)
        p = os.path.join(self.d, 'a.txt')
        _write_keeping_mtime(p, b'password=mine-v9!\n')                               # same size, same mtime
        with pytest.raises(Vault__Dirty_Working_Tree_Error):
            self.sync.pull(self.d)
        with open(p, 'rb') as f:
            assert f.read() == b'password=mine-v9!\n'

    def test_the_dirty_guard_reads_a_touched_file_even_with_a_matching_cache_entry(self):
        """Belt and braces: whatever the cache says, a file the merge would change is read."""
        sync_b, b = self.env.clone(self.key, 'b')
        self.env.write(b, {'a.txt': b'password=from-bob\n'})
        sync_b.commit(b, message='bob'); sync_b.push(b)
        p = os.path.join(self.d, 'a.txt')
        with open(p, 'wb') as f:
            f.write(b'password=mine-v9!\n')
        cache = _cache(self.d)                                                        # forge an entry that matches
        st    = os.stat(p)                                                            # the edited file's stat exactly
        cache['files']['a.txt'] = [st.st_mtime_ns - 5 * 10**9, st.st_ctime_ns, st.st_size, st.st_ino, st.st_dev,
                                   Vault__Crypto().content_hash(b'password=hunter2\n')]
        os.utime(p, ns=(st.st_atime_ns, st.st_mtime_ns - 5 * 10**9))
        st2 = os.stat(p); cache['files']['a.txt'][1] = st2.st_ctime_ns
        with open(os.path.join(self.d, '.sg_vault', 'local', 'scan-cache.json'), 'w') as f:
            json.dump(cache, f)
        scan = self.sync._scan_local_directory(self.d)
        assert scan['a.txt']['content_hash'] == Vault__Crypto().content_hash(b'password=hunter2\n')   # the forged hit
        with pytest.raises(Vault__Dirty_Working_Tree_Error):                                        # the guard reads it
            self.sync.pull(self.d)


class Guard__Writes_During_Read(Vault__Path_Guard):
    """An editor's atomic save that lands between the scan's read and its stat."""
    target : str = ''
    def read_regular(self, full_path, rel_path=None):
        content = super().read_regular(full_path, rel_path)
        if full_path == self.target:
            with open(full_path, 'wb') as f:
                f.write(b'a much longer line after the save\n')
            _age(full_path, 10)
        return content


class Test_Finding_2__How_The_Cache_Is_Filled:

    def setup_method(self):
        self.env = Pack__Env()
        self.sync, self.d, _ = self.env.normal_vault({'notes.txt': b'short\n'}, vault_key=TEST_VAULT_KEY)
        self.p = os.path.join(self.d, 'notes.txt')
        _age(self.p)

    def test_a_write_between_the_read_and_the_stat_is_not_cached(self):
        import sgit_ai.core.Vault__Sync__Base as module
        guard = Guard__Writes_During_Read(target=self.p)
        original = module.Vault__Path_Guard
        module.Vault__Path_Guard = lambda: guard
        try:
            scan = self.sync._scan_local_directory(self.d)
        finally:
            module.Vault__Path_Guard = original
        assert scan['notes.txt']['size'] == 6                                        # what was read, this time
        assert 'notes.txt' not in _cache(self.d)['files']                            # not paired with the new stat
        assert self.sync._scan_local_directory(self.d)['notes.txt']['size'] == 34    # and read again next time

    def test_a_file_modified_within_the_racy_window_is_not_cached(self):
        """Two same-size writes in one tick of a coarse filesystem: the first is never
        recorded, so the second cannot hide behind it."""
        with open(self.p, 'wb') as f:
            f.write(b'AAAA\n')                                                       # just now
        self.sync._scan_local_directory(self.d)
        assert 'notes.txt' not in _cache(self.d)['files']
        _age(self.p)                                                                 # older than 2 s: recorded
        self.sync._scan_local_directory(self.d)
        assert 'notes.txt' in _cache(self.d)['files']

    def test_an_older_cache_format_is_discarded_not_misread(self):
        self.sync._scan_local_directory(self.d)
        cache = _cache(self.d)
        assert cache['version'] == SCAN_CACHE_VERSION and len(cache['files']['notes.txt']) == 6
        st = os.stat(self.p)
        with open(os.path.join(self.d, '.sg_vault', 'local', 'scan-cache.json'), 'w') as f:
            json.dump(dict(files={'notes.txt': [st.st_mtime_ns, st.st_size, 'a-stale-hash']}), f)   # 0.24.1's format
        assert self.sync._scan_local_directory(self.d)['notes.txt']['content_hash'] == Vault__Crypto().content_hash(b'short\n')


class Test_Finding_3__Commits_Between_With_A_Skewed_Clock:

    def test_a_merge_plus_one_clock_behind_lists_only_the_new_commits(self):
        """Base B (timestamp 5) sits on A (10); the server's head is H = merge(X(12), B).
        Expected base..head = [H, X]; a date-ordered walk listed the whole history."""
        env = Pack__Env()
        sync, d, _ = env.normal_vault({'f.txt': b'f\n'}, vault_key=TEST_VAULT_KEY)
        c  = sync._init_components(d)
        from sgit_ai.storage.Vault__Commit import Vault__Commit
        vc = Vault__Commit(crypto=sync.crypto, pki=c.pki, object_store=c.obj_store, ref_manager=c.ref_manager)
        head0 = c.ref_manager.read_ref(c.ref_file_id, c.read_key)
        tree  = str(vc.load_commit(head0, c.read_key).tree_id)
        def commit(parents, ts, msg):
            return vc.create_commit(c.read_key, tree, parent_ids=parents, message=msg, timestamp_ms=ts)
        olds = [head0]
        for i in range(5):
            olds.append(commit([olds[-1]], 1000 + i, f'old{i}'))
        A = commit([olds[-1]], 10_000, 'A')
        B = commit([A],        5_000,  'B')                                          # the clock behind
        X = commit([A],        12_000, 'X')
        H = commit([X, B],     13_000, 'H')
        from sgit_ai.core.actions.pull.Vault__Sync__Pull import Vault__Sync__Pull
        listed = Vault__Sync__Pull(crypto=sync.crypto, api=env.api)._commits_between(vc, c.read_key, H, B, c.obj_store)
        assert [short for short, _, _ in listed] == [H[12:], X[12:]]


class Test_Finding_4__Diff_Trees_With_A_Random_IV_Writer:

    def test_names_encrypted_with_a_random_iv_still_match_by_name(self):
        from sgit_ai.schemas.Schema__Object_Tree       import Schema__Object_Tree
        from sgit_ai.schemas.Schema__Object_Tree_Entry import Schema__Object_Tree_Entry
        from sgit_ai.storage.Vault__Sub_Tree           import Vault__Sub_Tree
        env = Pack__Env()
        sync, d, _ = env.normal_vault({'a.txt': b'a\n', 'b.txt': b'b\n'}, vault_key=TEST_VAULT_KEY)
        c   = sync._init_components(d)
        sub = Vault__Sub_Tree(crypto=sync.crypto, obj_store=c.obj_store)
        key = c.read_key
        blobs = {data: c.obj_store.store(sync.crypto.encrypt(key, data)) for data in (b'a\n', b'b\n', b'c\n')}
        def entry(name, data):                                                      # a writer using random IVs for
            return Schema__Object_Tree_Entry(blob_id=blobs[data], name_enc=sync.crypto.encrypt_metadata(key, name),   # the names
                                             size_enc=sync.crypto.encrypt_metadata(key, str(len(data))),
                                             content_hash_enc=sync.crypto.encrypt_metadata(key, sync.crypto.content_hash(data)),
                                             content_type_enc=sync.crypto.encrypt_metadata(key, 'text/plain'))
        old_tree = sub._store_tree(Schema__Object_Tree(schema='tree_v1', entries=[entry('a.txt', b'a\n'), entry('b.txt', b'b\n')]), key)
        new_tree = sub._store_tree(Schema__Object_Tree(schema='tree_v1', entries=[entry('a.txt', b'a\n'), entry('b.txt', b'b\n'),
                                                                                  entry('c.txt', b'c\n')]), key)
        diff = sub.diff_trees(new_tree, old_tree, key)
        assert set(diff['added']) == {'c.txt'} and not diff['deleted'] and not diff['modified']
        assert sub.flatten(new_tree, key).keys() == {'a.txt', 'b.txt', 'c.txt'}


class Test_Finding_5__Flat_Cache_Fails_Safe:

    def setup_method(self):
        from sgit_ai.storage.Vault__Sub_Tree import FLAT_CACHE
        FLAT_CACHE.clear()
        self.env = Pack__Env()
        self.sync, self.d, _ = self.env.normal_vault({'s/b.txt': b'b\n', 'top.md': b'top\n'}, vault_key=TEST_VAULT_KEY)
        self.sync.status(self.d)
        self.dir   = os.path.join(self.d, '.sg_vault', 'local', 'flat-cache')
        self.files = [os.path.join(self.dir, n) for n in os.listdir(self.dir) if n.endswith('.json')]
        self.head  = [p for p in self.files if 's/b.txt' in open(p).read()][0]

    def _replace(self, mutate):
        from sgit_ai.storage.Vault__Sub_Tree import FLAT_CACHE
        with open(self.head) as f:
            saved = json.load(f)
        mutate(saved)
        with open(self.head, 'w') as f:
            json.dump(saved, f)
        FLAT_CACHE.clear()                                                           # "a new process"

    def test_well_formed_json_with_entries_that_are_not_dicts_is_rebuilt_not_a_crash(self):
        self._replace(lambda saved: saved['flat'].update({'s/b.txt': 'not a dict'}))
        assert self.sync.status(self.d)['clean']

    def test_a_poisoned_blob_id_or_an_emptied_flat_is_a_miss(self):
        self._replace(lambda saved: saved['flat']['s/b.txt'].update(blob_id='../../etc/passwd'))
        assert self.sync.status(self.d)['clean']
        self._replace(lambda saved: saved.update(flat={}))                           # the root tree names top.md
        assert self.sync.status(self.d)['clean']                                     # and s/: not "+ top.md"
        self._replace(lambda saved: saved.update(dirs={'': saved['tree_id']}))
        assert self.sync.status(self.d)['clean']

    def test_no_version_or_another_version_is_a_miss_and_a_stale_tmp_is_pruned(self):
        self._replace(lambda saved: saved.pop('version'))
        with open(os.path.join(self.dir, 'obj-cas-imm-000000000000.tmp'), 'w') as f:
            f.write('{')
        assert self.sync.status(self.d)['clean']
        assert json.load(open(self.head))['version'] == 2                            # rewritten
        assert not [n for n in os.listdir(self.dir) if n.endswith('.tmp')]
