"""0.21.0 additions from the git -> sgit security mapping: signed tags, a local
reflog, push --force-with-lease. Two real clones over the in-memory API."""
import json
import os
import pytest

from tests._helpers.vault_test_env                 import Vault__Test_Env
from sgit_ai.core.Vault__Errors                    import Vault__Tag_Error, Vault__Push_Lease_Error
from sgit_ai.schemas.Schema__Branch_Index          import Schema__Branch_Index
from sgit_ai.core.actions.index.Vault__Index_Sync  import Vault__Index_Sync


def _write(d, rel, content):
    full = os.path.join(d, rel); os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, 'w') as f: f.write(content)

def _read(d, rel):
    with open(os.path.join(d, rel)) as f: return f.read()


class _Base:
    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env(); cls._env.setup_two_clones(files={'a.txt': 'a v1'})

    @classmethod
    def teardown_class(cls):
        if cls._env: cls._env.cleanup_snapshot()

    def setup_method(self):
        self.env = self._env.restore(); self.sync = self.env.sync; self.api = self.env.api
        self.alice = self.env.alice_dir; self.bob = self.env.bob_dir
        self.c = self.sync._init_components(self.alice); self.vid = str(self.c.vault_id)
        self.index_key = f'{self.vid}/bare/indexes/{self.c.branch_index_file_id}'

    def teardown_method(self):
        self.env.cleanup()

    def _push(self, d, files, message='m'):
        for rel, content in files.items(): _write(d, rel, content)
        self.sync.commit(d, message=message); return self.sync.push(d)

    def _server_index(self):
        return Schema__Branch_Index.from_json(json.loads(self.env.crypto.decrypt(self.c.read_key, self.api._store[self.index_key])))

    def _put_server_index(self, index):
        self.api._store[self.index_key] = Vault__Index_Sync(crypto=self.env.crypto).encrypt(index, self.c.read_key)

    def _names(self, d):
        return {t['name']: t for t in self.sync.tag_list(d)}


# ------------------------------------------------------------------- tags

class Test_Tags(_Base):

    def test_create_list_show_and_a_teammate_sees_it_verified(self):
        c1 = self._push(self.alice, {'a.txt': 'release'}, 'release')['commit_id']
        r  = self.sync.tag_create(self.alice, 'v1.0', message='first release')
        assert r['commit_id'] == c1
        t = self._names(self.alice)['v1.0']
        assert t['status'] == 'verified' and t['commit_id'] == c1 and t['message'] == 'first release'
        self.sync.pull(self.bob)
        assert self._names(self.bob)['v1.0']['status'] == 'verified'
        assert self.sync.tag_show(self.bob, 'v1.0')['commit_id'] == c1
        names = [str(t.name) for t in self._server_index().tags]
        assert names == ['v1.0']                                       # in the index, which is encrypted
        assert b'v1.0' not in self.api._store[self.index_key]          # the host never sees the name

    def test_an_unpushed_commit_cannot_be_tagged(self):
        _write(self.alice, 'a.txt', 'local only'); self.sync.commit(self.alice, message='local')
        with pytest.raises(Vault__Tag_Error, match='push it first'):
            self.sync.tag_create(self.alice, 'v0')

    def test_tags_do_not_move_without_force_and_a_move_is_reported(self):
        c1 = self._push(self.alice, {'a.txt': 'one'}, 'one')['commit_id']
        self.sync.tag_create(self.alice, 'v1')
        self.sync.pull(self.bob)
        c2 = self._push(self.alice, {'a.txt': 'two'}, 'two')['commit_id']
        with pytest.raises(Vault__Tag_Error, match='already exists'):
            self.sync.tag_create(self.alice, 'v1')
        assert self.sync.tag_create(self.alice, 'v1', force=True)['moved_from'] == c1
        msgs = []
        self.sync.pull(self.bob, on_progress=lambda kind, msg, *a: msgs.append((kind, msg)))
        assert any(k == 'warn' and 'Tag v1 now points' in m for k, m in msgs), msgs
        assert self._names(self.bob)['v1']['commit_id'] == c2

    def test_a_delete_survives_a_stale_clone(self):
        self._push(self.alice, {'a.txt': 'one'}, 'one'); self.sync.tag_create(self.alice, 'v1')
        self.sync.pull(self.bob)                                       # bob's copy has the tag
        self.sync.tag_delete(self.alice, 'v1')
        self._push(self.alice, {'a.txt': 'two'}, 'two')
        self.sync.pull(self.bob)
        assert 'v1' not in self._names(self.bob)
        assert not any(not t.deleted for t in self._server_index().tags)   # bob did not bring it back

    def test_tags_dropped_by_a_writer_that_does_not_know_them_come_back(self):
        self._push(self.alice, {'a.txt': 'one'}, 'one'); self.sync.tag_create(self.alice, 'v1')
        stripped = self._server_index(); stripped.tags = []            # what a 0.20 client or the web UI writes
        self._put_server_index(stripped)
        self._push(self.bob, {'b.txt': 'b'}, 'b')
        self.sync.pull(self.alice)
        assert [str(t.name) for t in self._server_index().tags] == ['v1']

    def test_an_entry_pointing_a_name_at_another_names_object_is_bad(self):
        self._push(self.alice, {'a.txt': 'one'}, 'one'); self.sync.tag_create(self.alice, 'v1')
        idx = self._server_index()
        forged = idx.tags[0].json(); forged['name'] = 'v2'; forged['timestamp_ms'] = int(forged['timestamp_ms']) + 1
        idx.tags = [idx.tags[0].json(), forged]
        self._put_server_index(Schema__Branch_Index.from_json(idx.json()))
        tags = self._names(self.bob)
        assert tags['v1']['status'] == 'verified' and tags['v2']['status'] == 'bad'

    def test_a_tag_name_works_in_history_show_and_reset(self):
        c1 = self._push(self.alice, {'a.txt': 'tagged'}, 'tagged')['commit_id']
        self.sync.tag_create(self.alice, 'release/2026-10')
        self._push(self.alice, {'a.txt': 'later'}, 'later')
        from sgit_ai.core.actions.diff.Vault__Diff import Vault__Diff
        assert Vault__Diff(crypto=self.env.crypto).show_commit(self.alice, 'release/2026-10')[0]['commit_id'] == c1
        assert self.sync.reset(self.alice, 'release/2026-10')['commit_id'] == c1
        assert _read(self.alice, 'a.txt') == 'tagged'

    def test_invalid_names_are_refused(self):
        self._push(self.alice, {'a.txt': 'one'}, 'one')
        for bad in ('../x', 'v1..2', '-x', 'obj-cas-imm-abcdefabcdef', 'a b'):
            with pytest.raises(Vault__Tag_Error, match='not a valid tag name'):
                self.sync.tag_create(self.alice, bad)


