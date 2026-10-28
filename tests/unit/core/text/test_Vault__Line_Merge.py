"""The three-way line merge (design__01 §5.4), checked against `git merge-file`.

Git is the oracle: every vector from design__01 §1.2 and random inputs must come out
byte-identical (content and conflict count = git's exit code), in both conflict
styles. Since the differ is a port of xdiff's (cli.build BR-2, BR-3), that holds for
repeated lines too: code-like lines (`}`, blank lines) and a three-letter alphabet,
the generators of cli.build's fuzz_line_merge.py, with CRLF and missing final newlines."""
import random
import shutil
import subprocess

import pytest

from sgit_ai.core.text.Vault__Line_Merge          import Vault__Line_Merge, MAX_MERGE_BYTES
from sgit_ai.safe_types.Enum__Conflict_Style      import Enum__Conflict_Style
from sgit_ai.safe_types.Enum__Line_Merge_Outcome  import Enum__Line_Merge_Outcome
from sgit_ai.schemas.Schema__Conflict_Labels      import Schema__Conflict_Labels

GIT = shutil.which('git')


def L(*lines) -> bytes:
    return b''.join(line.encode() + b'\n' for line in lines)


VECTORS = {
    'G1  ours b, theirs b and e'       : (L('a', 'b', 'c', 'd', 'e'), L('a', 'B1', 'c', 'd', 'e'), L('a', 'B2', 'c', 'd', 'E')),
    'G3  the identical change'         : (L('a', 'b', 'c'), L('a', 'X', 'c'), L('a', 'X', 'c')),
    'G4  adjacent changes conflict'    : (L('a', 'b', 'c', 'd'), L('a', 'X', 'c', 'd'), L('a', 'b', 'Y', 'd')),
    'G5  one line apart: clean'        : (L('a', 'b', 'c', 'd', 'e'), L('a', 'X', 'c', 'd', 'e'), L('a', 'b', 'c', 'Y', 'e')),
    'G6  both insert, differently'     : (L('a', 'b'), L('a', 'X', 'b'), L('a', 'Y', 'b')),
    'G7  both insert the same'         : (L('a', 'b'), L('a', 'X', 'b'), L('a', 'X', 'b')),
    'G8  partial overlap (refined)'    : (L('a', 'b', 'c', 'd'), L('a', 'X', 'Y', 'd'), L('a', 'X', 'Z', 'd')),
    'G10 three lines apart: joined'    : (L('a', 'b', 'c', 'd', 'e', 'f', 'g'), L('a', 'X', 'c', 'd', 'e', 'Y', 'g'),
                                          L('a', 'P', 'c', 'd', 'e', 'Q', 'g')),
    'G11 four lines apart: two'        : (L('a', 'b', 'c', 'd', 'e', 'f', 'g', 'h'), L('a', 'X', 'c', 'd', 'e', 'f', 'Y', 'h'),
                                          L('a', 'P', 'c', 'd', 'e', 'f', 'Q', 'h')),
    'G12 apart by braces only: joined' : (L('a', 'b', '}', '}', '}', '}', 'g'), L('a', 'X', '}', '}', '}', '}', 'Y'),
                                          L('a', 'P', '}', '}', '}', '}', 'Q')),
    'G13 CRLF markers'                 : (b'a\r\nb\r\nc\r\n', b'a\r\nX\r\nc\r\n', b'a\r\nY\r\nc\r\n'),
    'G14 no final newline, conflict'   : (b'a\nb', b'a\nX', b'a\nY'),
    'G15 theirs drops the newline'     : (b'a\nb\n', b'a\nb\n', b'a\nb'),
    'G16 add/add'                      : (b'', L('a', 'x', 'c'), L('a', 'y', 'c')),
}


