"""Unit tests for Vault__Diff.commits_in_range — Brief 13."""
import os
import shutil
import tempfile

import pytest

from sgit_ai.crypto.Vault__Crypto               import Vault__Crypto
from sgit_ai.core.actions.diff.Vault__Diff       import Vault__Diff


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_vault(files: dict) -> tuple:
    """Create a real vault with initial files committed. Returns (tmp_dir, sync, commit_id)."""
    from sgit_ai.core.Vault__Sync            import Vault__Sync
    from sgit_ai.network.api.Vault__API__In_Memory import Vault__API__In_Memory

    crypto = Vault__Crypto()
    api    = Vault__API__In_Memory()
    api.setup()
    sync   = Vault__Sync(crypto=crypto, api=api)
    tmp    = tempfile.mkdtemp()
    sync.init(tmp)

    for rel, content in files.items():
        full   = os.path.join(tmp, rel)
        parent = os.path.dirname(full)
        if parent != tmp:
            os.makedirs(parent, exist_ok=True)
        mode = 'wb' if isinstance(content, bytes) else 'w'
        with open(full, mode) as f:
            f.write(content)

    r = sync.commit(tmp, message='commit A')
    return tmp, sync, r['commit_id']


def _add_commit(sync, tmp, files: dict, message: str) -> str:
    for rel, content in files.items():
        full   = os.path.join(tmp, rel)
        parent = os.path.dirname(full)
        if parent != tmp:
            os.makedirs(parent, exist_ok=True)
        mode = 'wb' if isinstance(content, bytes) else 'w'
        with open(full, mode) as f:
            f.write(content)
    r = sync.commit(tmp, message=message)
    return r['commit_id']


# ---------------------------------------------------------------------------
# Tests for commits_in_range
# ---------------------------------------------------------------------------

class Test_Vault__Diff__Range:

    def setup_method(self):
        self.diff = Vault__Diff(crypto=Vault__Crypto())

    def _build_five_commit_vault(self):
        """Returns (tmp, sync, [A, B, C, D, E]) oldest-first."""
        tmp, sync, commit_a = _make_vault({'a.txt': 'A'})
        commit_b = _add_commit(sync, tmp, {'b.txt': 'B'}, 'commit B')
        commit_c = _add_commit(sync, tmp, {'c.txt': 'C'}, 'commit C')
        commit_d = _add_commit(sync, tmp, {'d.txt': 'D'}, 'commit D')
        commit_e = _add_commit(sync, tmp, {'e.txt': 'E'}, 'commit E')
        return tmp, sync, [commit_a, commit_b, commit_c, commit_d, commit_e]

    def test_commits_in_range_walks_oldest_first(self):
        tmp, sync, commits = self._build_five_commit_vault()
        try:
            A, B, C, D, E = commits
            result = self.diff.commits_in_range(tmp, from_commit=B, to_commit=E)
            assert result == [C, D, E]
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_commits_in_range_inclusive_to(self):
        tmp, sync, commits = self._build_five_commit_vault()
        try:
            A, B, C, D, E = commits
            result = self.diff.commits_in_range(tmp, from_commit=C, to_commit=E)
            assert E in result
            assert result[-1] == E
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_commits_in_range_exclusive_from(self):
        tmp, sync, commits = self._build_five_commit_vault()
        try:
            A, B, C, D, E = commits
            result = self.diff.commits_in_range(tmp, from_commit=B, to_commit=E)
            assert B not in result
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_commits_in_range_open_ended_to_walks_to_head(self):
        tmp, sync, commits = self._build_five_commit_vault()
        try:
            A, B, C, D, E = commits
            # to_commit='' → defaults to HEAD (E)
            result = self.diff.commits_in_range(tmp, from_commit=C, to_commit='')
            assert result == [D, E]
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_commits_in_range_open_ended_from_walks_to_root(self):
        tmp, sync, commits = self._build_five_commit_vault()
        try:
            A, B, C, D, E = commits
            # from_commit='' → walk to root (includes any init commit before A)
            result = self.diff.commits_in_range(tmp, from_commit='', to_commit=C)
            # A, B, C must all appear and be in that order (oldest first)
            assert A in result
            assert B in result
            assert C in result
            assert result.index(A) < result.index(B) < result.index(C)
            assert D not in result
            assert E not in result
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_commits_in_range_from_not_ancestor_raises(self):
        tmp, sync, commits = self._build_five_commit_vault()
        try:
            A, B, C, D, E = commits
            with pytest.raises(RuntimeError, match='not an ancestor'):
                self.diff.commits_in_range(tmp, from_commit=E, to_commit=C)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_commits_in_range_full_history_when_no_range(self):
        tmp, sync, commits = self._build_five_commit_vault()
        try:
            A, B, C, D, E = commits
            result = self.diff.commits_in_range(tmp, from_commit='', to_commit='')
            # All five commits must appear in oldest-first order
            for cid in [A, B, C, D, E]:
                assert cid in result
            assert result.index(A) < result.index(B) < result.index(C) < result.index(D) < result.index(E)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
