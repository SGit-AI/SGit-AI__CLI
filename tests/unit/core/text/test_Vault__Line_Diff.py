"""The shared line differ (phase 0: design__00 F1).

Checked against a reference: on random inputs the unchanged lines are a longest
common subsequence (its length equals a dynamic-programming LCS), the hunks take
a to b exactly, and the difflib-shaped helpers cover both sequences."""
import random
import subprocess

import pytest

from sgit_ai.core.Vault__Errors                import Vault__Line_Diff__Too_Different
from sgit_ai.core.text.Vault__Line_Diff        import Vault__Line_Diff
from sgit_ai.core.text.Vault__Line_Splitter    import Vault__Line_Splitter
from sgit_ai.schemas.Schema__Line_Hunk         import Schema__Line_Hunk


def lcs_length(a: list, b: list) -> int:
    prev = [0] * (len(b) + 1)
    for x in a:
        cur = [0]
        for j, y in enumerate(b):
            cur.append(prev[j] + 1 if x == y else max(prev[j + 1], cur[j]))
        prev = cur
    return prev[-1]


def apply_hunks(a: list, b: list, hunks: list) -> list:
    out, i = [], 0
    for a_lo, a_hi, b_lo, b_hi in hunks:
        out.extend(a[i:a_lo])
        out.extend(b[b_lo:b_hi])
        i = a_hi
    out.extend(a[i:])
    return out


class Test_Vault__Line_Diff:

    def setup_method(self):
        self.diff = Vault__Line_Diff()
        self.rng  = random.Random(20261028)

    def test_identical_and_empty(self):
        assert self.diff.hunks([1, 2, 3], [1, 2, 3]) == []
        assert self.diff.hunks([], [])               == []
        assert self.diff.hunks([], [1, 2])           == [(0, 0, 0, 2)]
        assert self.diff.hunks([1, 2], [])           == [(0, 2, 0, 0)]

    def test_insert_delete_replace(self):
        assert self.diff.hunks([1, 2, 3], [1, 9, 2, 3]) == [(1, 1, 1, 2)]
        assert self.diff.hunks([1, 2, 3], [1, 3])       == [(1, 2, 1, 1)]
        assert self.diff.hunks([1, 2, 3], [1, 7, 3])    == [(1, 2, 1, 2)]

    def test_nothing_in_common(self):
        assert self.diff.hunks([1, 2, 3], [4, 5]) == [(0, 3, 0, 2)]

    @pytest.mark.parametrize('seed', range(60))
    def test_random_inputs_are_minimal_and_exact(self, seed):
        rng = random.Random(seed)
        alphabet = rng.choice([3, 5, 12])                        # small alphabets: many repeated lines
        a = [rng.randrange(alphabet) for _ in range(rng.randrange(0, 80))]
        b = list(a)
        for _ in range(rng.randrange(0, 25)):                    # edit a copy, so a and b are related
            op = rng.random()
            if op < 0.4 and b:
                del b[rng.randrange(len(b))]
            elif op < 0.8:
                b.insert(rng.randrange(len(b) + 1), rng.randrange(alphabet))
            elif b:
                b[rng.randrange(len(b))] = rng.randrange(alphabet)
        changed_a, changed_b = self.diff.mark_changes(a, b)
        kept_a = [x for x, c in zip(a, changed_a) if not c]
        kept_b = [x for x, c in zip(b, changed_b) if not c]
        assert kept_a == kept_b                                  # the unchanged lines are common, in order
        assert len(kept_a) == lcs_length(a, b)                   # and as many as possible
        assert apply_hunks(a, b, self.diff.hunks(a, b)) == b

    def test_unrelated_random_inputs(self):
        a = [self.rng.randrange(1000) for _ in range(300)]
        b = [self.rng.randrange(1000) for _ in range(300)]
        changed_a, changed_b = self.diff.mark_changes(a, b)
        kept = [x for x, c in zip(a, changed_a) if not c]
        assert len(kept) == lcs_length(a, b)

    def test_cost_cap_raises(self):
        small = Vault__Line_Diff(max_edit_cost=10)
        with pytest.raises(Vault__Line_Diff__Too_Different):
            small.hunks(list(range(50)), list(range(100, 150)))
        assert small.hunks(list(range(50)), list(range(50)) + [99]) == [(50, 50, 50, 51)]

    def test_large_mostly_equal_files_are_fast(self):
        a = list(range(200_000))
        b = list(a)
        b[1000] = -1
        b.insert(150_000, -2)
        assert self.diff.hunks(a, b) == [(1000, 1001, 1000, 1001), (150_000, 150_000, 150_000, 150_001)]

    def test_diff_returns_schema_hunks(self):
        hunks = self.diff.diff([1, 2, 3], [1, 9, 3])
        assert len(hunks) == 1 and isinstance(hunks[0], Schema__Line_Hunk)
        assert (hunks[0].base_start, hunks[0].base_end, hunks[0].side_start, hunks[0].side_end) == (1, 2, 1, 2)

    def test_opcodes_cover_both_sequences(self):
        a, b = [1, 2, 3, 4, 5], [0, 1, 3, 4, 9]
        ops  = self.diff.opcodes(a, b)
        assert ops[0][1] == 0 and ops[0][3] == 0 and ops[-1][2] == len(a) and ops[-1][4] == len(b)
        for (_, _, i2, _, j2), (_, i1, _, j1, _) in zip(ops, ops[1:]):
            assert (i2, j2) == (i1, j1)
        for tag, i1, i2, j1, j2 in ops:
            if tag == 'equal':
                assert a[i1:i2] == b[j1:j2]

    def test_matching_blocks_sum_to_the_lcs(self):
        for _ in range(50):
            a = [self.rng.randrange(6) for _ in range(self.rng.randrange(40))]
            b = [self.rng.randrange(6) for _ in range(self.rng.randrange(40))]
            blocks = self.diff.matching_blocks(a, b)
            assert blocks[-1] == (len(a), len(b), 0)
            assert sum(size for _, _, size in blocks) == lcs_length(a, b)


