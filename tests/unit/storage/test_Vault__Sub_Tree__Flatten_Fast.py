"""The flatten fast path and its caches (report of 26 Oct: a status on a 38,474-folder
vault spent two minutes per flatten in Type_Safe construction, and flattened twice).
The result must be the one the schema-driven walk gave; a tree whose ids are not
object ids is refused; the second flatten of a head costs no tree reads; the on-disk
cache survives a new process and is keyed by the tree id (a content address)."""
import json
import os

import pytest

from sgit_ai.crypto.Vault__Crypto            import Vault__Crypto
from sgit_ai.schemas.Schema__Object_Tree     import Schema__Object_Tree
from sgit_ai.storage.Vault__Object_Store     import Vault__Object_Store
from sgit_ai.storage.Vault__Sub_Tree         import Vault__Sub_Tree, FLAT_CACHE
from tests._helpers.pack_env                 import Pack__Env
from tests._helpers.vault_test_env           import TEST_VAULT_KEY


class Store__Counting(Vault__Object_Store):
    loads : int = 0
    def load(self, object_id):
        self.loads += 1
        return super().load(object_id)


def _schema_flatten(sub_tree, tree_id, read_key, prefix=''):
    """The walk as it was: through Schema__Object_Tree.from_json, entry by entry."""
    out  = {}
    tree = sub_tree._load_tree(tree_id, read_key)
    for e in tree.entries:
        name = sub_tree._decrypt_name(e, read_key)
        if not name:
            continue
        p = f'{prefix}/{name}' if prefix else name
        if e.blob_id:
            out[p] = dict(blob_id=str(e.blob_id), size=sub_tree._decrypt_size(e, read_key),
                          content_hash=sub_tree._decrypt_content_hash(e, read_key),
                          content_type=sub_tree._decrypt_content_type(e, read_key), large=e.large)
        elif e.tree_id:
            out.update(_schema_flatten(sub_tree, str(e.tree_id), read_key, p))
    return out