# ----------------------------------------------------------------- reflog

class Test_Reflog(_Base):

    def test_every_head_move_is_recorded_and_can_be_undone(self):
        c1 = self._push(self.alice, {'a.txt': 'one'}, 'one')['commit_id']
        c2 = self._push(self.alice, {'a.txt': 'two'}, 'two')['commit_id']
        self.sync.reset(self.alice, c1)                                  # the "oops"
        log = self.sync.reflog(self.alice)
        assert log[0]['new'] == c1 and log[0]['old'] == c2              # newest first: the reset
        assert log[1]['new'] == c2 and log[1]['message'] == 'two'
        self.sync.reset(self.alice, log[0]['old'])                       # and back
        assert _read(self.alice, 'a.txt') == 'two'

    def test_all_refs_includes_the_named_branch(self):
        self._push(self.alice, {'a.txt': 'one'}, 'one')
        refs = {e['ref'] for e in self.sync.reflog(self.alice, all_refs=True)}
        assert 'current' in refs and len(refs) >= 2


# ------------------------------------------------------------------ lease

class Test_Force_With_Lease(_Base):

    def test_lease_refuses_when_a_teammate_pushed_and_writes_nothing(self):
        c1 = self._push(self.alice, {'a.txt': 'one'}, 'one')['commit_id']
        self.sync.pull(self.bob)
        c2 = self._push(self.alice, {'a.txt': 'two'}, 'two')['commit_id']   # bob has not seen this
        self.sync.reset(self.bob, self.sync.reflog(self.bob)[-1]['new'])     # bob rewinds his own head
        before = self.api._store[f'{self.vid}/bare/refs/{self._named_ref()}']
        with pytest.raises(Vault__Push_Lease_Error, match='someone pushed since'):
            self.sync.push(self.bob, force=True, lease='')
        assert self.api._store[f'{self.vid}/bare/refs/{self._named_ref()}'] == before and c1 and c2

    def test_lease_allows_a_deliberate_rewind_when_the_remote_is_where_we_saw_it(self):
        c1 = self._push(self.alice, {'a.txt': 'one'}, 'one')['commit_id']
        self._push(self.alice, {'a.txt': 'two'}, 'two')
        self.sync.reset(self.alice, c1)
        self.sync.push(self.alice, force=True, lease='')
        self.sync.pull(self.bob, accept_rewind=True)
        assert _read(self.bob, 'a.txt') == 'one'

    def test_an_explicit_lease_commit_must_match(self):
        c1 = self._push(self.alice, {'a.txt': 'one'}, 'one')['commit_id']
        self._push(self.alice, {'a.txt': 'two'}, 'two')
        self.sync.reset(self.alice, c1)
        with pytest.raises(Vault__Push_Lease_Error):
            self.sync.push(self.alice, force=True, lease=c1)               # the remote is at c2, not c1

    def _named_ref(self):
        return next(str(b.head_ref_id) for b in self._server_index().branches if str(b.name) == 'current')


class Test_Force_Push__From_A_Clone_Behind_The_Remote(_Base):

    def test_plain_force_push_does_not_crash_on_the_remote_heads_missing_tree(self):
        """0.20.0: the status check moved the local named ref to the server head with
        commit objects only; --force skipped the pull and died on the missing tree."""
        init = self.sync.reflog(self.bob)[-1]['new']
        self._push(self.alice, {'a.txt': 'one'}, 'one')
        self.sync.pull(self.bob)
        self._push(self.alice, {'a.txt': 'two'}, 'two')
        self.sync.reset(self.bob, init)
        assert self.sync.push(self.bob, force=True)['status'] != 'error'
        self.sync.pull(self.alice, accept_rewind=True)
        assert _read(self.alice, 'a.txt') == 'a v1'
