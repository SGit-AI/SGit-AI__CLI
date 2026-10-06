"""A scoped clone's view of a tree: held folders as files, siblings by id —
and a rebuild from that view reproduces the whole-vault tree id exactly."""
import os, tempfile, shutil
from sgit_ai.crypto.Vault__Crypto            import Vault__Crypto
from sgit_ai.storage.Vault__Object_Store     import Vault__Object_Store
from sgit_ai.storage.Vault__Sub_Tree         import Vault__Sub_Tree
from sgit_ai.storage.Vault__Scoped_Tree      import Vault__Scoped_Tree
from sgit_ai.core.scope.Vault__Scope         import Vault__Scope

FILES = {'README.md': 'root file', 'mail/crm/a.txt': 'a', 'mail/crm/sub/b.txt': 'b',
         'mail/inbox/c.txt': 'c', 'runs/r1.json': '{}', 'docs/d.md': 'd'}


class Test_Vault__Scoped_Tree:

    def setup_method(self):
        self.tmp     = tempfile.mkdtemp()
        self.work    = os.path.join(self.tmp, 'work'); os.makedirs(self.work)
        self.crypto  = Vault__Crypto()
        self.rk      = self.crypto.derive_keys_from_vault_key('pass:vault001')['read_key_bytes']
        self.store   = Vault__Object_Store(vault_path=os.path.join(self.tmp, 'sg'), crypto=self.crypto)
        self.sub     = Vault__Sub_Tree(crypto=self.crypto, obj_store=self.store)
        self.scoped  = Vault__Scoped_Tree(crypto=self.crypto, obj_store=self.store).setup()
        for rel, content in FILES.items():
            full = os.path.join(self.work, rel); os.makedirs(os.path.dirname(full), exist_ok=True)
            open(full, 'w').write(content)
        scan = {rel: dict(size=len(c), content_hash=self.crypto.content_hash(c.encode())) for rel, c in FILES.items()}
        self.root = self.sub.build(self.work, scan, self.rk)

    def teardown_method(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_whole_scope_is_plain_flatten(self):
        flat, opaque = self.scoped.flatten(self.root, self.rk, Vault__Scope())
        assert set(flat) == set(FILES) and opaque == {}

    def test_scoped_flatten_holds_only_the_folder_and_carries_siblings_by_id(self):
        scope = Vault__Scope().with_paths(['mail/crm'])
        flat, opaque = self.scoped.flatten(self.root, self.rk, scope)
        assert set(flat) == {'mail/crm/a.txt', 'mail/crm/sub/b.txt'}
        assert set(opaque) == {'', 'mail'}                              # root and the spine folder
        assert sorted(self.sub._decrypt_name(e, self.rk) for e in opaque['']) == ['README.md', 'docs', 'runs']
        assert [self.sub._decrypt_name(e, self.rk) for e in opaque['mail']] == ['inbox']

    def test_rebuild_from_scoped_view_reproduces_the_exact_tree_id(self):
        scope = Vault__Scope().with_paths(['mail/crm'])
        flat, opaque = self.scoped.flatten(self.root, self.rk, scope)
        assert self.scoped.build_from_flat(flat, self.rk, opaque) == self.root        # byte-identical tree

    def test_edit_inside_scope_changes_only_the_spine(self):
        scope = Vault__Scope().with_paths(['mail/crm'])
        flat, opaque = self.scoped.flatten(self.root, self.rk, scope)
        before = self.sub.flatten(self.root, self.rk)
        flat['mail/crm/a.txt'] = dict(flat['mail/crm/a.txt'], blob_id=self.store.store(self.crypto.encrypt(self.rk, b'a2')),
                                      content_hash=self.crypto.content_hash(b'a2'), size=2)
        new_root = self.scoped.build_from_flat(flat, self.rk, opaque)
        after    = self.sub.flatten(new_root, self.rk)                   # the FULL tree is still readable
        assert after['mail/crm/a.txt']['blob_id'] != before['mail/crm/a.txt']['blob_id']
        for p in FILES:
            if p != 'mail/crm/a.txt':
                assert after[p]['blob_id'] == before[p]['blob_id']       # every sibling untouched
        # and the untouched sibling SUBTREES kept their ids (not just their blobs)
        _, op_before = self.scoped.flatten(self.root, self.rk, Vault__Scope().with_paths(['docs']))
        _, op_after  = self.scoped.flatten(new_root,  self.rk, Vault__Scope().with_paths(['docs']))
        ids = lambda op: sorted(str(e.tree_id or e.blob_id) for e in op[''] if self.sub._decrypt_name(e, self.rk) in ('runs', 'README.md'))
        assert ids(op_before) == ids(op_after)

    def test_two_scopes_in_one_clone(self):
        scope = Vault__Scope().with_paths(['mail/crm', 'docs'])
        flat, opaque = self.scoped.flatten(self.root, self.rk, scope)
        assert set(flat) == {'mail/crm/a.txt', 'mail/crm/sub/b.txt', 'docs/d.md'}
        assert self.scoped.build_from_flat(flat, self.rk, opaque) == self.root

    def test_walk_fetch_only_descends_into_held_and_spine_folders(self):
        scope   = Vault__Scope().with_paths(['mail/crm'])
        result  = self.scoped.walk_fetch([self.root], self.rk, scope)
        full    = self.sub.flatten(self.root, self.rk)
        assert result['small_blobs'] == {full['mail/crm/a.txt']['blob_id'], full['mail/crm/sub/b.txt']['blob_id']}
        assert len(result['trees']) == 4                                 # root, mail, mail/crm, mail/crm/sub

    def test_walk_fetch_asks_for_missing_trees_level_by_level(self):
        scope = Vault__Scope().with_paths(['mail/crm'])
        full  = self.scoped.walk_fetch([self.root], self.rk, scope)['trees']
        # drop every tree but the root from the store, keep copies to "download"
        copies = {t: self.store.load(t) for t in full}
        for t in full:
            if t != self.root:
                os.remove(self.store.object_path(t))
        asked = []
        def download(ids):
            asked.append(list(ids))
            for t in ids:
                self.store.store_raw(t, copies[t])
        result = self.scoped.walk_fetch([self.root], self.rk, scope, on_batch_missing=download)
        assert result['trees'] == full
        assert [len(a) for a in asked] == [1, 1, 1]                      # mail, mail/crm, mail/crm/sub — never runs/ or docs/

    def test_sub_tree_build_without_opaque_is_unchanged(self):
        # the full-clone path: same call, same id as before the opaque support
        scan = {rel: dict(size=len(c), content_hash=self.crypto.content_hash(c.encode())) for rel, c in FILES.items()}
        old  = self.sub.flatten(self.root, self.rk)                       # commit passes the parent's entries so blobs are reused
        assert self.sub.build(self.work, scan, self.rk, old_flat_entries=old) == self.root
        assert self.sub.build_from_flat(old, self.rk) == self.root
