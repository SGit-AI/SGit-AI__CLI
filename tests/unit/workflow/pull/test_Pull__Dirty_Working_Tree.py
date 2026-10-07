"""`sgit pull` must never discard uncommitted work (bug report, 3 Oct 2026).

Two real clones (alice, bob) of one vault on the in-memory API. Bob commits and
pushes; alice has uncommitted edits; alice pulls."""
import os
import pytest

from tests._helpers.vault_test_env                       import Vault__Test_Env
from sgit_ai.core.Vault__Errors                          import Vault__Dirty_Working_Tree_Error
from sgit_ai.core.actions.pull.Vault__Pull__Guard        import Vault__Pull__Guard


def _write(directory, rel, content):
    full = os.path.join(directory, rel)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, 'w') as f:
        f.write(content)

def _read(directory, rel):
    with open(os.path.join(directory, rel)) as f:
        return f.read()


class _TwoClones:
    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_two_clones(files={'x.txt': 'x v1', 'y.txt': 'y v1', 'docs/z.md': 'z v1'})

    @classmethod
    def teardown_class(cls):
        if cls._env:
            cls._env.cleanup_snapshot()

    def setup_method(self):
        self.env   = self._env.restore()
        self.sync  = self.env.sync
        self.alice = self.env.alice_dir
        self.bob   = self.env.bob_dir

    def teardown_method(self):
        self.env.cleanup()

    def _bob_pushes(self, files: dict, message='bob'):
        for rel, content in files.items():
            _write(self.bob, rel, content)
        self.sync.commit(self.bob, message=message)
        self.sync.push(self.bob)

    def _alice_head(self):
        return self.sync.status(self.alice).get('clone_head') or self.sync.status(self.alice).get('head')


class Test_Pull__Fast_Forward__Keeps_Uncommitted_Edits(_TwoClones):

    def test_the_reported_case__edit_to_an_untouched_file_survives(self):
        self._bob_pushes({'x.txt': 'x v2 (from B)'})
        _write(self.alice, 'y.txt', 'y v2 (UNCOMMITTED in A)')
        assert self.sync.status(self.alice)['modified'] == ['y.txt']

        result = self.sync.pull(self.alice)

        assert _read(self.alice, 'y.txt') == 'y v2 (UNCOMMITTED in A)'          # the edit is still there (the bug: 'y v1')
        assert _read(self.alice, 'x.txt') == 'x v2 (from B)'
        assert self.sync.status(self.alice)['modified'] == ['y.txt']             # and status still sees it
        assert result['status']     == 'merged'
        assert result['modified']   == ['x.txt']
        assert result['kept_dirty'] == ['y.txt']

    def test_edit_to_a_file_the_incoming_commit_changes_refuses_before_writing(self):
        self._bob_pushes({'x.txt': 'x v2 (from B)', 'docs/z.md': 'z v2'})
        _write(self.alice, 'x.txt', 'x edited (UNCOMMITTED in A)')
        head_before = self.sync.status(self.alice)

        with pytest.raises(Vault__Dirty_Working_Tree_Error) as exc:
            self.sync.pull(self.alice)

        msg = str(exc.value)
        assert 'x.txt' in msg and 'overwritten' in msg and 'stash' in msg
        assert _read(self.alice, 'x.txt')    == 'x edited (UNCOMMITTED in A)'   # untouched
        assert _read(self.alice, 'docs/z.md') == 'z v1'                          # nothing else applied either
        after = self.sync.status(self.alice)
        assert after['modified'] == ['x.txt']
        assert after['behind']   == head_before['behind']                        # clone ref did not move

    def test_after_committing_the_refused_pull_becomes_a_merge(self):
        self._bob_pushes({'x.txt': 'x v2 (from B)'})
        _write(self.alice, 'y.txt', 'y v2 alice')
        self.sync.commit(self.alice, message='alice edits y')
        result = self.sync.pull(self.alice)
        assert result['status'] in ('merged',)
        assert _read(self.alice, 'x.txt') == 'x v2 (from B)'
        assert _read(self.alice, 'y.txt') == 'y v2 alice'

    def test_locally_deleted_untouched_file_stays_deleted(self):
        self._bob_pushes({'x.txt': 'x v2 (from B)'})
        os.remove(os.path.join(self.alice, 'y.txt'))
        result = self.sync.pull(self.alice)
        assert result['status'] == 'merged'
        assert not os.path.exists(os.path.join(self.alice, 'y.txt'))
        assert result['kept_dirty'] == ['y.txt']
        assert self.sync.status(self.alice)['deleted'] == ['y.txt']

    def test_locally_deleted_file_that_the_incoming_commit_changes_is_refused(self):
        self._bob_pushes({'y.txt': 'y v2 (from B)'})
        os.remove(os.path.join(self.alice, 'y.txt'))
        with pytest.raises(Vault__Dirty_Working_Tree_Error, match='y.txt'):
            self.sync.pull(self.alice)

    def test_untracked_file_colliding_with_an_incoming_file_is_refused(self):
        self._bob_pushes({'new.txt': 'from bob'})
        _write(self.alice, 'new.txt', 'alice wrote this first, uncommitted')
        with pytest.raises(Vault__Dirty_Working_Tree_Error, match='new.txt'):
            self.sync.pull(self.alice)
        assert _read(self.alice, 'new.txt') == 'alice wrote this first, uncommitted'

    def test_untracked_file_identical_to_the_incoming_one_is_fine(self):
        self._bob_pushes({'new.txt': 'same bytes'})
        _write(self.alice, 'new.txt', 'same bytes')
        result = self.sync.pull(self.alice)
        assert result['status'] == 'merged'
        assert _read(self.alice, 'new.txt') == 'same bytes'

    def test_unrelated_untracked_file_is_left_alone(self):
        self._bob_pushes({'x.txt': 'x v2'})
        _write(self.alice, 'scratch.txt', 'not committed, not incoming')
        result = self.sync.pull(self.alice)
        assert result['status'] == 'merged'
        assert _read(self.alice, 'scratch.txt') == 'not committed, not incoming'

    def test_clean_tree_pull_is_unchanged(self):
        self._bob_pushes({'x.txt': 'x v2', 'docs/z.md': 'z v2'})
        result = self.sync.pull(self.alice)
        assert result['status'] == 'merged'
        assert sorted(result['modified']) == ['docs/z.md', 'x.txt']
        assert result['kept_dirty'] == []
        assert self.sync.status(self.alice)['clean'] is True


