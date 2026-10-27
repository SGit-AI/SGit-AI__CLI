"""Pack indexes (0.26): a commit index whose folder member lies is dropped before it
touches a working copy (review of 26 Oct, security round, F3).

Threat model: TM-R42. A write-key holder (any teammate; with `signatures-required`, any key
in bare/keys/) could push a signed commit index whose `folder:` member omitted an
unchanged file. The reader anchored an assembled flat map to the root tree only, so the
lie passed; every puller's merge then deleted that file from disk, status was clean, and
the victim's next commit removed it from the vault under the VICTIM's key, for every
clone, through `_flatten_incremental`. A commit index's folder members are now anchored
to their own tree objects (all local on a pack vault; the cost follows the change): one
that omits, adds or re-maps a file, or names other child folders, drops its index and the
reader walks. The snapshot index's `flat` keeps the root anchor only (still TM-R42)."""
import json
import os

from sgit_ai.core.actions.pack.Vault__Packs      import PACK_COMMITS
from sgit_ai.core.actions.pack.Vault__Pack_Index import Vault__Pack_Index
from sgit_ai.storage.Vault__Sub_Tree             import FLAT_CACHE
from tests._helpers.pack_env                     import Pack__Env
from tests._helpers.vault_test_env               import TEST_VAULT_KEYS


