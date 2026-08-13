"""Tests for Vault__Diff.three_way_conflict_view (A4 — `resolve --show` 3-way).

Builds a real vault with three commits and feeds them as base/ours/theirs so the
classification logic is exercised against real encrypted trees (no mocks).
"""
import os
import shutil
import tempfile

from sgit_ai.core.Vault__Sync                     import Vault__Sync
from sgit_ai.core.actions.diff.Vault__Diff         import Vault__Diff
from sgit_ai.crypto.Vault__Crypto                  import Vault__Crypto
from sgit_ai.network.api.Vault__API__In_Memory     import Vault__API__In_Memory


class Test_Vault__Diff__Three_Way_Conflict_View:

    @classmethod
    def setup_class(cls):
        cls.crypto = Vault__Crypto()
        api        = Vault__API__In_Memory(); api.setup()
        cls.sync   = Vault__Sync(crypto=cls.crypto, api=api)
        cls.tmp    = tempfile.mkdtemp(prefix='three_way_')
        cls.vault  = os.path.join(cls.tmp, 'vault')
        cls.sync.init(cls.vault)

        def write(rel, content):
            with open(os.path.join(cls.vault, rel), 'w') as f:
                f.write(content)

        # base: conflict.txt='base', sentinel.txt='s0'
        write('conflict.txt', 'base\n'); write('sentinel.txt', 's0')
        cls.base = cls.sync.commit(cls.vault, message='base')['commit_id']
        # ours: change ONLY sentinel.txt (conflict.txt unchanged vs base)
        write('sentinel.txt', 's1')
        cls.ours_unchanged = cls.sync.commit(cls.vault, message='ours-untouched-conflict')['commit_id']
        # theirs: change ONLY conflict.txt
        write('conflict.txt', 'theirs\n')
        cls.theirs = cls.sync.commit(cls.vault, message='theirs-changed-conflict')['commit_id']
        # ours2: change conflict.txt to a DIFFERENT value than theirs
        write('conflict.txt', 'ours\n')
        cls.ours_changed = cls.sync.commit(cls.vault, message='ours-changed-conflict')['commit_id']

    @classmethod
    def teardown_class(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _view(self, base, ours, theirs, paths):
        return Vault__Diff(crypto=self.crypto).three_way_conflict_view(
            self.vault, base, ours, theirs, paths)

    def test_genuine_when_both_sides_changed_differently(self):
        rows = self._view(self.base, self.ours_changed, self.theirs, ['conflict.txt'])
        assert len(rows) == 1
        r = rows[0]
        assert r['verdict']        == 'genuine'
        assert r['ours_changed']   is True
        assert r['theirs_changed'] is True
        assert r['ours_text']      == 'ours\n'
        assert r['theirs_text']    == 'theirs\n'

    def test_one_sided_theirs_when_only_theirs_changed(self):
        # ours_unchanged left conflict.txt == base; theirs changed it
        rows = self._view(self.base, self.ours_unchanged, self.theirs, ['conflict.txt'])
        r = rows[0]
        assert r['verdict']        == 'one-sided-theirs'
        assert r['ours_changed']   is False
        assert r['theirs_changed'] is True

    def test_one_sided_ours_when_only_ours_changed(self):
        # symmetric: ours changed conflict.txt, "theirs" left it at base
        rows = self._view(self.base, self.ours_changed, self.ours_unchanged, ['conflict.txt'])
        r = rows[0]
        assert r['verdict']        == 'one-sided-ours'
        assert r['ours_changed']   is True
        assert r['theirs_changed'] is False

    def test_identical_when_both_made_same_change(self):
        rows = self._view(self.base, self.theirs, self.theirs, ['conflict.txt'])
        assert rows[0]['verdict'] == 'identical'

    def test_genuine_count_is_only_real_conflicts(self):
        rows = self._view(self.base, self.ours_changed, self.theirs, ['conflict.txt'])
        genuine = [r for r in rows if r['verdict'] == 'genuine']
        assert len(genuine) == 1