class Test_Pull__Three_Way__Keeps_Uncommitted_Edits(_TwoClones):

    def _diverge(self):
        self._bob_pushes({'x.txt': 'x v2 (from B)'})
        _write(self.alice, 'docs/z.md', 'z v2 (alice, committed)')
        self.sync.commit(self.alice, message='alice edits z')           # alice is now ahead AND behind

    def test_dirty_untouched_file_survives_a_three_way_merge(self):
        self._diverge()
        _write(self.alice, 'y.txt', 'y v2 (UNCOMMITTED in A)')
        result = self.sync.pull(self.alice)
        assert result['status'] == 'merged'
        assert result['kept_dirty'] == ['y.txt']
        assert _read(self.alice, 'x.txt') == 'x v2 (from B)'
        assert _read(self.alice, 'y.txt') == 'y v2 (UNCOMMITTED in A)'
        assert _read(self.alice, 'docs/z.md') == 'z v2 (alice, committed)'

    def test_dirty_file_changed_by_the_other_side_is_refused_in_a_three_way_merge(self):
        self._diverge()
        _write(self.alice, 'x.txt', 'x (UNCOMMITTED in A)')
        with pytest.raises(Vault__Dirty_Working_Tree_Error, match='x.txt'):
            self.sync.pull(self.alice)
        assert _read(self.alice, 'x.txt') == 'x (UNCOMMITTED in A)'


