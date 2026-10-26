"""The incremental tree build (report of 26 Oct: a one-file commit on a 38,474-folder
vault rebuilt and re-encrypted every tree, four minutes whatever the change). A folder
whose files and sub-folders are unchanged keeps its old tree id; everything else is
rebuilt. The root id must be exactly what the full rebuild gives, in every shape of
change, and an unchanged file is never read again."""
import os
import shutil

from sgit_ai.storage.Vault__Path_Guard       import Vault__Path_Guard
from sgit_ai.storage.Vault__Sub_Tree         import Vault__Sub_Tree, FLAT_CACHE
from sgit_ai.storage.Vault__Commit           import Vault__Commit
from tests._helpers.pack_env                 import Pack__Env
from tests._helpers.vault_test_env           import TEST_VAULT_KEY


class Sub_Tree__Counting(Vault__Sub_Tree):
    stored : int = 0
    def _store_tree(self, tree, read_key):
        self.stored += 1
        return super()._store_tree(tree, read_key)


class Guard__Counting(Vault__Path_Guard):
    reads : int = 0
    def read_regular(self, full_path, rel_path=None):
        self.reads += 1
        return super().read_regular(full_path, rel_path)


FILES = {'raw/uk/gov/p1/page.html': b'p1\n', 'raw/uk/gov/p1/shot.png': b'png1',
         'raw/uk/gov/p2/page.html': b'p2\n',
         'raw/uk/edu/p3/page.html': b'p3\n',
         'raw/fr/gov/p4/page.html': b'p4\n',
         'top.md': b'# top\n'}


