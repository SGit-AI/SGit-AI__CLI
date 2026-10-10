"""Branches end to end: create, list, switch in and out, work on a branch, push
to it, pull from it (including the main branch, `current`), merge either way,
conflicts, and the bookkeeping that must follow the branch (rewind baseline,
signing keys, status). Two real clones over the in-memory API; the env is
built once per class and restored per test."""
import json
import os
import pytest

from tests._helpers.vault_test_env                       import Vault__Test_Env
from sgit_ai.core.actions.branch.Vault__Branch_Switch    import Vault__Branch_Switch
from sgit_ai.schemas.Schema__Branch_Index                import Schema__Branch_Index


def _write(d, rel, content):
    full = os.path.join(d, rel); os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, 'w') as f: f.write(content)

def _read(d, rel):
    p = os.path.join(d, rel)
    return open(p).read() if os.path.exists(p) else None


class _Base:
    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env(); cls._env.setup_two_clones(files={'a.txt': 'main v1', 'shared.md': 'base'})

    @classmethod
    def teardown_class(cls):
        if cls._env: cls._env.cleanup_snapshot()

    def setup_method(self):
        self.env = self._env.restore(); self.sync = self.env.sync; self.api = self.env.api
        self.alice = self.env.alice_dir; self.bob = self.env.bob_dir
        self.c = self.sync._init_components(self.alice); self.vid = str(self.c.vault_id)
        self.branches = Vault__Branch_Switch(crypto=self.env.crypto)

    def teardown_method(self):
        self.env.cleanup()

    # helpers ---------------------------------------------------------------
    def _commit(self, d, files, message='m'):
        for rel, content in files.items(): _write(d, rel, content)
        return self.sync.commit(d, message=message)['commit_id']

    def _push(self, d, files, message='m'):
        self._commit(d, files, message); return self.sync.push(d)

    def _switch(self, d, name, force=False):
        return self.sync.switch_branch(d, name, force=force)     # what `sgit branch switch` runs

    def _server_index(self):
        raw = self.api._store[f'{self.vid}/bare/indexes/{self.c.branch_index_file_id}']
        return Schema__Branch_Index.from_json(json.loads(self.env.crypto.decrypt(self.c.read_key, raw)))

    def _server_head(self, name):
        meta = next((b for b in self._server_index().branches if str(b.name) == name), None)
        raw  = self.api._store.get(f'{self.vid}/bare/refs/{meta.head_ref_id}') if meta else None
        return json.loads(self.env.crypto.decrypt(self.c.read_key, raw))['commit_id'] if raw else None

    def _tracked(self, d):
        return next(b['name'] for b in self.branches.branch_list(d)['branches']
                    if b['branch_type'] == 'named' and b['branch_id'] ==
                    next(x['creator_branch'] for x in self.branches.branch_list(d)['branches'] if x['is_current']))


# --------------------------------------------------------------- create / list

class Test_Branch__Create_And_List(_Base):

    def test_new_branch_is_listed_and_current(self):
        r = self.branches.branch_new(self.alice, 'feature')
        listing = self.branches.branch_list(self.alice)['branches']
        named   = {b['name'] for b in listing if b['branch_type'] == 'named'}
        assert named == {'current', 'feature'}
        assert next(b for b in listing if b['is_current'])['branch_id'] == r['clone_branch_id']
        assert self._tracked(self.alice) == 'feature'

    def test_a_duplicate_name_is_refused(self):
        self.branches.branch_new(self.alice, 'feature')
        with pytest.raises(RuntimeError, match='already exists'):
            self.branches.branch_new(self.alice, 'feature')

    def test_new_branch_from_another_branch_checks_it_out(self):
        main_head = self._server_head('current')
        self.branches.branch_new(self.alice, 'feature')
        self._push(self.alice, {'f.txt': 'f'}, 'on feature')
        r = self.branches.branch_new(self.alice, 'hotfix', from_branch_id='current')
        assert self.sync.resolve_revision(self.alice, 'HEAD') == main_head and r['named_name'] == 'hotfix'
        assert _read(self.alice, 'f.txt') is None                # --from checks out its source
        assert self.sync.status(self.alice)['clean']

    def test_new_branch_carries_unpushed_commits_and_stays_clean(self):
        local = self._commit(self.alice, {'a.txt': 'unpushed'}, 'local')
        self.branches.branch_new(self.alice, 'feature')
        assert self.sync.resolve_revision(self.alice, 'HEAD') == local and self.sync.status(self.alice)['clean']


# ----------------------------------------------------------- push to a branch

