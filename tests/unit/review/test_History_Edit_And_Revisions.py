"""0.21.0: revision shorthand, history undo, log filters and --stat,
revert --as-commit, commit --amend. Two real clones over the in-memory API."""
import os
import pytest

from tests._helpers.vault_test_env                       import Vault__Test_Env
from sgit_ai.core.Vault__Errors                          import Vault__Revision_Error
from sgit_ai.core.actions.history.Vault__Log_Filter      import Vault__Log_Filter
from sgit_ai.objects.Vault__Inspector                    import Vault__Inspector


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
        self.env = self._env.restore(); self.sync = self.env.sync
        self.alice = self.env.alice_dir; self.bob = self.env.bob_dir

    def teardown_method(self):
        self.env.cleanup()

    def _commit(self, d, files, message):
        for rel, content in files.items(): _write(d, rel, content)
        return self.sync.commit(d, message=message)['commit_id']

    def _head(self, d):
        return self.sync.resolve_revision(d, 'HEAD')

    def _chain(self, d, limit=50):
        c = self.sync._init_components(d)
        return Vault__Inspector(crypto=self.env.crypto).inspect_commit_chain(d, read_key=c.read_key, limit=limit)


# --------------------------------------------------------- revisions

class Test_Revisions(_Base):

    def test_head_tilde_caret_reflog_tag_and_short_ids(self):
        c1 = self._commit(self.alice, {'a.txt': 'one'},   'one')
        c2 = self._commit(self.alice, {'a.txt': 'two'},   'two')
        c3 = self._commit(self.alice, {'a.txt': 'three'}, 'three')
        r  = lambda spec: self.sync.resolve_revision(self.alice, spec)
        assert r('HEAD') == c3 and r('@') == c3
        assert r('HEAD~') == c2 and r('HEAD~2') == c1 and r('HEAD^') == c2 and r('HEAD~1^') == c1
        assert r('@{0}') == c3 and r('@{1}') == c2 and r('HEAD@{2}') == c1
        assert r(c2[len('obj-cas-imm-'):]) == c2 and r(c2[len('obj-cas-imm-'):][:6]) == c2

    def test_tags_and_ranges_resolve_through_the_same_rules(self):
        c1 = self._commit(self.alice, {'a.txt': 'one'}, 'one'); self.sync.push(self.alice)
        self.sync.tag_create(self.alice, 'v1')
        self._commit(self.alice, {'a.txt': 'two'}, 'two')
        assert self.sync.resolve_revision(self.alice, 'v1') == c1
        assert self.sync.resolve_revision(self.alice, 'v1~1') != c1
        from sgit_ai.core.actions.diff.Vault__Diff import Vault__Diff
        diff = Vault__Diff(crypto=self.env.crypto)
        assert len(diff.commits_in_range(self.alice, 'HEAD~1', 'HEAD')) == 1
        assert diff.show_commit(self.alice, 'HEAD~1')[0]['commit_id'] == c1
        assert self.sync.reset(self.alice, 'HEAD~1')['commit_id'] == c1

    def test_bad_spellings_are_refused_by_name(self):
        self._commit(self.alice, {'a.txt': 'one'}, 'one')
        for bad in ('HEAD~50', '@{99}', 'nope', 'HEAD~x', 'HEAD^3'):
            with pytest.raises(Vault__Revision_Error):
                self.sync.resolve_revision(self.alice, bad)


# --------------------------------------------------------------- undo

class Test_Undo(_Base):

    def test_undo_a_local_commit_and_redo_it(self):
        c1 = self._commit(self.alice, {'a.txt': 'one'}, 'one')
        c2 = self._commit(self.alice, {'a.txt': 'two'}, 'two')
        r  = self.sync.undo(self.alice)
        assert r['from_commit'] == c2 and r['to_commit'] == c1 and _read(self.alice, 'a.txt') == 'one'
        self.sync.undo(self.alice)                                       # undo the undo
        assert self._head(self.alice) == c2 and _read(self.alice, 'a.txt') == 'two'

    def test_undo_refuses_a_dirty_working_copy(self):
        self._commit(self.alice, {'a.txt': 'one'}, 'one')
        _write(self.alice, 'a.txt', 'uncommitted')
        with pytest.raises(Vault__Revision_Error, match='clean working copy'):
            self.sync.undo(self.alice)
        assert _read(self.alice, 'a.txt') == 'uncommitted'

    def test_undo_refuses_a_pushed_head_unless_forced(self):
        self._commit(self.alice, {'a.txt': 'one'}, 'one'); self.sync.push(self.alice)
        with pytest.raises(Vault__Revision_Error, match='already on the server'):
            self.sync.undo(self.alice)
        self.sync.undo(self.alice, force=True)


# ---------------------------------------------------- log filters / stat

