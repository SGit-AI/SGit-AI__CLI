"""sgit history blame (design__04 step 5): git blame is the oracle. The same history is
built in a git repository and in a vault; for every line, the commit that git blame names
(matched by its unique message), the original line number and the original path must be
ours. Plus -L ranges, -w, boundaries, merges, binary files and the three output formats."""
import json
import os
import random
import shutil
import subprocess

import pytest

from sgit_ai.cli.CLI__Main                         import CLI__Main
from sgit_ai.core.Vault__Errors                    import Vault__Revision_Error
from sgit_ai.core.actions.history.Vault__Blame     import Vault__Blame
from sgit_ai.crypto.Vault__Crypto                  import Vault__Crypto
from tests.unit.sync.vault_test_env                import Vault__Test_Env

GIT = shutil.which('git')


CODE = ['}', '', '{', '    return x;', '    i++;', 'end', 'else', 'if (a) {']


def script(seed: int, code: bool = False) -> list:
    """[(message, path, content)] — a file edited many times and renamed once. With
    `code`, most lines repeat (`}`, blank lines), where differs disagree on placement."""
    rng   = random.Random(seed)
    lines = [f'base {i}' if not code or rng.random() < .4 else rng.choice(CODE) for i in range(rng.randrange(8, 20))]
    steps, path = [('c0 start', 'doc.txt', list(lines))], 'doc.txt'
    for k in range(1, rng.randrange(5, 10)):
        for _ in range(rng.randrange(1, 4)):
            op = rng.random()
            at = rng.randrange(len(lines) + 1)
            if op < 0.35 and len(lines) > 3 and at < len(lines):
                del lines[at]
            elif op < 0.7:
                lines.insert(at, rng.choice(CODE) if code and rng.random() < .5 else f'add {k}.{rng.randrange(1000)}')
            elif at < len(lines):
                lines[at] = rng.choice(CODE) if code and rng.random() < .5 else f'chg {k}.{rng.randrange(1000)}'
        if k == 3:
            path = 'renamed/doc-v2.txt'
        if lines == steps[-1][2] and path == steps[-1][1]:                     # a step that changed nothing
            lines.append(f'step {k}')
        steps.append((f'c{k} step', path, list(lines)))
    return steps


@pytest.mark.skipif(GIT is None, reason='git is the oracle')
class Test_Vault__Blame__Git_Oracle:

    def setup_method(self):
        self.env = Vault__Test_Env()
        self.env.setup_single_vault(files={'other.txt': 'x\n'})
        self.vault = self.env.restore()

    def teardown_method(self):
        self.vault.cleanup()
        self.env.cleanup_snapshot()

    def replay_sgit(self, steps) -> str:
        d, current = self.vault.vault_dir, None
        for message, path, lines in steps:
            if current and current != path:
                os.remove(os.path.join(d, current))
            full = os.path.join(d, path)
            os.makedirs(os.path.dirname(full) or d, exist_ok=True)
            with open(full, 'w') as f:
                f.write(''.join(l + '\n' for l in lines))
            self.vault.sync.commit(d, message=message)
            current = path
        return current

    def replay_git(self, tmp_path, steps) -> dict:
        repo = tmp_path / 'repo'
        repo.mkdir()
        git = [GIT, '-C', str(repo), '-c', 'user.name=t', '-c', 'user.email=t@t', '-c', 'commit.gpgsign=false']
        subprocess.run(git[:3] + ['init', '-q'], check=True)
        current = None
        for message, path, lines in steps:
            if current and current != path:
                (repo / current).unlink()
            (repo / path).parent.mkdir(parents=True, exist_ok=True)
            (repo / path).write_text(''.join(l + '\n' for l in lines))
            subprocess.run(git + ['add', '-A'], check=True)
            subprocess.run(git + ['commit', '-q', '-m', message], check=True)
            current = path
        out = subprocess.run(git + ['blame', '--line-porcelain', current], capture_output=True, check=True).stdout.decode()
        rows, header = {}, None
        for row in out.splitlines():
            if row.startswith('\t'):
                rows[header['final']] = (header['summary'], header['orig'], header['filename'])
            elif len(row.split(' ')) >= 3 and len(row.split(' ')[0]) == 40:
                sha, orig, final = row.split(' ')[:3]
                header = dict(orig=int(orig), final=int(final))
            elif row.startswith('summary '):
                header['summary'] = row[len('summary '):]
            elif row.startswith('filename '):
                header['filename'] = row[len('filename '):]
        return rows

    @pytest.mark.parametrize('code', [False, True])
    @pytest.mark.parametrize('seed', range(25))
    def test_every_line_is_attributed_as_git_attributes_it(self, tmp_path, seed, code):
        steps  = script(seed, code)
        final  = self.replay_sgit(steps)
        theirs = self.replay_git(tmp_path, steps)
        result = Vault__Blame(crypto=Vault__Crypto()).blame(self.vault.vault_dir, final)
        ours   = {int(l.final_line): (str(result.commits[str(l.commit_id)].summary), int(l.orig_line), str(l.orig_path))
                  for l in result.lines}
        assert ours == theirs