class Test_Flatten_Fast:

    def setup_method(self):
        FLAT_CACHE.clear()
        self.env = Pack__Env()
        files = {f'raw/uk/{s}/p{i}/page.html': f'page {i}\n'.encode() for i in range(6) for s in ('gov', 'edu')}
        files['top.md'] = b'# top\n'
        self.sync, self.d, _ = self.env.normal_vault(files, vault_key=TEST_VAULT_KEY)
        self.c    = self.sync._init_components(self.d)
        commit    = self.sync.crypto  # noqa
        from sgit_ai.storage.Vault__Commit import Vault__Commit
        vc        = Vault__Commit(crypto=self.sync.crypto, pki=self.c.pki, object_store=self.c.obj_store, ref_manager=self.c.ref_manager)
        head      = self.c.ref_manager.read_ref(self.c.ref_file_id, self.c.read_key)
        self.tree = str(vc.load_commit(head, self.c.read_key).tree_id)
        self.sg   = os.path.join(self.d, '.sg_vault')

    def test_fast_flatten_equals_the_schema_walk(self):
        sub  = Vault__Sub_Tree(crypto=self.sync.crypto, obj_store=self.c.obj_store)
        fast = sub.flatten(self.tree, self.c.read_key)
        slow = _schema_flatten(sub, self.tree, self.c.read_key)
        assert fast == slow and len(fast) == 13

    def test_second_flatten_in_the_process_reads_no_tree(self):
        import shutil
        shutil.rmtree(os.path.join(self.sg, 'local', 'flat-cache'), ignore_errors=True)   # the commit wrote one
        FLAT_CACHE.clear()                                                                  # and filled this one
        store = Store__Counting(vault_path=self.sg, crypto=self.sync.crypto)
        sub   = Vault__Sub_Tree(crypto=self.sync.crypto, obj_store=store)
        first = sub.flatten(self.tree, self.c.read_key)
        n     = store.loads
        assert n >= 4                                                  # root, raw, uk, gov, edu ...
        again = sub.flatten(self.tree, self.c.read_key)
        assert store.loads == n and again == first
        again['top.md']['blob_id'] = 'changed-by-caller'               # a caller's copy, never the cache
        assert sub.flatten(self.tree, self.c.read_key)['top.md']['blob_id'] != 'changed-by-caller'

    def test_the_on_disk_cache_is_written_0600_keyed_by_tree_id_and_used_by_a_new_process(self):
        sub = Vault__Sub_Tree(crypto=self.sync.crypto, obj_store=self.c.obj_store)
        sub.flatten(self.tree, self.c.read_key)
        path = os.path.join(self.sg, 'local', 'flat-cache', self.tree + '.json')
        assert os.path.isfile(path) and (os.stat(path).st_mode & 0o777) == 0o600
        with open(path) as f:
            saved = json.load(f)
        assert saved['tree_id'] == self.tree and len(saved['flat']) == 13
        FLAT_CACHE.clear()                                             # "a new process"
        store = Store__Counting(vault_path=self.sg, crypto=self.sync.crypto)
        got   = Vault__Sub_Tree(crypto=self.sync.crypto, obj_store=store).flatten(self.tree, self.c.read_key)
        assert store.loads == 1 and len(got) == 13                      # the root tree only: the cache's consistency check

    def test_a_cache_file_for_another_tree_id_is_ignored(self):
        sub = Vault__Sub_Tree(crypto=self.sync.crypto, obj_store=self.c.obj_store)
        sub.flatten(self.tree, self.c.read_key)
        path = os.path.join(self.sg, 'local', 'flat-cache', self.tree + '.json')
        with open(path) as f:
            saved = json.load(f)
        saved['tree_id'] = 'obj-cas-imm-000000000000'                  # a planted or stale file
        with open(path, 'w') as f:
            json.dump(saved, f)
        FLAT_CACHE.clear()
        store = Store__Counting(vault_path=self.sg, crypto=self.sync.crypto)
        got   = Vault__Sub_Tree(crypto=self.sync.crypto, obj_store=store).flatten(self.tree, self.c.read_key)
        assert store.loads > 0 and len(got) == 13

    def test_a_tree_whose_ids_are_not_object_ids_is_refused(self):
        crypto = self.sync.crypto
        bad    = {'schema': 'tree_v1', 'entries': [{'blob_id': '../../etc/passwd',
                                                     'name_enc': crypto.encrypt_metadata_deterministic(self.c.read_key, 'x')}]}
        tid    = self.c.obj_store.store(crypto.encrypt_deterministic(self.c.read_key, json.dumps(bad).encode()))
        sub    = Vault__Sub_Tree(crypto=crypto, obj_store=self.c.obj_store)
        with pytest.raises(ValueError, match='not an object id'):
            sub.flatten(tid, self.c.read_key)

    def test_the_linear_builder_gives_the_same_tree_ids_as_before(self):
        """Folder entries are appended in the order the quadratic scan produced (by full
        path within a parent); the ids are content addresses, so a reorder would show."""
        sub   = Vault__Sub_Tree(crypto=self.sync.crypto, obj_store=self.c.obj_store)
        flat  = sub.flatten(self.tree, self.c.read_key)
        again = sub.build_from_flat(flat, self.c.read_key)
        assert again == self.tree


