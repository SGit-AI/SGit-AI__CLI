"""Vault__Renames — Git's rename detection, with git as the oracle: the same R pairs and
the same scores as `git diff -M --name-status` (design__04 §5.2, 9.1)."""
import hashlib
import random
import shutil
import subprocess

import pytest

from sgit_ai.core.actions.diff.Vault__Renames import Vault__Renames

GIT = shutil.which('git')


def entry(data: bytes) -> dict:
    return dict(blob_id=f'obj-{hashlib.sha256(data).hexdigest()[:12]}', size=len(data),
                content_hash=hashlib.sha256(data).hexdigest()[:12])


def text(seed: int, n: int) -> bytes:
    rng = random.Random(seed)
    return b''.join(f'{rng.randrange(10 ** 9)} line {i}\n'.encode() for i in range(n))


class Renames__Oracle:

    def detect(self, before: dict, after: dict, **kw) -> dict:
        deleted = {p: entry(d) for p, d in before.items() if p not in after}
        added   = {p: entry(d) for p, d in after.items() if p not in before}
        changed = {p for p in before if p in after and before[p] != after[p]}
        blobs   = {entry(d)['blob_id']: d for d in list(before.values()) + list(after.values())}
        result  = Vault__Renames(**kw).detect(deleted, added, content_of=lambda e: blobs[e['blob_id']])
        out     = {(str(p.old_path), str(p.new_path)): int(p.score) for p in result.pairs}
        return out, result, changed

    def git(self, tmp_path, before: dict, after: dict, *args) -> dict:
        repo = tmp_path / 'repo'
        if repo.exists():
            shutil.rmtree(repo)
        repo.mkdir()
        git = [GIT, '-C', str(repo), '-c', 'user.name=t', '-c', 'user.email=t@t', '-c', 'commit.gpgsign=false']
        subprocess.run(git[:3] + ['init', '-q'], check=True)
        for files, message in ((before, 'a'), (after, 'b')):
            for old in list(repo.rglob('*')):
                if old.is_file() and '.git' not in old.parts:
                    old.unlink()
            for path, data in files.items():
                (repo / path).parent.mkdir(parents=True, exist_ok=True)
                (repo / path).write_bytes(data)
            subprocess.run(git + ['add', '-A'], check=True)
            subprocess.run(git + ['commit', '-q', '--allow-empty', '-m', message], check=True)
        out = subprocess.run(git + ['diff', '--name-status', '-M', *args, 'HEAD~1', 'HEAD'], capture_output=True,
                             check=True).stdout.decode()
        pairs = {}
        for row in out.splitlines():
            fields = row.split('\t')
            if fields[0].startswith('R'):
                pairs[(fields[1], fields[2])] = int(fields[0][1:])
        return pairs