class Test_Branch__Push_And_Pull(_Base):

    def test_push_on_a_branch_goes_to_that_branch_not_main(self):
        main_before = self._server_head('current')
        self.branches.branch_new(self.alice, 'feature')
        pushed = self._push(self.alice, {'f.txt': 'feature work'}, 'on feature')['commit_id']
        assert self._server_head('feature') == pushed
        assert self._server_head('current') == main_before        # 0.21.0 and older pushed it to main
        assert self.sync.pull(self.bob)['status'] == 'up_to_date' and _read(self.bob, 'f.txt') is None

    def test_a_teammate_switches_to_the_branch_and_gets_its_files(self):
        self.branches.branch_new(self.alice, 'feature')
        self._push(self.alice, {'f.txt': 'feature work'}, 'on feature')
        self._switch(self.bob, 'feature')
        assert _read(self.bob, 'f.txt') == 'feature work' and self._tracked(self.bob) == 'feature'

    def test_two_people_on_one_branch_push_and_pull(self):
        self.branches.branch_new(self.alice, 'feature')
        self._push(self.alice, {'f.txt': 'v1'}, 'alice 1')
        self._switch(self.bob, 'feature')
        self._push(self.bob, {'g.txt': 'bob'}, 'bob 1')
        self._push(self.alice, {'f.txt': 'v2'}, 'alice 2')          # push pulls bob's commit first
        assert _read(self.alice, 'g.txt') == 'bob'
        self.sync.pull(self.bob)
        assert _read(self.bob, 'f.txt') == 'v2'
        assert self._server_head('current') != self._server_head('feature')

    def test_status_compares_with_the_tracked_branch(self):
        self.branches.branch_new(self.alice, 'feature')
        self._push(self.alice, {'f.txt': 'v1'}, 'alice 1')
        self._push(self.bob, {'a.txt': 'main moved'}, 'main moves')    # main moves; alice is not behind feature
        self._commit(self.alice, {'f.txt': 'v2'}, 'local')
        st = self.sync.status(self.alice)
        assert st['ahead'] == 1 and st['behind'] == 0

    def test_teammates_verify_commits_made_on_a_new_branch(self):
        self.branches.branch_new(self.alice, 'feature')              # a new clone branch, a new signing key
        self._push(self.alice, {'f.txt': 'v1'}, 'signed on feature')
        self._switch(self.bob, 'feature')
        rep = self.sync.verify_signatures(self.bob)
        assert rep['counts']['no-key'] == 0 and rep['counts']['bad'] == 0


# ---------------------------------------------------------- switching in/out

class Test_Branch__Switching(_Base):

    def test_switching_back_and_forth_swaps_the_working_copy(self):
        self.branches.branch_new(self.alice, 'feature')
        self._push(self.alice, {'f.txt': 'feature', 'a.txt': 'feature a'}, 'feature')
        self._switch(self.alice, 'current')
        assert _read(self.alice, 'f.txt') is None and _read(self.alice, 'a.txt') == 'main v1'
        self._switch(self.alice, 'feature')
        assert _read(self.alice, 'f.txt') == 'feature' and _read(self.alice, 'a.txt') == 'feature a'

    def test_unpushed_commits_survive_switching_away_and_back(self):
        local = self._commit(self.alice, {'a.txt': 'unpushed on main'}, 'local only')
        self.branches.branch_new(self.alice, 'feature')
        self._switch(self.alice, 'current')
        assert self.sync.resolve_revision(self.alice, 'HEAD') == local
        assert _read(self.alice, 'a.txt') == 'unpushed on main'

    def test_a_dirty_working_copy_blocks_a_switch_unless_forced(self):
        self.branches.branch_new(self.alice, 'feature')
        self._switch(self.alice, 'current')
        _write(self.alice, 'a.txt', 'dirty')
        with pytest.raises(RuntimeError, match='uncommitted'):
            self.branches.switch(self.alice, 'feature')
        assert _read(self.alice, 'a.txt') == 'dirty'
        self.branches.switch(self.alice, 'feature', force=True)
        assert _read(self.alice, 'a.txt') == 'main v1'

    def test_no_false_rewind_when_branches_do_not_descend_from_each_other(self):
        self.branches.branch_new(self.alice, 'feature')
        self._push(self.alice, {'f.txt': 'feature'}, 'feature')
        self._switch(self.alice, 'current')
        self._push(self.alice, {'a.txt': 'main 2'}, 'main 2')        # main moves past the fork point
        self._switch(self.alice, 'feature')                          # feature does not descend from main's head
        assert self.sync.status(self.alice)['push_status'] != 'rewound'
        assert self.sync.pull(self.alice)['status'] in ('up_to_date', 'merged')

    def test_unknown_branch_is_refused(self):
        with pytest.raises(RuntimeError, match='Branch not found'):
            self.branches.switch(self.alice, 'nope')