class Test_Diff_Trees:
    """The pruned diff gives what two full flattens gave: added, deleted, modified, renames
    through `_file_stat`, folders that became files and back, and the count of new folders."""

    def setup_method(self):
        FLAT_CACHE.clear()
        self.env = Pack__Env()
        files = {'a/x.txt': b'x\n', 'a/y.txt': b'y\n', 'b/z.txt': b'z\n', 'keep.md': b'keep\n', 'swap': b'a file\n'}
        self.sync, self.d, _ = self.env.normal_vault(files, vault_key=TEST_VAULT_KEY)
        self.c = self.sync._init_components(self.d)
        from sgit_ai.storage.Vault__Commit import Vault__Commit
        self.vc = Vault__Commit(crypto=self.sync.crypto, pki=self.c.pki, object_store=self.c.obj_store, ref_manager=self.c.ref_manager)
        self.old_tree = self._head_tree()

    def _head_tree(self):
        cfg  = self.sync._read_local_config(self.d, self.c.storage)                 # the CLONE branch moves on commit
        idx  = self.c.branch_manager.load_branch_index(self.d, self.c.branch_index_file_id, self.c.read_key)
        meta = self.c.branch_manager.get_branch_by_id(idx, str(cfg.my_branch_id))
        head = self.c.ref_manager.read_ref(str(meta.head_ref_id), self.c.read_key)
        return str(self.vc.load_commit(head, self.c.read_key).tree_id)

    def test_diff_matches_two_full_flattens(self):
        import shutil
        shutil.rmtree(os.path.join(self.d, 'swap'), ignore_errors=True); os.remove(os.path.join(self.d, 'swap'))
        self.env.write(self.d, {'a/x.txt': b'x2\n', 'c/n.txt': b'n\n', 'moved.txt': b'z\n', 'swap/inner.txt': b'now a folder\n'})
        os.remove(os.path.join(self.d, 'b', 'z.txt'))                              # b/z.txt -> moved.txt (a rename)
        self.sync.commit(self.d, message='changes', allow_deletions=True)
        new_tree = self._head_tree()
        sub  = Vault__Sub_Tree(crypto=self.sync.crypto, obj_store=self.c.obj_store)
        diff = sub.diff_trees(new_tree, self.old_tree, self.c.read_key)
        new_flat, old_flat = sub.flatten(new_tree, self.c.read_key), sub.flatten(self.old_tree, self.c.read_key)
        assert diff['added']    == {p: new_flat[p] for p in new_flat if p not in old_flat}
        assert diff['deleted']  == {p: old_flat[p] for p in old_flat if p not in new_flat}
        assert set(diff['modified']) == {'a/x.txt'} and diff['modified']['a/x.txt'] == (new_flat['a/x.txt'], old_flat['a/x.txt'])
        assert diff['new_dirs'] == 2                                                # c/ and swap/
        from sgit_ai.objects.Vault__Inspector import Vault__Inspector
        insp = Vault__Inspector(crypto=self.sync.crypto)
        assert insp._file_stat_from_diff(diff) == insp._file_stat(new_flat, old_flat)
        assert ('R', 'moved.txt', 'b/z.txt') in insp._file_stat_from_diff(diff)

    def test_diff_against_nothing_is_everything_added(self):
        sub  = Vault__Sub_Tree(crypto=self.sync.crypto, obj_store=self.c.obj_store)
        diff = sub.diff_trees(self.old_tree, None, self.c.read_key)
        assert set(diff['added']) == {'a/x.txt', 'a/y.txt', 'b/z.txt', 'keep.md', 'swap'} and diff['new_dirs'] == 2
        assert sub.diff_trees(self.old_tree, self.old_tree, self.c.read_key) == dict(added={}, deleted={}, modified={}, new_dirs=0)

    def test_history_log_counts_come_out_the_same(self):
        self.env.write(self.d, {'a/x.txt': b'x2\n', 'new.txt': b'n\n'}); os.remove(os.path.join(self.d, 'keep.md'))
        self.sync.commit(self.d, message='second', allow_deletions=True)
        from sgit_ai.objects.Vault__Inspector import Vault__Inspector
        chain = Vault__Inspector(crypto=self.sync.crypto).inspect_commit_chain(self.d, read_key=self.c.read_key, limit=10)
        head, first = chain[0], chain[1]
        assert (head['added'], head['modified'], head['deleted'], head['total_files']) == (1, 1, 1, 5)
        assert (first['added'], first['modified'], first['deleted'], first['total_files']) == (5, 0, 0, 5)
        assert first['new_trees'] == 2 and head['new_trees'] == 0
