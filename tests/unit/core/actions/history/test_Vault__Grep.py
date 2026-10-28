"""sgit grep (design__04 step 6) with git grep as the oracle: for each set of options the
output and the exit code equal `git grep`'s on a repository holding the same files, the
same uncommitted edit and the same untracked file; revisions, pathspecs, context, -c / -l
/ -L / -o / -v / -w / -i / -m, binary files. Plus the guard, the error exit 2 and --json."""
import json
import os
import shutil
import subprocess

import pytest

from sgit_ai.cli.CLI__Main            import CLI__Main
from tests.unit.sync.vault_test_env   import Vault__Test_Env

GIT = shutil.which('git')
FILES = {'a.txt'          : 'one\ntwo\nthree\nfour\nfive\nsix\nseven\neight\nnine\nten\n',
         'docs/b.md'      : '# Title\nfive fingers\nFive Guys\nnothing here\nfivefold\nhigh-five\n',
         'docs/deep/c.py' : 'def five():\n    return 5\n\nprint(five())\n',
         'logo.bin'       : 'five\x00binary\n',
         'other.txt'      : 'unrelated\n'}
EDIT  = ('docs/b.md', 'EDITED five\n')                                       # uncommitted, appended
NEW   = ('untracked.txt', 'five in an untracked file\n')

CASES = [
    ['five'], ['-n', 'five'], ['-i', 'five'], ['-w', 'five'], ['-v', 'five'], ['-c', 'five'], ['-l', 'five'],
    ['-L', 'five'], ['-o', '-n', 'fi[a-z]e'], ['-n', '-C', '1', 'four'], ['-n', '-A', '1', 'five'],
    ['-n', '-B', '2', 'nine'], ['-m', '1', 'five'], ['-h', 'five'], ['-F', 'high-five'], ['-e', 'one', '-e', 'ten'],
    ['-n', 'five', 'HEAD~1'], ['-n', 'one', 'HEAD~1'], ['five', 'HEAD', '--', 'docs'], ['-l', 'five', '--', '*.py'], ['--untracked', 'five'],
    ['-I', 'five'], ['-q', 'five'], ['zzz-no-match'], ['-c', '-v', 'e'], ['-w', '-i', 'FIVE', '--', 'docs/b.md'],
]


@pytest.mark.skipif(GIT is None, reason='git is the oracle')
class Test_Vault__Grep__Git_Oracle:

    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_single_vault(files={'a.txt': 'old one\n'})

    def setup_method(self, method):
        import tempfile
        self.env  = self._env.restore()
        self.dir  = self.env.vault_dir
        self.repo = tempfile.mkdtemp(prefix='sgit-grep-git-')
        git = self.git_cmd()
        subprocess.run(git[:3] + ['init', '-q'], check=True)
        for target in (self.dir, self.repo):
            self.write(target, 'a.txt', 'old one\n')
        subprocess.run(git + ['add', '-A'], check=True)
        subprocess.run(git + ['commit', '-q', '-m', 'first'], check=True)
        for target in (self.dir, self.repo):
            for path, text in FILES.items():
                self.write(target, path, text)
        self.env.sync.commit(self.dir, message='second')
        subprocess.run(git + ['add', '-A'], check=True)
        subprocess.run(git + ['commit', '-q', '-m', 'second'], check=True)
        for target in (self.dir, self.repo):
            self.write(target, EDIT[0], FILES[EDIT[0]] + EDIT[1])
            self.write(target, *NEW)

    def teardown_method(self, method):
        self.env.cleanup()
        shutil.rmtree(self.repo, ignore_errors=True)

    def git_cmd(self) -> list:
        return [GIT, '-C', self.repo, '-c', 'user.name=t', '-c', 'user.email=t@t', '-c', 'commit.gpgsign=false',
                '-c', 'grep.lineNumber=false', '-c', 'color.grep=never']

    def write(self, root, path, text):
        full = os.path.join(root, path)
        os.makedirs(os.path.dirname(full) or root, exist_ok=True)
        with open(full, 'w') as f:
            f.write(text)

    def sgit(self, capsys, args) -> tuple:
        here = os.getcwd()
        os.chdir(self.dir)
        code = 0
        try:
            CLI__Main().run(['--base-url', 'http://127.0.0.1:9', 'grep'] + list(args))
        except SystemExit as e:
            code = e.code or 0
        finally:
            os.chdir(here)
        return code, capsys.readouterr().out

    def gitgrep(self, args) -> tuple:
        args = ['-E' if a == '-E' else a for a in args]
        done = subprocess.run(self.git_cmd() + ['grep', '-E'] + list(args), capture_output=True, cwd=self.repo)
        return done.returncode, done.stdout.decode()

    @pytest.mark.parametrize('case', CASES, ids=[' '.join(c) for c in CASES])
    def test_the_same_output_and_exit_code_as_git_grep(self, capsys, case):
        assert self.sgit(capsys, case) == self.gitgrep(case)


class Test_Vault__Grep:

    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_single_vault(files={'a.txt': 'alpha\nbeta\n'})

    def setup_method(self):
        self.env = self._env.restore()
        self.dir = self.env.vault_dir

    def teardown_method(self):
        self.env.cleanup()

    def sgit(self, capsys, *args) -> tuple:
        here = os.getcwd()
        os.chdir(self.dir)
        code = 0
        try:
            CLI__Main().run(['--base-url', 'http://127.0.0.1:9'] + list(args))
        except SystemExit as e:
            code = e.code or 0
        finally:
            os.chdir(here)
        captured = capsys.readouterr()
        return code, captured.out, captured.err

    def test_errors_exit_2(self, capsys):
        assert self.sgit(capsys, 'grep', '(a+)+$')[0] == 2
        code, _, err = self.sgit(capsys, 'grep', 'x', 'no-such-rev')
        assert code == 2 and 'error:' in err
        code, _, err = self.sgit(capsys, 'grep', 'x', '--', ':!a.txt')
        assert code == 2 and 'pathspec magic' in err

    def test_json(self, capsys):
        code, out, _ = self.sgit(capsys, 'grep', '--json', 'beta')
        data = json.loads(out)
        assert code == 0 and data['schema'] == 'grep_v1'
        assert [(m['path'], m['line'], m['text'], m['spans']) for m in data['matches']] == [('a.txt', 2, 'beta', [[0, 4]])]

    def test_file_grep_is_the_same_command(self, capsys):
        assert self.sgit(capsys, 'file', 'grep', '-n', 'beta')[:2] == (0, 'a.txt:2:beta\n')

    def test_a_tracked_file_not_on_disk_is_counted_not_searched(self, capsys):
        os.remove(os.path.join(self.dir, 'a.txt'))
        code, out, _ = self.sgit(capsys, 'grep', '--json', 'beta')
        assert code == 1 and json.loads(out)['skipped']['not_checked_out'] == 1
        assert self.sgit(capsys, 'grep', 'beta', 'HEAD')[:2] == (0, 'HEAD:a.txt:beta\n')