class Test_Log_Filters_And_Stat(_Base):

    def test_grep_since_until_and_author(self):
        self._commit(self.alice, {'a.txt': 'one'}, 'fix: first')
        self._commit(self.alice, {'b.txt': 'b'},   'feature: second')
        chain = self._chain(self.alice)
        f = lambda **kw: [c['message'] for c in chain if Vault__Log_Filter().setup(**kw).matches(c)]
        assert f(grep='^FIX') == ['fix: first']
        assert len(f(since='1h')) >= 2 and f(until='2000-01-01') == []
        key = chain[0]['author_key_id']
        assert key and f(author=key[-6:].upper())[:2] == ['feature: second', 'fix: first']
        assert f(author='nobody-like-this') == []

    def test_stat_lists_added_modified_deleted_and_renamed(self):
        self._commit(self.alice, {'docs/x.md': 'x', 'b.txt': 'b'}, 'add')
        os.rename(os.path.join(self.alice, 'docs/x.md'), os.path.join(self.alice, 'docs/y.md'))
        os.remove(os.path.join(self.alice, 'b.txt'))
        _write(self.alice, 'a.txt', 'changed'); _write(self.alice, 'new.txt', 'n')
        self.sync.commit(self.alice, message='mixed')
        stat = self._chain(self.alice)[0]['stat']
        assert ('R', 'docs/y.md', 'docs/x.md') in stat and ('D', 'b.txt', '') in stat
        assert ('M', 'a.txt', '') in stat and ('A', 'new.txt', '') in stat

    def test_dates_parse(self):
        lf = Vault__Log_Filter()
        assert lf.parse_when('2026-10-08', 0) == 1791417600000
        assert lf.parse_when('3 days ago', 1791417600000) == 1791417600000 - 3 * 86400000
        with pytest.raises(Vault__Revision_Error):
            lf.parse_when('last tuesday-ish', 0)


# --------------------------------------------------- revert --as-commit

class Test_Revert_As_Commit(_Base):

    def test_reverts_an_earlier_commit_with_a_new_one_and_keeps_later_work(self):
        self._commit(self.alice, {'a.txt': 'one'}, 'one')
        bad = self._commit(self.alice, {'bad.txt': 'oops', 'a.txt': 'one'}, 'bad change')
        self._commit(self.alice, {'later.txt': 'keep'}, 'later')
        self.sync.push(self.alice)
        r = self.sync.revert_commit(self.alice, bad[len('obj-cas-imm-'):])
        assert not os.path.exists(os.path.join(self.alice, 'bad.txt')) and _read(self.alice, 'later.txt') == 'keep'
        assert r['reverted'] == bad and 'This reverts commit' in r['message']
        self.sync.push(self.alice); self.sync.pull(self.bob)
        assert not os.path.exists(os.path.join(self.bob, 'bad.txt')) and _read(self.bob, 'later.txt') == 'keep'

    def test_a_conflict_with_later_commits_refuses_and_changes_nothing(self):
        bad = self._commit(self.alice, {'a.txt': 'two'}, 'two')
        head = self._commit(self.alice, {'a.txt': 'three'}, 'three')
        with pytest.raises(Vault__Revision_Error, match='later commits also changed a.txt'):
            self.sync.revert_commit(self.alice, bad)
        assert self._head(self.alice) == head and _read(self.alice, 'a.txt') == 'three'

    def test_reverting_head_restores_the_previous_content(self):
        self._commit(self.alice, {'a.txt': 'one'}, 'one')
        self._commit(self.alice, {'a.txt': 'two'}, 'two')
        self.sync.revert_commit(self.alice, 'HEAD')
        assert _read(self.alice, 'a.txt') == 'one'


# ------------------------------------------------------------ amend

class Test_Amend(_Base):

    def test_amend_replaces_the_unpushed_head_with_same_parent(self):
        c1 = self._commit(self.alice, {'a.txt': 'one'}, 'one')
        c2 = self._commit(self.alice, {'a.txt': 'two'}, 'tow')
        _write(self.alice, 'b.txt', 'forgot')
        r  = self.sync.commit(self.alice, message='two', amend=True)
        assert r['commit_id'] != c2 and self.sync.resolve_revision(self.alice, 'HEAD~1') == c1
        assert self._chain(self.alice, 1)[0]['message'] == 'two'
        assert self.sync.resolve_revision(self.alice, '@{1}') == c2           # the old head is in the reflog

    def test_message_only_amend_keeps_the_tree(self):
        self._commit(self.alice, {'a.txt': 'one'}, 'tpyo')
        r = self.sync.commit(self.alice, message='typo', amend=True)
        assert self._chain(self.alice, 1)[0]['message'] == 'typo' and r['commit_id']

    def test_amend_refuses_a_pushed_head(self):
        self._commit(self.alice, {'a.txt': 'one'}, 'one'); self.sync.push(self.alice)
        with pytest.raises(Vault__Revision_Error, match='already on the server'):
            self.sync.commit(self.alice, message='rewrite', amend=True)

    def test_amend_with_nothing_new_is_refused(self):
        self._commit(self.alice, {'a.txt': 'one'}, 'one')
        with pytest.raises(Vault__Revision_Error, match='nothing to amend'):
            self.sync.commit(self.alice, amend=True)
