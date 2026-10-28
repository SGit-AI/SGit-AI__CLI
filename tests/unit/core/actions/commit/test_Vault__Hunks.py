"""Vault__Hunks — the hunks of `sgit commit --list-hunks / --hunk / -p` (design__03 §5.3).

Git is the oracle: on unique-line files the hunk headers are `git diff -U3`'s, and
committing any subset of hunks gives the bytes `git apply --cached` gives for the
same hunks cut out of git's own diff."""
import itertools
import random
import shutil
import subprocess

import pytest

from sgit_ai.core.actions.commit.Vault__Hunks     import Vault__Hunks
from sgit_ai.safe_types.Enum__Hunk_File_Status    import Enum__Hunk_File_Status
from sgit_ai.schemas.commit.Schema__File_Hunks    import Schema__File_Hunks

GIT = shutil.which('git')


def L(*lines) -> bytes:
    return b''.join(line.encode() + b'\n' for line in lines)


def numbered(n: int) -> list:
    return [f'line {i}' for i in range(1, n + 1)]


def edited(lines: list, at: dict) -> list:
    """at: {index: new text, or None to delete}."""
    out = []
    for i, line in enumerate(lines):
        if i in at:
            if at[i] is not None:
                out.append(at[i])
        else:
            out.append(line)
    return out


class Test_Vault__Hunks__Shape:

    def setup_method(self):
        self.hunks = Vault__Hunks()

    def of(self, base: bytes, work: bytes, split=False):
        return self.hunks.hunks_of('a.txt', base, work, 'aaaaaaaaaaaa', 'bbbbbbbbbbbb', split=split).hunks

    def test_one_edit_is_one_hunk_with_a_1_based_header(self):
        base = numbered(20)
        hunks = self.of(L(*base), L(*edited(base, {9: 'TEN'})))
        assert len(hunks) == 1
        assert str(hunks[0].header) == '@@ -7,7 +7,7 @@ line 6'
        assert (hunks[0].old_start, hunks[0].old_lines, hunks[0].added, hunks[0].removed) == (7, 7, 1, 1)

    def test_edits_far_apart_are_two_hunks(self):
        base = numbered(40)
        assert len(self.of(L(*base), L(*edited(base, {2: 'X', 30: 'Y'})))) == 2

    def test_edits_six_lines_apart_share_a_splittable_hunk_and_seven_do_not(self):
        base  = numbered(40)
        joint = self.of(L(*base), L(*edited(base, {10: 'X', 17: 'Y'})))          # 6 equal lines between
        apart = self.of(L(*base), L(*edited(base, {10: 'X', 18: 'Y'})))          # 7
        assert len(joint) == 1 and joint[0].splittable
        assert len(apart) == 2 and not apart[0].splittable
        parts = self.of(L(*base), L(*edited(base, {10: 'X', 17: 'Y'})), split=True)
        assert len(parts) == 2 and {str(p.hunk_id) for p in parts}.isdisjoint({str(joint[0].hunk_id)})

    def test_crlf_and_a_missing_final_newline_survive(self):
        base = b'a\r\nb\r\nc'
        work = b'a\r\nB\r\nc'
        hunk = self.of(base, work)[0]
        assert '-b\r\n+B\r\n c\n\\ No newline at end of file\n' in str(hunk.text)
        assert self.hunks.apply(base, work, [hunk], {str(hunk.hunk_id)}) == work

    def test_binary_and_too_large_are_whole_file(self):
        assert self.of(b'a\x00b', b'a\x00c')[0].whole_file
        small = Vault__Hunks(max_bytes=10)
        assert small.hunks_of('a', b'x\n' * 10, b'y\n' * 10).hunks[0].whole_file

    def test_new_and_deleted_files_are_one_whole_file_hunk(self):
        added   = self.hunks.hunks_of('n.txt', None, L('a', 'b'))
        deleted = self.hunks.hunks_of('d.txt', L('a'), None)
        assert added.status == Enum__Hunk_File_Status.ADDED and added.hunks[0].whole_file
        assert deleted.status == Enum__Hunk_File_Status.DELETED and deleted.hunks[0].whole_file
        assert str(added.hunks[0].text) == '+a\n+b\n'

    def test_an_empty_file_gaining_lines_is_an_ordinary_hunk(self):
        hunk = self.of(b'', L('a'))[0]
        assert not hunk.whole_file and str(hunk.header) == '@@ -0,0 +1 @@'

    def test_round_trip(self):
        result = self.hunks.hunks_of('a.txt', L(*numbered(20)), L(*edited(numbered(20), {3: 'x', 15: None})))
        assert Schema__File_Hunks.from_json(result.json()).json() == result.json()


class Test_Vault__Hunks__Ids:

    def setup_method(self):
        self.base = numbered(40)
        self.work = edited(self.base, {2: 'X', 30: 'Y'})

    def ids(self, base, work, path='a.txt', base_hash='aaaaaaaaaaaa'):
        return [str(h.hunk_id) for h in Vault__Hunks().hunks_of(path, L(*base), L(*work), base_hash).hunks]

    def test_stable_across_runs(self):
        assert self.ids(self.base, self.work) == self.ids(self.base, self.work)

    def test_an_edit_elsewhere_keeps_a_hunk_id(self):
        more = edited(self.work, {20: 'Z'})
        assert self.ids(self.base, self.work)[0] == self.ids(self.base, more)[0]

    def test_the_id_changes_with_the_hunk_the_base_or_the_path(self):
        first = self.ids(self.base, self.work)[0]
        assert self.ids(self.base, edited(self.base, {2: 'X2', 30: 'Y'}))[0] != first
        assert self.ids(self.base, self.work, base_hash='cccccccccccc')[0] != first
        assert self.ids(self.base, self.work, path='b.txt')[0] != first