class Test_Vault__Blame:

    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_single_vault(files={'a.txt': 'one\ntwo\nthree\nfour\nfive\n', 'logo.bin': '\x00\x01'})

    def setup_method(self):
        self.env  = self._env.restore()
        self.sync = self.env.sync
        self.dir  = self.env.vault_dir
        with open(os.path.join(self.dir, 'a.txt'), 'w') as f:
            f.write('one\nTWO\nthree\n  four\nfive\nsix\n')
        self.sync.commit(self.dir, message='second')

    def teardown_method(self):
        self.env.cleanup()

    def blame(self, *ranges, **kw):
        return Vault__Blame(crypto=Vault__Crypto(), **kw).blame(self.dir, 'a.txt', ranges=list(ranges) or None)

    def summaries(self, result) -> list:
        return [str(result.commits[str(l.commit_id)].summary) for l in result.lines]

    def test_attribution_and_ranges(self):
        assert self.summaries(self.blame()) == ['initial commit', 'second', 'initial commit', 'second', 'initial commit',
                                                'second']
        assert [int(l.final_line) for l in self.blame('2,+2').lines] == [2, 3]
        assert [int(l.final_line) for l in self.blame('5').lines] == [5, 6]
        assert [int(l.final_line) for l in self.blame('/three/,+2', '1,1').lines] == [1, 3, 4]
        assert [int(l.final_line) for l in self.blame(',2').lines] == [1, 2]

    def test_ignore_whitespace(self):
        assert self.summaries(self.blame(ignore_whitespace=True))[3] == 'initial commit'

    def test_errors(self):
        with pytest.raises(Vault__Revision_Error, match='file has only 6 lines'):
            self.blame('9')
        with pytest.raises(Vault__Revision_Error, match='does not exist'):
            Vault__Blame(crypto=Vault__Crypto()).blame(self.dir, 'nope.txt')
        with pytest.raises(Vault__Revision_Error, match='binary file'):
            Vault__Blame(crypto=Vault__Crypto()).blame(self.dir, 'logo.bin')
        with pytest.raises(Vault__Revision_Error, match='repeats a repetition'):
            self.blame('/(a+)+/')

    def test_an_older_revision(self):
        result = Vault__Blame(crypto=Vault__Crypto()).blame(self.dir, 'a.txt', rev='HEAD~1')
        assert self.summaries(result) == ['initial commit'] * 5

    def cli(self, capsys, *argv) -> tuple:
        here = os.getcwd()
        os.chdir(self.dir)
        code = 0
        try:
            CLI__Main().run(['--base-url', 'http://127.0.0.1:9', 'history', 'blame'] + list(argv))
        except SystemExit as e:
            code = e.code or 0
        finally:
            os.chdir(here)
        captured = capsys.readouterr()
        return code, captured.out, captured.err

    def test_the_default_format(self, capsys):
        code, out, _ = self.cli(capsys, 'a.txt')
        rows = out.splitlines()
        assert code == 0 and len(rows) == 6
        assert rows[1].endswith(' 2) TWO') and ' +0000 ' in rows[1]
        assert rows[0].split(' ')[0] != rows[1].split(' ')[0]

    def test_porcelain_and_line_porcelain(self, capsys):
        code, out, _ = self.cli(capsys, '--porcelain', 'a.txt')
        assert code == 0 and out.count('\t') == 6 and out.count('summary second') == 1
        assert 'filename a.txt' in out and 'author-tz +0000' in out
        _, line_out, _ = self.cli(capsys, '--line-porcelain', 'a.txt')
        assert line_out.count('summary ') == 6

    def test_json(self, capsys):
        code, out, _ = self.cli(capsys, '--json', 'a.txt')
        data = json.loads(out)
        assert data['schema'] == 'history_blame_v1' and len(data['lines']) == 6
        assert data['lines'][1]['text'] == 'TWO'

    def test_a_missing_file_exits_1(self, capsys):
        code, _, err = self.cli(capsys, 'nope.txt')
        assert code == 1 and 'does not exist' in err


class Test_Vault__Blame__Merge:

    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_two_clones(files={'shared.txt': ''.join(f'line {i}\n' for i in range(20))})

    def setup_method(self):
        self.env = self._env.restore()

    def teardown_method(self):
        self.env.cleanup()

    def test_lines_from_both_sides_of_a_merge(self):
        sync, alice, bob = self.env.sync, self.env.alice_dir, self.env.bob_dir
        with open(os.path.join(alice, 'shared.txt'), 'w') as f:
            f.write(''.join(f'line {i}\n' if i != 2 else 'ALICE\n' for i in range(20)))
        sync.commit(alice, message='alice edit')
        sync.push(alice)
        with open(os.path.join(bob, 'shared.txt'), 'w') as f:
            f.write(''.join(f'line {i}\n' if i != 17 else 'BOB\n' for i in range(20)))
        sync.commit(bob, message='bob edit')
        assert sync.pull(bob, merge_style='lines')['status'] == 'merged'
        result = Vault__Blame(crypto=Vault__Crypto()).blame(bob, 'shared.txt')
        by_line = {int(l.final_line): str(result.commits[str(l.commit_id)].summary) for l in result.lines}
        assert by_line[3] == 'alice edit' and by_line[18] == 'bob edit' and by_line[1] == 'initial commit'
