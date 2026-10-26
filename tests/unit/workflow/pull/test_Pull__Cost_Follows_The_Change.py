"""Newsroom field report, 26 Oct, item 2: a pull of a whole pass (+6,807 blobs) took
8 minutes. Three causes, three rules: the fetch does not open a folder of the head this
clone last accepted (it is complete); the new head is flattened by copying the unchanged
folders from the cached old head; the merge writes only the files whose blob changed."""
import os

from sgit_ai.storage.Vault__Object_Store  import Vault__Object_Store
from sgit_ai.storage.Vault__Sub_Tree      import Vault__Sub_Tree, FLAT_CACHE
from tests._helpers.pack_env              import Pack__Env
from tests._helpers.vault_test_env        import TEST_VAULT_KEY


class Store__Counting(Vault__Object_Store):
    loads : int = 0
    def load(self, object_id):
        self.loads += 1
        return super().load(object_id)


def _tree_files(folders, per_folder):
    return {f'raw/{c}/{s}/p{i}/file{j}.txt': f'{c}{s}{i}{j}\n'.encode()
            for c in ('uk', 'fr') for s in ('gov', 'edu') for i in range(folders) for j in range(per_folder)}


class Test_Pull__Cost_Follows_The_Change:

    def setup_method(self):
        FLAT_CACHE.clear()
        self.env = Pack__Env()
        self.files = _tree_files(4, 3)                                            # 16 leaf folders, 48 files
        self.sync, self.a, self.key = self.env.normal_vault(self.files, vault_key=TEST_VAULT_KEY)
        self.sync_b, self.b = self.env.clone(self.key, 'b')
        self.env.write(self.a, {'raw/uk/gov/p0/file0.txt': b'changed\n', 'raw/fr/edu/p9/new.txt': b'new\n'})
        self.sync.commit(self.a, message='a pass'); self.sync.push(self.a)

    def test_the_fetch_opens_only_the_changed_folders(self):
        cb    = self.sync_b._init_components(self.b)
        store = Store__Counting(vault_path=cb.sg_dir, crypto=self.sync_b.crypto)
        from sgit_ai.core.actions.pull.Vault__Sync__Pull import Vault__Sync__Pull
        puller   = Vault__Sync__Pull(crypto=self.sync_b.crypto, api=self.env.api)
        head     = self.sync_b._server_named_commit_id(str(cb.vault_id), self.sync_b._tracked_named_ref_id(self.b), cb.read_key)
        old_head = self.sync_b._read_remote_baseline(self.b, cb.storage, self.sync_b._tracked_named_ref_id(self.b))
        from sgit_ai.storage.Vault__Commit import Vault__Commit
        vc       = Vault__Commit(crypto=self.sync_b.crypto, pki=cb.pki, object_store=cb.obj_store, ref_manager=cb.ref_manager)
        old_tree = str(vc.load_commit(old_head, cb.read_key).tree_id)
        complete = set(Vault__Sub_Tree(crypto=self.sync_b.crypto, obj_store=cb.obj_store).flatten_dirs(old_tree, cb.read_key).values())
        stats = puller._fetch_missing_objects(str(cb.vault_id), head, store, cb.read_key, cb.sg_dir,
                                              stop_at=old_head, complete_trees=complete)
        # the spine to the two changed leaves: root, raw, raw/uk, raw/uk/gov, raw/uk/gov/p0, raw/fr, raw/fr/edu,
        # raw/fr/edu/p9 = 8 trees, not the 24 of the whole head
        assert stats['n_trees'] == 8 and stats['n_blobs'] == 2
        assert store.loads < 30                                                  # the commit, 8 trees, nothing else twice

    def test_the_pull_writes_only_the_changed_files(self):
        import sgit_ai.core.Vault__Sync__Base as base
        written  = []
        original = base.Vault__Sync__Base._checkout_flat_map
        def recording(self_, directory, flat_map, obj_store, read_key):
            written.extend(sorted(flat_map))
            return original(self_, directory, flat_map, obj_store, read_key)
        base.Vault__Sync__Base._checkout_flat_map = recording
        try:
            result = self.sync_b.pull(self.b)
        finally:
            base.Vault__Sync__Base._checkout_flat_map = original
        assert result['status'] in ('merged', 'fast_forward')               # a fast-forward reports 'merged'
        assert written == ['raw/fr/edu/p9/new.txt', 'raw/uk/gov/p0/file0.txt']   # not the 48 others
        with open(os.path.join(self.b, 'raw/uk/gov/p0/file0.txt'), 'rb') as f:
            assert f.read() == b'changed\n'
        assert self.sync_b.status(self.b)['clean']

    def test_the_new_head_is_flattened_from_the_old_heads_cache(self):
        self.sync_b.pull(self.b)
        cb    = self.sync_b._init_components(self.b)
        from sgit_ai.storage.Vault__Commit import Vault__Commit
        vc    = Vault__Commit(crypto=self.sync_b.crypto, pki=cb.pki, object_store=cb.obj_store, ref_manager=cb.ref_manager)
        head  = cb.ref_manager.read_ref(cb.ref_file_id, cb.read_key)
        tree  = str(vc.load_commit(head, cb.read_key).tree_id)
        sub   = Vault__Sub_Tree(crypto=self.sync_b.crypto, obj_store=cb.obj_store)
        full  = sub._flatten_walk(tree, cb.read_key, '')
        for name in list(FLAT_CACHE):                                            # keep only the OLD head in the cache
            if name == tree:
                FLAT_CACHE.pop(name)
        import shutil
        shutil.rmtree(os.path.join(cb.sg_dir, 'local', 'flat-cache'), ignore_errors=True)
        store = Store__Counting(vault_path=cb.sg_dir, crypto=self.sync_b.crypto)
        incremental = Vault__Sub_Tree(crypto=self.sync_b.crypto, obj_store=store)
        assert incremental.flatten(tree, cb.read_key) == full
        assert store.loads <= 8 + 8                                              # the changed spine, both sides
        assert incremental.flatten_dirs(tree, cb.read_key)[''] == tree

    def test_an_unrelated_base_still_gives_the_full_walks_result(self):
        other = Pack__Env()
        o_sync, o_dir, _ = other.normal_vault({'x/y.txt': b'y\n'}, vault_key=TEST_VAULT_KEY)
        cb   = self.sync_b._init_components(self.b)
        from sgit_ai.storage.Vault__Commit import Vault__Commit
        vc   = Vault__Commit(crypto=self.sync_b.crypto, pki=cb.pki, object_store=cb.obj_store, ref_manager=cb.ref_manager)
        head = cb.ref_manager.read_ref(cb.ref_file_id, cb.read_key)
        tree = str(vc.load_commit(head, cb.read_key).tree_id)
        sub  = Vault__Sub_Tree(crypto=self.sync_b.crypto, obj_store=cb.obj_store)
        full = sub._flatten_walk(tree, cb.read_key, '')
        FLAT_CACHE.clear()
        o_c  = o_sync._init_components(o_dir)                                     # the other vault's head becomes
        o_vc = Vault__Commit(crypto=o_sync.crypto, pki=o_c.pki, object_store=o_c.obj_store, ref_manager=o_c.ref_manager)   # the base
        Vault__Sub_Tree(crypto=o_sync.crypto, obj_store=o_c.obj_store).flatten(
            str(o_vc.load_commit(o_c.ref_manager.read_ref(o_c.ref_file_id, o_c.read_key), o_c.read_key).tree_id), o_c.read_key)
        assert sub.flatten(tree, cb.read_key) == full