class Test_Vault__Line_Splitter:

    def setup_method(self):
        self.splitter = Vault__Line_Splitter()

    def test_lines_keep_their_endings_and_only_newline_splits(self):
        assert self.splitter.split(b'a\nb\r\nc') == [b'a\n', b'b\r\n', b'c']
        assert self.splitter.split(b'a\x0bb\x0cc\n') == [b'a\x0bb\x0cc\n']
        assert self.splitter.split(b'') == []
        assert self.splitter.split(b'x\n') == [b'x\n']
        assert b''.join(self.splitter.split(b'one\ntwo\n\nthree')) == b'one\ntwo\n\nthree'

    def test_binary_is_a_nul_in_the_first_8000_bytes(self):
        assert self.splitter.is_binary(b'abc\x00def')
        assert not self.splitter.is_binary(b'a' * 8000 + b'\x00')

    def test_intern_shares_one_table(self):
        a, b = self.splitter.intern([b'x\n', b'y\n'], [b'y\n', b'z\n'])
        assert a[1] == b[0] and a[0] != b[1]

    def test_ignore_whitespace(self):
        ws   = Vault__Line_Splitter(ignore_whitespace=True)
        a, b = ws.intern([b'if  x:\n'], [b'if x :\r\n'])
        assert a == b


class Test_Vault__Line_Diff__Git_Oracle:
    """The number of changed lines matches `git diff --no-index` on the same files
    (both minimal; hunk placement in ambiguous runs may differ)."""

    def test_changed_line_counts_match_git(self, tmp_path):
        rng = random.Random(7)
        for case in range(10):
            a = [f'line {rng.randrange(8)}\n'.encode() for _ in range(60)]
            b = list(a)
            for _ in range(10):
                k = rng.randrange(len(b))
                b[k:k + 1] = [f'new {rng.randrange(8)}\n'.encode()] * rng.randrange(0, 3)
            (tmp_path / 'a').write_bytes(b''.join(a))
            (tmp_path / 'b').write_bytes(b''.join(b))
            out = subprocess.run(['git', 'diff', '--no-index', '--numstat', '--diff-algorithm=myers',
                                  str(tmp_path / 'a'), str(tmp_path / 'b')], capture_output=True, text=True).stdout
            if not out.strip():
                assert a == b
                continue
            added, deleted = (int(x) for x in out.split()[:2])
            ids_a, ids_b = Vault__Line_Splitter().intern(a, b)
            changed_a, changed_b = Vault__Line_Diff().mark_changes(ids_a, ids_b)
            assert (changed_b.count(True), changed_a.count(True)) == (added, deleted)