@pytest.mark.skipif(GIT is None, reason='git is the oracle')
class Test_Vault__Line_Merge__Git_Oracle:

    def git_merge_file(self, tmp_path, base: bytes, ours: bytes, theirs: bytes, diff3: bool) -> tuple:
        for name, data in (('base', base), ('ours', ours), ('theirs', theirs)):
            (tmp_path / name).write_bytes(data)
        args = [GIT, 'merge-file', '-p'] + (['--diff3'] if diff3 else []) + \
               ['-L', 'ours', '-L', 'base', '-L', 'theirs', str(tmp_path / 'ours'), str(tmp_path / 'base'), str(tmp_path / 'theirs')]
        result = subprocess.run(args, capture_output=True)
        return result.stdout, result.returncode

    def ours(self, base: bytes, ours: bytes, theirs: bytes, diff3: bool) -> tuple:
        content, result = Vault__Line_Merge().merge(base, ours, theirs,
                                                    conflict_style=Enum__Conflict_Style.DIFF3 if diff3 else Enum__Conflict_Style.MERGE)
        return content, int(result.hunks)

    @pytest.mark.parametrize('diff3', [False, True])
    @pytest.mark.parametrize('name', sorted(VECTORS))
    def test_vectors_are_byte_identical_to_git(self, tmp_path, name, diff3):
        base, ours, theirs = VECTORS[name]
        assert self.ours(base, ours, theirs, diff3) == self.git_merge_file(tmp_path, base, ours, theirs, diff3)

    @pytest.mark.parametrize('seed', range(40))
    def test_random_unique_lines_are_byte_identical_to_git(self, tmp_path, seed):
        rng  = random.Random(seed)
        base = rng.sample([f'line {i}' for i in range(300)], 40)

        def edit(lines):
            lines = list(lines)
            for _ in range(rng.randrange(1, 7)):
                k, op = rng.randrange(len(lines) + 1), rng.random()
                if op < 0.3 and k < len(lines):
                    del lines[k]
                elif op < 0.6:
                    lines.insert(k, f'new {rng.randrange(10 ** 9)}')
                elif k < len(lines):
                    lines[k] = f'new {rng.randrange(10 ** 9)}'
            return lines

        b, o, t = L(*base), L(*edit(base)), L(*edit(base))
        for diff3 in (False, True):
            assert self.ours(b, o, t, diff3) == self.git_merge_file(tmp_path, b, o, t, diff3)


@pytest.mark.skipif(GIT is None, reason='git is the oracle')
class Test_Vault__Line_Merge__Git_Oracle__Repeated_Lines(Test_Vault__Line_Merge__Git_Oracle):
    """cli.build BR-2: a clean merge where Git reports a conflict, when lines repeat. The
    generators are those of cli.build's fuzzer; before the xdiff port, 2 in 4,544 code-like
    and 23 in 4,500 three-letter merges merged silently where Git asks."""

    CODE = ['}', '', '{', '    return x;', '    i++;', 'end', '#', '  ', 'else', '    }', 'if (a) {', 'x = 1;']

    def lines(self, rng, kind: str, n: int) -> list:
        if kind == 'code':
            return [rng.choice(self.CODE) if rng.random() < .6 else f'line {rng.randrange(10 ** 6)}' for _ in range(n)]
        return [rng.choice('abc') for _ in range(n)]

    def edit(self, rng, lines: list, kind: str) -> list:
        out = list(lines)
        for _ in range(rng.randint(0, 4)):
            op, i = rng.random(), rng.randint(0, len(out))
            new   = self.lines(rng, kind, rng.randint(1, 3))
            if op < .35 and out:
                del out[i:i + rng.randint(1, 3)]
            elif op < .7:
                out[i:i] = new
            elif out:
                out[i:i + rng.randint(1, 2)] = new
        return out

    def render(self, lines: list, crlf: bool, final_newline: bool) -> bytes:
        eol  = '\r\n' if crlf else '\n'
        text = eol.join(lines)
        return (text + eol if lines and final_newline else text).encode()

    @pytest.mark.parametrize('kind', ['code', 'tiny'])
    @pytest.mark.parametrize('seed', range(8))
    def test_repeated_lines_are_byte_identical_to_git(self, tmp_path, kind, seed):
        rng = random.Random(f'{kind}-{seed}')
        for _ in range(40):
            base  = self.lines(rng, kind, rng.randint(0, 25))
            crlf  = rng.random() < .15
            b, o, t = (self.render(x, crlf, rng.random() > .2)
                       for x in (base, self.edit(rng, base, kind), self.edit(rng, base, kind)))
            for diff3 in (False, True):
                assert self.ours(b, o, t, diff3) == self.git_merge_file(tmp_path, b, o, t, diff3)

    def test_cli_builds_br_2_case(self, tmp_path):
        """The code-like case from cli.build's review of 0.26.5 (seed 4, diff3): git conflicts."""
        base   = L('line 34408', '{', 'end', 'if (a) {', 'line 34409')
        ours   = L('line 34413', 'line 34412', '{', 'end', 'if (a) {', 'line 34408', '{', 'end', 'line 34409',
                   'line 34414', 'if (a) {')
        theirs = L('line 34408', '{', 'end', 'if (a) {')
        for diff3 in (False, True):
            assert self.ours(base, ours, theirs, diff3) == self.git_merge_file(tmp_path, base, ours, theirs, diff3)