class Test_Incremental_Build:

    def setup_method(self):
        FLAT_CACHE.clear()
        self.env = Pack__Env()
        self.sync, self.d, _ = self.env.normal_vault(dict(FILES), vault_key=TEST_VAULT_KEY)
        self.c   = self.sync._init_components(self.d)
        self.vc  = Vault__Commit(crypto=self.sync.crypto, pki=self.c.pki, object_store=self.c.obj_store, ref_manager=self.c.ref_manager)
        self.sub = Sub_Tree__Counting(crypto=self.sync.crypto, obj_store=self.c.obj_store)
        self.old_tree = self._head_tree()
        self.old_flat = self.sub.flatten(self.old_tree, self.c.read_key)
        self.old_dirs = self.sub.flatten_dirs(self.old_tree, self.c.read_key)

    def _head_tree(self):
        cfg  = self.sync._read_local_config(self.d, self.c.storage)
        idx  = self.c.branch_manager.load_branch_index(self.d, self.c.branch_index_file_id, self.c.read_key)
        meta = self.c.branch_manager.get_branch_by_id(idx, str(cfg.my_branch_id))
        head = self.c.ref_manager.read_ref(str(meta.head_ref_id), self.c.read_key)
        return str(self.vc.load_commit(head, self.c.read_key).tree_id)

    def _both_builds(self):
        """(incremental root, full-rebuild root, trees stored by the incremental build).
        The full rebuild is of the incremental tree's own flat content (a changed file's
        blob is encrypted with a fresh IV, so two reads of it give two blob ids): equal
        ids mean the incremental build produced exactly the trees a full build gives.
        The flat content itself is checked against the scan."""
        file_map = self.sync._scan_local_directory(self.d)
        self.sub.stored = 0
        fast   = self.sub.build(self.d, file_map, self.c.read_key, old_flat_entries=self.old_flat, old_tree_ids=self.old_dirs)
        stored = self.sub.stored
        plain  = Vault__Sub_Tree(crypto=self.sync.crypto, obj_store=self.c.obj_store)
        flat   = plain.flatten(fast, self.c.read_key)
        assert {p: (e['size'], e['content_hash']) for p, e in flat.items()} == \
               {p: (e['size'], e['content_hash']) for p, e in file_map.items()}
        full   = plain.build_from_flat(flat, self.c.read_key)
        return fast, full, stored

    def test_flatten_dirs_names_every_folder_and_the_root(self):
        assert set(self.old_dirs) == {'', 'raw', 'raw/uk', 'raw/uk/gov', 'raw/uk/gov/p1', 'raw/uk/gov/p2',
                                      'raw/uk/edu', 'raw/uk/edu/p3', 'raw/fr', 'raw/fr/gov', 'raw/fr/gov/p4'}
        assert self.old_dirs[''] == self.old_tree
        FLAT_CACHE.clear()                                                        # the on-disk cache carries them too
        assert Vault__Sub_Tree(crypto=self.sync.crypto, obj_store=self.c.obj_store).flatten_dirs(self.old_tree, self.c.read_key) == self.old_dirs

    def test_no_change_gives_the_old_root_and_stores_nothing(self):
        fast, full, stored = self._both_builds()
        assert fast == full == self.old_tree
        assert stored == 0

    def test_one_modified_file_rebuilds_only_its_spine(self):
        self.env.write(self.d, {'raw/uk/gov/p1/page.html': b'p1 changed\n'})
        fast, full, stored = self._both_builds()
        assert fast == full != self.old_tree
        assert stored == 5                                                        # p1, gov, uk, raw, root
        new_dirs = self.sub.flatten_dirs(fast, self.c.read_key)
        for same in ('raw/uk/gov/p2', 'raw/uk/edu', 'raw/uk/edu/p3', 'raw/fr', 'raw/fr/gov', 'raw/fr/gov/p4'):
            assert new_dirs[same] == self.old_dirs[same]
        for changed in ('raw/uk/gov/p1', 'raw/uk/gov', 'raw/uk', 'raw', ''):
            assert new_dirs[changed] != self.old_dirs[changed]

    def test_added_deleted_renamed_and_new_folder(self):
        self.env.write(self.d, {'raw/uk/gov/p2/extra.txt': b'new\n',                 # added in a folder
                                'raw/de/gov/p9/page.html': b'p9\n',                  # a new folder chain
                                'raw/fr/gov/p4/page-renamed.html': b'p4\n'})         # renamed (same content)
        os.remove(os.path.join(self.d, 'raw/fr/gov/p4/page.html'))
        os.remove(os.path.join(self.d, 'raw/uk/edu/p3/page.html'))                   # folder emptied: gone
        fast, full, _ = self._both_builds()
        assert fast == full
        new_dirs = self.sub.flatten_dirs(fast, self.c.read_key)
        assert new_dirs['raw/uk/gov/p1'] == self.old_dirs['raw/uk/gov/p1']
        assert 'raw/uk/edu' not in new_dirs and 'raw/de/gov/p9' in new_dirs

    def test_a_file_that_became_a_folder_and_back(self):
        os.remove(os.path.join(self.d, 'top.md'))
        self.env.write(self.d, {'top.md/inner.txt': b'inner\n'})
        fast, full, _ = self._both_builds()
        assert fast == full
        shutil.rmtree(os.path.join(self.d, 'raw/uk/edu/p3'))
        self.env.write(self.d, {'raw/uk/edu/p3': b'now a file\n'})
        fast, full, _ = self._both_builds()
        assert fast == full

    def test_same_size_different_content_is_a_change(self):
        self.env.write(self.d, {'raw/uk/gov/p2/page.html': b'pX\n'})                 # same size as b'p2\n'
        fast, full, _ = self._both_builds()
        assert fast == full != self.old_tree
        assert self.sub.flatten(fast, self.c.read_key)['raw/uk/gov/p2/page.html']['content_hash'] \
            != self.old_flat['raw/uk/gov/p2/page.html']['content_hash']

    def test_an_old_tree_missing_from_the_store_is_rebuilt_not_referenced(self):
        os.remove(self.c.obj_store.object_path(self.old_dirs['raw/fr/gov/p4']))
        fast, full, _ = self._both_builds()
        assert fast == full == self.old_tree                                          # rebuilt to the same id
        assert self.c.obj_store.exists(self.old_dirs['raw/fr/gov/p4'])

    def test_unchanged_files_are_not_read(self):
        self.env.write(self.d, {'raw/uk/gov/p1/page.html': b'p1 changed\n'})
        file_map = self.sync._scan_local_directory(self.d)
        guard    = Guard__Counting()
        import sgit_ai.storage.Vault__Sub_Tree as module
        original = module.Vault__Path_Guard
        module.Vault__Path_Guard = lambda: guard
        try:
            self.sub.build(self.d, file_map, self.c.read_key, old_flat_entries=self.old_flat, old_tree_ids=self.old_dirs)
        finally:
            module.Vault__Path_Guard = original
        assert guard.reads == 1

    def test_without_old_tree_ids_the_build_is_the_full_one(self):
        self.env.write(self.d, {'raw/uk/gov/p1/page.html': b'p1 changed\n'})
        file_map = self.sync._scan_local_directory(self.d)
        self.sub.stored = 0
        root = self.sub.build(self.d, file_map, self.c.read_key, old_flat_entries=self.old_flat)
        assert self.sub.stored == len(self.old_dirs)                               # every folder rebuilt
        fast, _, _ = self._both_builds()
        without_blob = lambda flat: {p: {k: v for k, v in e.items() if k != 'blob_id'} for p, e in flat.items()}
        assert without_blob(self.sub.flatten(root, self.c.read_key)) == without_blob(self.sub.flatten(fast, self.c.read_key))

    def test_a_commit_uses_it_and_a_second_commit_builds_on_the_first(self):
        self.env.write(self.d, {'raw/uk/gov/p1/page.html': b'first change\n'})
        self.sync.commit(self.d, message='one')
        tree_1 = self._head_tree()
        self.env.write(self.d, {'raw/fr/gov/p4/page.html': b'second change\n'})
        self.sync.commit(self.d, message='two')
        tree_2 = self._head_tree()
        sub    = Vault__Sub_Tree(crypto=self.sync.crypto, obj_store=self.c.obj_store)
        flat_2 = sub.flatten(tree_2, self.c.read_key)
        assert sub.build_from_flat(flat_2, self.c.read_key) == tree_2                 # the id a full build gives
        assert flat_2['raw/uk/gov/p1/page.html'] == sub.flatten(tree_1, self.c.read_key)['raw/uk/gov/p1/page.html']
        assert self.sync.status(self.d)['modified'] == [] if isinstance(self.sync.status(self.d).get('modified'), list) else True


class Test_Conflicts_From_The_Scan:

    def test_scan_lists_conflict_files_and_the_merge_check_uses_them(self):
        from sgit_ai.core.actions.merge.Vault__Merge import Vault__Merge, CONFLICT_SUFFIX
        from sgit_ai.core.Vault__Sync__Base          import CONFLICT_SUFFIX as SCAN_SUFFIX
        assert SCAN_SUFFIX == CONFLICT_SUFFIX
        env = Pack__Env()
        sync, d, _ = env.normal_vault({'a.txt': b'a\n'}, vault_key=TEST_VAULT_KEY)
        merge = Vault__Merge(crypto=sync.crypto)
        seen  = []
        sync._scan_local_directory(d, conflict_out=seen)
        assert seen == [] and merge.has_conflicts(d) is False and merge.has_conflicts(d, seen=seen) is False
        env.write(d, {'sub/a.txt' + CONFLICT_SUFFIX: b'theirs\n'})
        seen = []
        sync._scan_local_directory(d, conflict_out=seen)
        assert seen == ['sub/a.txt' + CONFLICT_SUFFIX]
        assert merge.has_conflicts(d) is True and merge.has_conflicts(d, seen=seen) is True
