"""Review of 26 Oct (pack-indexes branch, quality round): the checkout verb never loses
uncommitted work (B2/F2), `--all` makes a clone full only when every file is on disk
(F1), a rewind honours the selective working copy (F4), a folder replaced by a file of
the same name (and the reverse) is written by a pull (F5), a pack clone that lost its
checkout record recovers (M2), and `sgit fetch` with no path keeps the clone sparse as
0.25.0 did (S1)."""
import os

import pytest

from sgit_ai.storage.Vault__Checkout_Set     import Vault__Checkout_Set
from tests._helpers.pack_env                 import Pack__Env
from tests._helpers.vault_test_env           import TEST_VAULT_KEY

FILES = {'raw/uk/gov/a.txt': b'a\n', 'raw/uk/gov/b.txt': b'bb\n', 'raw/fr/edu/c.txt': b'ccc\n', 'top.md': b'# top\n'}


class Test_Checkout__Guard_And_Record:

    def setup_method(self):
        self.env = Pack__Env()
        self.sync, self.a, self.key = self.env.pack_vault(dict(FILES), vault_key=TEST_VAULT_KEY)

    def _push(self, files=None, deletes=()):
        for d in deletes:
            os.remove(os.path.join(self.a, d))
        if files:
            self.env.write(self.a, files)
        cid = self.sync.commit(self.a, message='up')['commit_id']
        self.sync.push(self.a)
        return cid

    def _edited_clone(self, name='b'):
        sync_b, b = self.env.clone(self.key, name, no_checkout=True)
        sync_b.checkout(b, paths=['raw/uk/gov/a.txt'])
        self.env.write(b, {'raw/uk/gov/a.txt': b'MY EDIT\n'})
        assert sync_b.status(b)['modified'] == ['raw/uk/gov/a.txt']
        return sync_b, b

    # --- B2 / F2: uncommitted work survives a checkout ------------------------------------------------------
    def test_checkout_of_a_folder_keeps_an_edited_file_in_it_and_says_so(self):
        sync_b, b = self._edited_clone()
        warns = []
        r = sync_b.checkout(b, paths=['raw/uk'], on_progress=lambda k, t, d='': warns.append((k, t)))
        assert r['written'] == ['raw/uk/gov/b.txt'] and r['kept_dirty'] == ['raw/uk/gov/a.txt']
        assert self.env.tree(b)['raw/uk/gov/a.txt'] == b'MY EDIT\n'
        assert any(k == 'warn' and 'kept your uncommitted change' in t for k, t in warns)
        assert Vault__Checkout_Set().load(b) == {'raw/uk/gov/a.txt', 'raw/uk/gov/b.txt'}   # the kept file is held

    def test_checkout_all_and_changed_since_and_since_pull_keep_the_edit_too(self):
        sync_b, b = self._edited_clone()
        r = sync_b.checkout(b, all_files=True)
        assert r['kept_dirty'] == ['raw/uk/gov/a.txt'] and self.env.tree(b)['raw/uk/gov/a.txt'] == b'MY EDIT\n'
        assert r['full'] and not sync_b.status(b)['sparse']                 # every file is on disk: full, edit kept
        sync_c, c = self._edited_clone('c')
        base = sync_c.status(c)['clone_head']
        self._push({'raw/uk/gov/a.txt': b'a2\n', 'raw/uk/gov/b.txt': b'b2\n'})
        with pytest.raises(Exception):
            sync_c.pull(c, checkout=False)                                   # the guard: a.txt changed upstream
        self.env.write(c, {'raw/uk/gov/a.txt': b'a\n'})                       # the user puts it back ...
        sync_c.pull(c, checkout=False)
        self.env.write(c, {'raw/uk/gov/a.txt': b'MY EDIT\n'})                 # ... and edits again before the checkout
        r = sync_c.checkout(c, since_pull=True)
        assert r['kept_dirty'] == ['raw/uk/gov/a.txt'] and r['written'] == ['raw/uk/gov/b.txt']
        r = sync_c.checkout(c, changed_since=base)
        assert r['kept_dirty'] == ['raw/uk/gov/a.txt']
        assert self.env.tree(c)['raw/uk/gov/a.txt'] == b'MY EDIT\n'

    def test_checkout_force_overwrites_and_an_untracked_file_at_a_tracked_path_is_kept(self):
        sync_b, b = self._edited_clone()
        r = sync_b.checkout(b, paths=['raw/uk/gov/a.txt'], force=True)
        assert r['written'] == ['raw/uk/gov/a.txt'] and r['kept_dirty'] == []
        assert self.env.tree(b)['raw/uk/gov/a.txt'] == b'a\n'
        self.env.write(b, {'top.md': b'my own top\n'})                        # never checked out, written by hand
        r = sync_b.checkout(b, paths=['top.md'])
        assert r['kept_dirty'] == ['top.md'] and self.env.tree(b)['top.md'] == b'my own top\n'

    def test_fetch_path_is_the_same_guarded_action(self):
        sync_b, b = self._edited_clone()
        r = sync_b.sparse_fetch(b, path='raw/uk/gov')
        assert r['kept_dirty'] == ['raw/uk/gov/a.txt'] and self.env.tree(b)['raw/uk/gov/a.txt'] == b'MY EDIT\n'

    # --- F1: --all with a missing object does not make the clone full ---------------------------------------
    def test_checkout_all_with_an_object_the_host_withholds_stays_selective_and_a_later_commit_deletes_nothing(self):
        sync_l, loose, key_l = self.env.normal_vault(dict(FILES), vault_key=None)
        sync_s, s = self.env.clone(key_l, 's', sparse=True)
        flat = sync_s._get_head_flat_map(s)[0]
        vid  = str(sync_l._init_components(loose).vault_id)
        bid  = flat['raw/uk/gov/b.txt']['blob_id']
        saved = self.env.api._store.pop(f'{vid}/bare/data/{bid}')
        warns = []
        r = sync_s.checkout(s, all_files=True, on_progress=lambda k, t, d='': warns.append(t))
        assert r['missing'] == ['raw/uk/gov/b.txt'] and r['full'] is False
        assert sync_s.status(s)['sparse'] and Vault__Checkout_Set().load(s) == set(FILES) - {'raw/uk/gov/b.txt'}
        assert 'This clone stays selective' in warns
        assert sync_s.status(s)['deleted'] == []
        self.env.api._store[f'{vid}/bare/data/{bid}'] = saved
        self.env.write(s, {'notes.txt': b'my note\n'})
        sync_s.commit(s, message='a note'); sync_s.push(s)
        sync_l.pull(loose)
        assert 'raw/uk/gov/b.txt' in self.env.tree(loose)                   # nothing deleted from the vault
        r = sync_s.checkout(s, all_files=True)                               # the host recovered: now full
        assert r['full'] and not sync_s.status(s)['sparse']

    # --- S1: `sgit fetch` with no path keeps the clone sparse ----------------------------------------------
    def test_fetch_everything_writes_every_file_and_keeps_the_clone_sparse(self):
        sync_b, b = self.env.clone(self.key, 'b', no_checkout=True)
        r = sync_b.sparse_fetch(b)
        assert r['written'] == sorted(FILES) and r['full'] is False
        assert sync_b.status(b)['sparse'] and Vault__Checkout_Set().load(b) == set(FILES)
        r = sync_b.checkout(b, all_files=True)
        assert r['full'] and not sync_b.status(b)['sparse']

    # --- F4: a rewind on a selective clone ---------------------------------------------------------------------
    def _rollback_server_ref_to(self, commit_id):
        c     = self.sync._init_components(self.a)
        index = c.branch_manager.load_branch_index(self.a, c.branch_index_file_id, c.read_key)
        cfg   = self.sync._read_local_config(self.a, c.storage)
        meta  = c.branch_manager.tracked_named_branch(index, str(cfg.my_branch_id))
        self.env.api._store[f'{c.vault_id}/bare/refs/{meta.head_ref_id}'] = c.ref_manager.encrypt_ref_value(commit_id, c.read_key)

    def test_an_accepted_rewind_writes_only_what_the_selective_clone_holds(self):
        sync_b, b = self.env.clone(self.key, 'b', no_checkout=True)
        sync_b.checkout(b, paths=['top.md', 'raw/uk/gov/a.txt'])
        c1 = self._push({'raw/uk/gov/a.txt': b'a v2\n', 'raw/fr/edu/c.txt': b'c v2\n'})
        self._push({'raw/uk/gov/a.txt': b'a v3\n', 'new/n.txt': b'n\n'})
        sync_b.pull(b)                                                       # head c2; a.txt v3 on disk, c.txt never
        assert self.env.tree(b) == {'top.md': b'# top\n', 'raw/uk/gov/a.txt': b'a v3\n'}
        self._rollback_server_ref_to(c1)                                     # the owner removes c2
        r = sync_b.pull(b, accept_rewind=True)
        assert r['rewound'] is True
        assert self.env.tree(b) == {'top.md': b'# top\n', 'raw/uk/gov/a.txt': b'a v2\n'}   # c.txt still not written
        assert r['not_written'] == [] and sync_b.status(b)['clean']
        assert Vault__Checkout_Set().load(b) == {'top.md', 'raw/uk/gov/a.txt'}

    # --- F5: a folder replaced by a file of the same name, and the reverse ------------------------------------
    def test_a_pull_writes_a_file_that_replaces_a_folder_and_a_folder_that_replaces_a_file(self):
        sync_b, b = self.env.clone(self.key, 'b')
        import shutil
        shutil.rmtree(os.path.join(self.a, 'raw/uk/gov'))
        self._push({'raw/uk/gov': b'now a file\n', 'top.md/inner.txt': b'top is a folder now\n'}, deletes=['top.md'])
        sync_b.pull(b)
        tree = self.env.tree(b)
        assert tree['raw/uk/gov'] == b'now a file\n' and tree['top.md/inner.txt'] == b'top is a folder now\n'
        assert 'raw/uk/gov/a.txt' not in tree and sync_b.status(b)['clean']

    # --- M2: a pack clone that lost its checkout record ---------------------------------------------------------
    def test_a_pack_clone_without_its_record_rebuilds_it_from_disk_and_can_commit_and_push(self):
        sync_b, b = self.env.clone(self.key, 'b', no_checkout=True)
        sync_b.checkout(b, paths=['raw/uk/gov'])
        Vault__Checkout_Set().remove(b)
        st = sync_b.status(b)
        assert st['clean'] and st['deleted'] == [] and (st['files_fetched'], st['files_total']) == (2, 4)
        assert Vault__Checkout_Set().load(b) == {'raw/uk/gov/a.txt', 'raw/uk/gov/b.txt'}   # rebuilt: what is on disk
        Vault__Checkout_Set().remove(b)
        self.env.write(b, {'raw/uk/gov/a.txt': b'edited\n'})
        r = sync_b.commit(b, message='edit')
        assert r['files_changed'] == 1
        sync_b.push(b)                                                       # neither "clean" nor "uncommitted changes"
        self.sync.pull(self.a)
        assert self.env.tree(self.a)['raw/uk/gov/a.txt'] == b'edited\n' and 'top.md' in self.env.tree(self.a)

    def test_a_pack_clone_without_its_record_pulls_by_the_same_rule(self):
        sync_b, b = self.env.clone(self.key, 'b', no_checkout=True)
        sync_b.checkout(b, paths=['top.md'])
        Vault__Checkout_Set().remove(b)
        self._push({'top.md': b'# top 2\n', 'raw/fr/edu/c.txt': b'c2\n'})
        r = sync_b.pull(b)
        assert self.env.tree(b) == {'top.md': b'# top 2\n'} and r['not_written'] == ['raw/fr/edu/c.txt']
        assert Vault__Checkout_Set().load(b) == {'top.md'}

    # --- F9 (documented): --no-checkout still removes a file deleted upstream ---------------------------------
    def test_pull_no_checkout_removes_a_checked_out_file_the_commits_deleted(self):
        sync_b, b = self.env.clone(self.key, 'b', no_checkout=True)
        sync_b.checkout(b, paths=['top.md'])
        self._push(deletes=['top.md'])
        r = sync_b.pull(b, checkout=False)
        assert r['deleted'] == ['top.md'] and 'top.md' not in self.env.tree(b)   # else the next commit puts it back
        assert sync_b.status(b)['clean']