class Test_Fixed__TM_R42__A_Lying_Commit_Index_Is_Dropped:

    def setup_method(self):
        self.env = Pack__Env()
        self.sync, self.a, self.key = self.env.pack_vault({'raw/uk/a.txt': b'a\n', 'raw/uk/b.txt': b'bb\n', 'top.md': b'# top\n'},
                                                          vault_key=TEST_VAULT_KEYS[0])
        self.sync_b, self.b = self.env.clone(self.key, 'b')
        self.c   = self.sync._init_components(self.a)
        self.vid = str(self.c.vault_id)
        self.idx = Vault__Pack_Index(crypto=self.sync.crypto, api=self.env.api)
        self.msgs = []

    def _replace_head_index(self, alter):
        """The head's commit index re-signed by the pusher's own key after alter(member)."""
        from sgit_ai.core.actions.sparse.Vault__Sync__Sparse import Vault__Sync__Sparse
        head  = Vault__Sync__Sparse(crypto=self.sync.crypto, api=self.env.api)._local_head_commit(self.a, self.c)
        entry = next(e for e in self.idx.list_folder(self.vid, PACK_COMMITS) if e['commit_id'] == head)
        old   = self.idx.index_pack_for(self.vid, PACK_COMMITS, entry)
        fields, members = self.idx.build_commit_members(os.path.join(self.a, '.sg_vault'), head, self.c.read_key)
        folder = json.loads(members['folder:raw/uk'])
        alter(folder, json.loads(members['folder:']))
        members['folder:raw/uk'] = self.idx.canonical_json(folder)
        signing_key, key_id = self.idx.signing_identity(self.a)
        out  = os.path.join(self.env.root, 'lying.zip')
        size = self.idx.write_index_pack(out, self.c.read_key, 'commit', fields, members, [entry['name']],
                                         signing_key=signing_key, author_key_id=key_id)
        self.env.api._store.pop(f'{self.vid}/{old["file_id"]}')
        with open(out, 'rb') as f:
            self.env.api._store[f'{self.vid}/{self.idx.index_folder_of(PACK_COMMITS)}{self.idx.pack_name(head, size, epoch_s=entry["epoch"])}'] = f.read()
        FLAT_CACHE.clear()

    def _pull_b(self):
        self.msgs.clear()
        return self.sync_b.pull(self.b, on_progress=lambda k, t, d='': self.msgs.append((k, t, d)))

    def _dropped(self) -> list:
        return [d for k, t, d in self.msgs if t.startswith('Index pack dropped')]

    def test_a_member_that_omits_an_unchanged_file_is_dropped_and_no_puller_deletes_it(self):
        self.env.write(self.a, {'raw/uk/a.txt': b'a2\n'}); self.sync.commit(self.a, message='c2'); self.sync.push(self.a)
        self._replace_head_index(lambda folder, root: folder['files'].pop('b.txt'))
        r = self._pull_b()
        assert r['deleted'] == [] and self.env.tree(self.b)['raw/uk/b.txt'] == b'bb\n'
        assert self._dropped() and 'does not match its tree object (files)' in self._dropped()[0]
        assert self.sync_b.status(self.b)['clean']
        self.env.write(self.b, {'top.md': b'# top edited\n'}); self.sync_b.commit(self.b, message='victim'); self.sync_b.push(self.b)
        FLAT_CACHE.clear()
        sync_c, c = self.env.clone(self.key, 'c')
        assert c and self.env.tree(c)['raw/uk/b.txt'] == b'bb\n'                   # the vault still holds it

    def test_a_member_that_re_maps_a_file_or_adds_one_or_names_another_folder_is_dropped(self):
        self.env.write(self.a, {'raw/uk/a.txt': b'a2\n'}); self.sync.commit(self.a, message='c2'); self.sync.push(self.a)

        def remap(folder, root):
            folder['files']['b.txt'] = dict(folder['files']['a.txt'])
        self._replace_head_index(remap)
        self._pull_b()
        assert self.env.tree(self.b) == self.env.tree(self.a) and self._dropped()
        self.env.write(self.a, {'raw/uk/a.txt': b'a3\n'}); self.sync.commit(self.a, message='c3'); self.sync.push(self.a)

        def add(folder, root):
            folder['files']['ghost.txt'] = dict(folder['files']['a.txt'])
        self._replace_head_index(add)
        self._pull_b()
        assert self.env.tree(self.b) == self.env.tree(self.a) and 'ghost.txt' not in self.sync_b._get_head_flat_map(self.b)[0]
        self.env.write(self.a, {'raw/uk/a.txt': b'a4\n'}); self.sync.commit(self.a, message='c4'); self.sync.push(self.a)

        def folders(folder, root):
            folder['dirs']['extra'] = folder['tree_id']
        self._replace_head_index(folders)
        self._pull_b()
        assert self.env.tree(self.b) == self.env.tree(self.a)
        assert 'does not match its tree object (folders)' in self._dropped()[0]

    def test_a_name_that_is_not_one_component_drops_the_index_before_any_write(self):
        for n, bad in enumerate(('..', '.', 'x/y', 'x\\y', 'nul\x00')):
            self.env.write(self.a, {'raw/uk/a.txt': f'a{n}\n'.encode()}); self.sync.commit(self.a, message=f'c{n}'); self.sync.push(self.a)

            def alter(folder, root, bad=bad):
                folder['files'][bad] = dict(folder['files']['a.txt'])
            self._replace_head_index(alter)
            self._pull_b()
            assert self.env.tree(self.b) == self.env.tree(self.a)
            assert self._dropped() and 'malformed' in self._dropped()[0], bad
            assert not any(bad.strip('.') and bad in p for p in self.env.tree(self.b))

    def test_control__the_real_index_is_used_and_nothing_is_dropped(self):
        self.env.write(self.a, {'raw/uk/a.txt': b'a2\n'}); self.sync.commit(self.a, message='c2'); self.sync.push(self.a)
        r = self._pull_b()
        assert r['modified'] == ['raw/uk/a.txt'] and self._dropped() == []
        assert any(t == 'Fetch plan from the pack indexes' for k, t, d in self.msgs)

    def test_a_member_that_inflates_past_the_bound_is_refused_before_the_hash(self):
        import zlib
        from sgit_ai.core.actions.pack.Vault__Pack_Index import INDEX_PLAIN_MAX
        import pytest
        sealed = self.idx.seal_member(self.c.read_key, b'{"a":1}')
        assert self.idx.open_member(self.c.read_key, sealed) == b'{"a":1}'
        bomb = self.sync.crypto.encrypt(self.c.read_key, zlib.compress(b'\0' * (INDEX_PLAIN_MAX + 1), 9))
        with pytest.raises(ValueError, match='inflates past'):
            self.idx.open_member(self.c.read_key, bomb)