# --------------------------------------------------------------- merging

class Test_Branch__Merge(_Base):

    def _feature_with(self, files):
        self.branches.branch_new(self.alice, 'feature')
        self._push(self.alice, files, 'feature work')
        self._switch(self.alice, 'current')

    def test_merge_a_branch_into_main_fast_forward_and_push(self):
        self._feature_with({'f.txt': 'feature'})
        r = self.sync.merge_branch(self.alice, 'feature')
        assert r['status'] == 'merged' and _read(self.alice, 'f.txt') == 'feature'
        self.sync.push(self.alice)
        assert self._server_head('current') == self._server_head('feature')
        self.sync.pull(self.bob)
        assert _read(self.bob, 'f.txt') == 'feature'

    def test_merge_with_divergence_makes_a_two_parent_commit(self):
        self._feature_with({'f.txt': 'feature'})
        self._push(self.alice, {'a.txt': 'main moved'}, 'main moved')
        self.sync.merge_branch(self.alice, 'feature')
        head = self.sync.resolve_revision(self.alice, 'HEAD')
        assert self.sync.resolve_revision(self.alice, 'HEAD^2') == self._server_head('feature') and head
        assert _read(self.alice, 'f.txt') == 'feature' and _read(self.alice, 'a.txt') == 'main moved'
        self.sync.push(self.alice); self.sync.pull(self.bob)
        assert _read(self.bob, 'f.txt') == 'feature' and _read(self.bob, 'a.txt') == 'main moved'

    def test_merge_main_into_a_branch_to_keep_it_current(self):
        self.branches.branch_new(self.alice, 'feature')
        self._push(self.alice, {'f.txt': 'feature'}, 'feature')
        self._push(self.bob, {'a.txt': 'main moved'}, 'main moved')
        self.sync.merge_branch(self.alice, 'current')
        self.sync.push(self.alice)
        assert _read(self.alice, 'a.txt') == 'main moved' and self._tracked(self.alice) == 'feature'
        assert self._server_head('feature') != self._server_head('current')

    def test_a_conflicting_merge_is_resolved_and_committed(self):
        self._feature_with({'shared.md': 'feature version'})
        self._push(self.alice, {'shared.md': 'main version'}, 'main edit')
        r = self.sync.merge_branch(self.alice, 'feature')
        assert r['status'] == 'conflicts' and 'shared.md' in r['conflicts']
        from sgit_ai.core.actions.merge.Vault__Merge__Resolve import Vault__Merge__Resolve
        Vault__Merge__Resolve().resolve_file(self.alice, 'shared.md', 'theirs')
        c = self.sync.commit(self.alice, message='merge feature')
        assert c['merge_commit'] is True and _read(self.alice, 'shared.md') == 'feature version'
        self.sync.push(self.alice)
        assert self._server_head('current') == c['commit_id']

    def test_merging_an_unknown_branch_is_refused(self):
        with pytest.raises(RuntimeError, match='Branch not found'):
            self.sync.merge_branch(self.alice, 'nope')

    def test_merging_twice_is_up_to_date(self):
        self._feature_with({'f.txt': 'feature'})
        self.sync.merge_branch(self.alice, 'feature')
        assert self.sync.merge_branch(self.alice, 'feature')['status'] == 'up_to_date'


class Test_Merge_Commits_Are_Signed(_Base):

    def test_a_pull_that_merges_signs_its_merge_commit(self):
        """The pull state carried the key id as a plain Safe_Str, which turns '-'
        into '_': the key was never found and every merge commit was unsigned, so
        `signatures-required` refused teammates' merges."""
        self._push(self.alice, {'a.txt': 'alice'}, 'alice')
        self._commit(self.bob, {'shared.md': 'bob'}, 'bob')
        assert self.sync.pull(self.bob)['status'] == 'merged'
        assert self.sync.verify_signatures(self.bob)['counts']['unsigned'] == 0

    def test_a_branch_merge_commit_is_signed(self):
        self.branches.branch_new(self.alice, 'feature')
        self._push(self.alice, {'f.txt': 'f'}, 'feature')
        self._switch(self.alice, 'current')
        self._push(self.alice, {'a.txt': 'main moved'}, 'main moved')
        self.sync.merge_branch(self.alice, 'feature')
        rep = self.sync.verify_signatures(self.alice)
        assert rep['counts']['unsigned'] == 0 and rep['counts']['bad'] == 0