class Test_Status__Ahead_Behind_After_Remote_Push(_TwoClones):

    def test_fresh_clone_one_behind_is_not_reported_as_everything_ahead(self):
        self._bob_pushes({'x.txt': 'x v2'})
        st = self.sync.status(self.alice)
        assert (st['ahead'], st['behind'], st['push_status']) == (0, 1, 'behind')

    def test_diverged_counts_are_exact(self):
        self._bob_pushes({'x.txt': 'x v2'})
        self._bob_pushes({'x.txt': 'x v3'})
        _write(self.alice, 'y.txt', 'y alice')
        self.sync.commit(self.alice, message='alice 1')
        st = self.sync.status(self.alice)
        assert (st['ahead'], st['behind'], st['push_status']) == (1, 2, 'diverged')


    def test_offline_status_still_counts_unpushed_commits_from_the_last_known_remote_head(self):
        from sgit_ai.core.Vault__Sync                     import Vault__Sync
        from sgit_ai.network.api.Vault__API__In_Memory    import Vault__API__In_Memory

        class _Ref_Only_API(Vault__API__In_Memory):         # the ref read works, object reads do not
            def batch_read(self, vault_id, file_ids, failures=None):
                raise RuntimeError('API Error: HTTP 503 Service Unavailable')

        self._bob_pushes({'x.txt': 'x v2'})
        _write(self.alice, 'y.txt', 'y alice')
        self.sync.commit(self.alice, message='alice 1')
        offline = _Ref_Only_API(); offline.setup(); offline._store = self.env.api._store
        st = Vault__Sync(crypto=self.env.crypto, api=offline).status(self.alice)
        assert (st['ahead'], st['behind'], st['push_status']) == (1, 1, 'diverged')
        assert st['behind_lower_bound'] is True

    def test_more_new_commits_than_the_fetch_limit_is_reported_as_a_lower_bound(self):
        for i in range(3):
            self._bob_pushes({'x.txt': f'x v{i + 2}'})
        self.sync.commit_fetch_limit = 1
        st = self.sync.status(self.alice)
        assert (st['ahead'], st['push_status'], st['behind_lower_bound']) == (0, 'behind', True)
        assert 1 <= st['behind'] <= 3
        self.sync.commit_fetch_limit = 50
        st = self.sync.status(self.alice)
        assert (st['ahead'], st['behind'], st['push_status'], st['behind_lower_bound']) == (0, 3, 'behind', False)


class Test_Vault__Pull__Guard__Plan:

    def setup_method(self):
        self.guard = Vault__Pull__Guard()

    def test_plan_rules(self):
        ours   = {'a': {'blob_id': 'A1'}, 'b': {'blob_id': 'B1'}, 'c': {'blob_id': 'C1'}, 'd': {'blob_id': 'D1'}}
        merged = {'a': {'blob_id': 'A1'}, 'b': {'blob_id': 'B2'}, 'd': {'blob_id': 'D2'},
                  'n': {'blob_id': 'N1', 'content_hash': 'h-n'}}
        dirty  = {'a': 'modified', 'b': 'modified', 'c': 'deleted', 'd': 'deleted', 'n': 'untracked', 'u': 'untracked'}
        scan   = {'n': {'content_hash': 'h-other'}}
        plan   = self.guard.plan(dirty, ours, merged, scan)
        assert plan['carry_over'] == ['a', 'c']
        assert [p for p, _ in plan['blocked']] == ['b', 'd', 'n']

    def test_untracked_identical_is_not_blocked(self):
        merged = {'n': {'blob_id': 'N1', 'content_hash': 'same'}}
        scan   = {'n': {'content_hash': 'same'}}
        # identical content is proven from the decrypted blob, never from the entry's own claim
        plan   = self.guard.plan({'n': 'untracked'}, {}, merged, scan, blob_hash_fn=lambda blob_id: 'same')
        assert plan == {'carry_over': [], 'blocked': []}
        assert self.guard.plan({'n': 'untracked'}, {}, merged, scan)['blocked']

    def test_dirty_paths_matches_status_semantics(self):
        ours = {'a': {'blob_id': 'A', 'content_hash': 'ha', 'size': 2},
                'b': {'blob_id': 'B', 'content_hash': 'hb', 'size': 2},
                'gone': {'blob_id': 'G', 'content_hash': 'hg', 'size': 2}}
        scan = {'a': {'content_hash': 'ha', 'size': 2}, 'b': {'content_hash': 'xx', 'size': 2},
                'new': {'content_hash': 'hn', 'size': 1}}
        assert self.guard.dirty_paths('/x', ours, scan) == {'b': 'modified', 'gone': 'deleted', 'new': 'untracked'}

    def test_message_names_paths_and_remedy(self):
        msg = self.guard.message([('y.txt', 'your uncommitted edit would be overwritten')])
        assert 'y.txt' in msg and 'sgit commit' in msg and 'nothing was changed' in msg