@pytest.mark.skipif(GIT is None, reason='git is the oracle')
class Test_Vault__Renames__Git_Oracle(Renames__Oracle):

    def scenario(self, seed: int) -> tuple:
        rng    = random.Random(seed)
        before = {f'{rng.choice(["a", "b/c", "d"])}/f{i}.txt': text(seed * 100 + i, rng.randrange(5, 60))
                  for i in range(12)}
        after  = dict(before)
        for path in rng.sample(sorted(before), 6):
            data = after.pop(path)
            kind = rng.random()
            if kind < 0.25:                                                  # deleted
                continue
            lines = data.splitlines(keepends=True)
            for _ in range(rng.randrange(0, len(lines) // 2 + 1)):            # edited: some lines changed
                lines[rng.randrange(len(lines))] = f'edit {rng.randrange(10 ** 6)}\n'.encode()
            if kind < 0.5:                                                    # moved, same basename
                after[f'moved/{path.split("/")[-1]}'] = b''.join(lines)
            else:                                                             # moved and renamed
                after[f'new/g{rng.randrange(10 ** 6)}.txt'] = b''.join(lines)
        for i in range(rng.randrange(0, 3)):
            after[f'added/n{i}.txt'] = text(seed * 7 + i, 20)
        return before, after

    @pytest.mark.parametrize('seed', range(40))
    def test_random_moves_give_gits_pairs_and_scores(self, tmp_path, seed):
        before, after = self.scenario(seed)
        ours, _, _    = self.detect(before, after)
        theirs        = self.git(tmp_path, before, after)
        assert set(ours) == set(theirs)
        assert all(abs(ours[k] - theirs[k]) <= 1 for k in ours), (ours, theirs)

    @pytest.mark.parametrize('kept', [49, 51, 75, 95])
    def test_the_threshold(self, tmp_path, kept):
        data   = b''.join(f'line {i}\n'.encode() for i in range(100))
        before = {'a.txt': data}
        after  = {'b.txt': b''.join(data.splitlines(keepends=True)[:kept])}
        ours, _, _ = self.detect(before, after)
        assert ours.keys() == self.git(tmp_path, before, after).keys()

    def test_exact_moves_and_the_basename_preference(self, tmp_path):
        same   = b'same content\n'
        before = {'x/one.txt': same, 'y/two.txt': same, 'z/keep.txt': b'k\n'}
        after  = {'q/two.txt': same, 'r/one.txt': same, 'z/keep.txt': b'k\n'}
        ours, result, _ = self.detect(before, after)
        assert ours == self.git(tmp_path, before, after) == {('x/one.txt', 'r/one.txt'): 100,
                                                             ('y/two.txt', 'q/two.txt'): 100}
        assert all(p.exact for p in result.pairs)

    @pytest.mark.parametrize('case', ['lone', 'several', 'same names'])
    def test_empty_files(self, tmp_path, case):
        before, after = {'lone': ({'e1': b''}, {'e2': b''}),
                         'several': ({'e1': b'', 'e2': b''}, {'f1': b'', 'f2': b''}),
                         'same names': ({'a/e': b'', 'a/f': b''}, {'b/e': b'', 'b/f': b''})}[case]
        ours, _, _ = self.detect(before, after)
        assert ours == self.git(tmp_path, before, after)

    def test_the_rename_limit_skips_only_the_inexact_pass(self, tmp_path):
        before = {f'old/a{i}.txt': text(i, 30) for i in range(6)}
        before['old/same.txt'] = text(99, 30)
        after  = {f'new/b{i}.txt': text(i, 30)[:-20] + b'x\n' for i in range(6)}
        after['elsewhere/same.txt'] = text(99, 30)[:-20] + b'y\n'                 # basename pass: no limit
        ours, result, _ = self.detect(before, after, limit=2)
        assert result.limit_hit
        assert ours.keys() == self.git(tmp_path, before, after, '-l2').keys() == {('old/same.txt', 'elsewhere/same.txt')}


class Test_Vault__Renames:

    def test_disabled_and_exact_only(self):
        data = text(1, 20)
        assert Vault__Renames(enabled=False).detect({'a': entry(data)}, {'b': entry(data)}).pairs == []
        edited = data[:-10] + b'z\n'
        result = Vault__Renames(exact_only=True).detect({'a': entry(data)}, {'b': entry(edited)},
                                                        content_of=lambda e: data if e['size'] == len(data) else edited)
        assert result.pairs == []

    def test_without_content_only_exact_renames(self):
        data = text(2, 20)
        result = Vault__Renames().detect({'a': entry(data), 'c': entry(text(3, 5))}, {'b': entry(data), 'd': entry(text(4, 5))})
        assert [(str(p.old_path), str(p.new_path)) for p in result.pairs] == [('a', 'b')]

    def test_an_unreadable_blob_is_counted_never_raised(self):
        result = Vault__Renames().detect({'a': entry(b'one\n')}, {'b': entry(b'two\n')}, content_of=lambda e: None)
        assert result.pairs == [] and int(result.unread) == 1                     # b; a is never asked for

    def test_verify_exact_drops_a_lying_claim(self):
        claim = dict(entry(b'x\n'))
        lie   = dict(claim, blob_id='obj-other')
        blobs = {claim['blob_id']: b'x\n', 'obj-other': b'something else entirely\n'}
        result = Vault__Renames().detect({'a': claim}, {'b': lie}, content_of=lambda e: blobs[e['blob_id']],
                                         verify_exact=True)
        assert result.pairs == []