class Test_Vault__Hunks__Apply:

    def test_all_is_work_and_none_is_base(self):
        base, work = L(*numbered(40)), L(*edited(numbered(40), {1: 'a', 12: None, 25: 'b', 39: 'c'}))
        hunks = list(Vault__Hunks().hunks_of('a', base, work).hunks)
        assert Vault__Hunks().apply(base, work, hunks, {str(h.hunk_id) for h in hunks}) == work
        assert Vault__Hunks().apply(base, work, hunks, set()) == base

    def test_hunks_and_split_parts_select_together(self):
        base, work = L(*numbered(40)), L(*edited(numbered(40), {10: 'X', 14: 'Y', 30: 'Z'}))
        hunker = Vault__Hunks()
        whole  = list(hunker.hunks_of('a', base, work).hunks)
        parts  = list(hunker.hunks_of('a', base, work, split=True).hunks)
        result = hunker.apply(base, work, whole + parts, {str(parts[1].hunk_id), str(whole[1].hunk_id)})
        assert result == L(*edited(numbered(40), {14: 'Y', 30: 'Z'}))


@pytest.mark.skipif(GIT is None, reason='git is the oracle')
class Test_Vault__Hunks__Git_Oracle:

    def git_diff(self, tmp_path, base: bytes, work: bytes) -> list:
        """git's hunks of base -> work, each as (header line, patch text)."""
        (tmp_path / 'a').write_bytes(base)
        (tmp_path / 'b').write_bytes(work)
        out = subprocess.run([GIT, 'diff', '--no-index', '-U3', 'a', 'b'], cwd=tmp_path,
                             capture_output=True).stdout.decode()
        body = out[out.index('\n@@') + 1:]
        hunks, current = [], None
        for line in body.splitlines(keepends=True):
            if line.startswith('@@'):
                current = [line]
                hunks.append(current)
            else:
                current.append(line)
        return [(h[0].rstrip('\n'), ''.join(h)) for h in hunks]

    def git_apply(self, tmp_path, base: bytes, patches: list) -> bytes:
        repo = tmp_path / 'repo'
        if repo.exists():
            shutil.rmtree(repo)
        repo.mkdir()
        (repo / 'f').write_bytes(base)
        git = [GIT, '-C', str(repo)]
        subprocess.run(git + ['init', '-q'], check=True)
        subprocess.run(git + ['add', 'f'], check=True)
        if patches:
            patch = '--- a/f\n+++ b/f\n' + ''.join(patches)
            subprocess.run(git + ['apply', '--cached', '--recount', '-'], input=patch.encode(), check=True)
        return subprocess.run(git + ['show', ':f'], capture_output=True, check=True).stdout

    def random_pair(self, seed: int) -> tuple:
        rng  = random.Random(seed)
        base = rng.sample([f'row {i}' for i in range(500)], 80)
        work = list(base)
        for _ in range(rng.randrange(1, 9)):
            k, op = rng.randrange(len(work)), rng.random()
            if op < 0.3:
                del work[k]
            elif op < 0.6:
                work.insert(k, f'new {rng.randrange(10 ** 6)}')
            else:
                work[k] = f'chg {rng.randrange(10 ** 6)}'
        return L(*base), L(*work)

    @pytest.mark.parametrize('seed', range(30))
    def test_headers_are_git_diffs(self, tmp_path, seed):
        base, work = self.random_pair(seed)
        ours = [str(h.header) for h in Vault__Hunks().hunks_of('a', base, work).hunks]
        assert ours == [header for header, _ in self.git_diff(tmp_path, base, work)]

    def test_every_subset_of_six_hunks_equals_git_apply(self, tmp_path):
        base_lines = numbered(90)
        base = L(*base_lines)
        work = L(*edited(base_lines, {2: 'A', 16: None, 30: 'C', 44: 'D', 58: None, 75: 'F'}))
        hunks = list(Vault__Hunks().hunks_of('f', base, work).hunks)
        git   = self.git_diff(tmp_path, base, work)
        assert len(hunks) == len(git) == 6
        for size in range(7):
            for subset in itertools.combinations(range(6), size):
                ours = Vault__Hunks().apply(base, work, hunks, {str(hunks[i].hunk_id) for i in subset})
                assert ours == self.git_apply(tmp_path, base, [git[i][1] for i in subset]), subset

    def test_crlf_and_no_final_newline_subsets_equal_git_apply(self, tmp_path):
        base = b''.join(f'l{i}\r\n'.encode() for i in range(30)) + b'end'
        work = base.replace(b'l3\r\n', b'L3\r\n').replace(b'l20\r\n', b'').replace(b'end', b'END')
        hunks = list(Vault__Hunks().hunks_of('f', base, work).hunks)
        git   = self.git_diff(tmp_path, base, work)
        assert len(hunks) == len(git)
        for size in range(len(hunks) + 1):
            for subset in itertools.combinations(range(len(hunks)), size):
                ours = Vault__Hunks().apply(base, work, hunks, {str(hunks[i].hunk_id) for i in subset})
                assert ours == self.git_apply(tmp_path, base, [git[i][1] for i in subset]), subset