class Test_Vault__Line_Merge:

    def setup_method(self):
        self.merge = Vault__Line_Merge()

    def test_one_side_unchanged_is_the_other_side(self):
        base = L('a', 'b')
        assert self.merge.merge(base, base, L('a', 'c'))[0] == L('a', 'c')
        assert self.merge.merge(base, L('a', 'd'), base)[0] == L('a', 'd')

    def test_clean_merge_has_both_changes(self):
        content, result = self.merge.merge(L('a', 'b', 'c', 'd', 'e'), L('A', 'b', 'c', 'd', 'e'), L('a', 'b', 'c', 'd', 'E'))
        assert result.outcome == Enum__Line_Merge_Outcome.CLEAN and result.hunks == 0
        assert content == L('A', 'b', 'c', 'd', 'E')

    def test_binary_is_never_merged(self):
        content, result = self.merge.merge(b'a\x00', b'b\x00', b'c\x00')
        assert (content, result.outcome) == (b'', Enum__Line_Merge_Outcome.BINARY)

    def test_too_large_is_never_merged(self):
        big = b'x\n' * (MAX_MERGE_BYTES // 2 + 1)
        assert self.merge.merge(big, big + b'y\n', big + b'z\n')[1].outcome == Enum__Line_Merge_Outcome.TOO_LARGE

    def test_labels_cannot_inject_a_line(self):
        labels = Schema__Conflict_Labels(ours='mine\n=======\n', theirs='x\r\n>>>>>>> y')
        content, _ = self.merge.merge(L('a'), L('b'), L('c'), labels=labels)
        lines = content.split(b'\n')
        assert lines[0] == b'<<<<<<< mine_======='                     # trimmed, then each control character replaced
        assert lines.count(b'=======') == 1
        assert lines[-2].startswith(b'>>>>>>> x__>>>>>>> y')

    @pytest.mark.parametrize('seed', range(30))
    def test_repeated_lines_keep_the_merge_invariants(self, seed):
        """Where only one side changed a region, the result has that side's lines; and
        resolving every conflict to ours or theirs reproduces a consistent file."""
        rng  = random.Random(seed)
        base = [f'l{rng.randrange(4)}' for _ in range(25)]
        ours = list(base)
        ours[rng.randrange(len(ours))] = 'OURS'
        content, result = self.merge.merge(L(*base), L(*ours), L(*base))
        assert content == L(*ours) and result.outcome == Enum__Line_Merge_Outcome.CLEAN
        theirs = list(base) + ['TAIL']
        content, result = self.merge.merge(L(*base), L(*ours), L(*theirs))
        assert b'OURS\n' in content and content.endswith(b'TAIL\n')
