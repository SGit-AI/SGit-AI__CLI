"""history log -S / -G (design__04 step 7) with git as the oracle: on the same random
histories, the commits git log -S / -G selects (by their unique messages) are ours."""
import os
import random
import shutil
import subprocess

import pytest

from sgit_ai.cli.CLI__Main                          import CLI__Main
from sgit_ai.core.actions.history.Vault__Pickaxe    import Vault__Pickaxe
from sgit_ai.crypto.Vault__Crypto                   import Vault__Crypto
from sgit_ai.objects.Vault__Inspector               import Vault__Inspector
from sgit_ai.core.Vault__Sync__Base                 import Vault__Sync__Base
from tests.unit.sync.vault_test_env                 import Vault__Test_Env

GIT   = shutil.which('git')
WORDS = ['apple', 'banana', 'cherry', 'apple pie', 'Apple', 'date']


def history(seed: int) -> list:
    rng   = random.Random(seed)
    files = {f'f{i}.txt': [rng.choice(WORDS) for _ in range(6)] for i in range(3)}
    steps = [('m0', {p: list(v) for p, v in files.items()})]
    for k in range(1, 9):
        path  = rng.choice(sorted(files))
        lines = files[path]
        op    = rng.random()
        if op < 0.4:
            lines[rng.randrange(len(lines))] = rng.choice(WORDS)
        elif op < 0.7:
            lines.insert(rng.randrange(len(lines) + 1), rng.choice(WORDS))
        elif len(lines) > 2:
            lines.pop(rng.randrange(len(lines)))
        else:
            k_line = rng.randrange(len(lines))
            lines[k_line], lines[-1] = lines[-1], lines[k_line]
        if k == 5:                                                            # move a line: -G sees it, -S may not
            lines.append(lines.pop(0))
        lines.append(f'step {k}')                                             # every step changes something
        steps.append((f'm{k}', {p: list(v) for p, v in files.items()}))
    return steps


@pytest.mark.skipif(GIT is None, reason='git is the oracle')
class Test_Vault__Pickaxe__Git_Oracle:

    def setup_method(self):
        self.env = Vault__Test_Env()
        self.env.setup_single_vault(files={'seed.txt': 'x\n'})
        self.vault = self.env.restore()

    def teardown_method(self):
        self.vault.cleanup()
        self.env.cleanup_snapshot()

    def replay(self, tmp_path, steps):
        d    = self.vault.vault_dir
        repo = tmp_path / 'repo'
        repo.mkdir()
        git  = [GIT, '-C', str(repo), '-c', 'user.name=t', '-c', 'user.email=t@t', '-c', 'commit.gpgsign=false']
        subprocess.run(git[:3] + ['init', '-q'], check=True)
        for message, files in steps:
            for root in (d, str(repo)):
                for path, lines in files.items():
                    with open(os.path.join(root, path), 'w') as f:
                        f.write(''.join(l + '\n' for l in lines))
            self.vault.sync.commit(d, message=message)
            subprocess.run(git + ['add', '-A'], check=True)
            subprocess.run(git + ['commit', '-q', '-m', message], check=True)
        return git

    def ours(self, **kw) -> set:
        d     = self.vault.vault_dir
        c     = Vault__Sync__Base(crypto=Vault__Crypto())._init_components(d)
        chain = Vault__Inspector(crypto=Vault__Crypto()).inspect_commit_dag(d, read_key=c.read_key, limit=1000)
        found = Vault__Pickaxe(**kw).setup().search(d, chain)
        return {e['message'] for e in found if str(e['message']).startswith('m')}

    def theirs(self, git, *args) -> set:
        out = subprocess.run(git + ['log', '--format=%s'] + list(args), capture_output=True, check=True).stdout.decode()
        return set(out.split())

    @pytest.mark.parametrize('seed', range(15))
    def test_s_and_g_select_gits_commits(self, tmp_path, seed):
        git = self.replay(tmp_path, history(seed))
        assert self.ours(mode='S', needle='apple')                  == self.theirs(git, '-S', 'apple')
        assert self.ours(mode='S', needle='apple', ignore_case=True) == self.theirs(git, '-i', '-S', 'apple')
        assert self.ours(mode='G', needle='^banana$')               == self.theirs(git, '-G', '^banana$')
        assert self.ours(mode='S', needle='a[pn]+', regex=True)     == self.theirs(git, '--pickaxe-regex', '-S', 'a[pn]+')


class Test_Vault__Pickaxe__CLI:

    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_single_vault(files={'a.txt': 'one\ntwo\n', 'b.txt': 'other\n'})

    def setup_method(self):
        self.env = self._env.restore()
        self.dir = self.env.vault_dir
        for text, message in (('one\ntwo\nneedle\n', 'add needle'), ('one\ntwo\nneedle\nmore\n', 'unrelated'),
                              ('one\ntwo\n', 'remove needle')):
            with open(os.path.join(self.dir, 'a.txt'), 'w') as f:
                f.write(text)
            self.env.sync.commit(self.dir, message=message)

    def teardown_method(self):
        self.env.cleanup()

    def cli(self, capsys, *argv) -> tuple:
        here = os.getcwd()
        os.chdir(self.dir)
        code = 0
        try:
            CLI__Main().run(['--base-url', 'http://127.0.0.1:9', 'history', 'log'] + list(argv))
        except SystemExit as e:
            code = e.code or 0
        finally:
            os.chdir(here)
        captured = capsys.readouterr()
        return code, captured.out, captured.err

    def test_dash_s_lists_the_commits_that_add_and_remove_it(self, capsys):
        code, out, _ = self.cli(capsys, '-S', 'needle', '--oneline')
        assert code == 0 and 'remove needle' in out and 'add needle' in out and 'unrelated' not in out

    def test_with_a_file_and_a_message_filter(self, capsys):
        assert 'No commits match.' in self.cli(capsys, '-S', 'needle', '--file', 'b.txt')[1]
        _, out, _ = self.cli(capsys, '-S', 'needle', '--grep', 'remove', '--oneline')
        assert 'remove needle' in out and 'add needle' not in out

    def test_stat_lists_the_matching_files(self, capsys):
        _, out, _ = self.cli(capsys, '-G', 'need', '--stat', '--oneline')
        assert 'a.txt' in out and 'b.txt' not in out

    def test_the_walk_stops_at_n(self, capsys):
        _, out, _ = self.cli(capsys, '-S', 'needle', '--oneline', '-n', '1')
        assert 'remove needle' in out and 'add needle' not in out
        read_key = Vault__Sync__Base(crypto=Vault__Crypto())._init_components(self.dir).read_key
        chain = Vault__Inspector(crypto=Vault__Crypto()).inspect_commit_dag(self.dir, read_key=read_key, limit=1000)
        chain = sorted(chain, key=lambda c: int(c.get('timestamp_ms') or 0), reverse=True)
        unreadable = dict(commit_id='obj-cas-imm-000000000000', parents=[], tree_id='obj-cas-imm-000000000000')
        found = Vault__Pickaxe(mode='S', needle='needle').setup().search(self.dir, chain[:1] + [unreadable], limit=1)
        assert [e['commit_id'] for e in found] == [chain[0]['commit_id']]          # the unreadable entry was never opened

    def test_refused_with_json(self, capsys):
        code, _, err = self.cli(capsys, '-S', 'needle', '--json')
        assert code == 1 and '-S / -G work with the plain log' in err
