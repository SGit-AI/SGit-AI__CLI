"""`sgit commit --list-hunks / --hunk / -p` on a real vault (design__03 §5.3, 9.2).

The working copy is never written: the commit holds the chosen hunks, the file keeps
every change, and status shows the rest as still modified."""
import io
import json
import os

import pytest

from sgit_ai.cli.CLI__Hunk_Prompt                 import CLI__Hunk_Prompt
from sgit_ai.core.Vault__Errors                   import Vault__Hunk_Selection_Error, Vault__Partial_Commit_Error
from tests.unit.core.actions.commit.test_Commit__Paths import Commit_Paths__Base

BASE = ''.join(f'line {i}\n' for i in range(1, 41))


def edited(at: dict) -> str:
    lines = BASE.splitlines(keepends=True)
    for i, text in at.items():
        lines[i] = text + '\n'
    return ''.join(lines)


class Commit_Patch__Base(Commit_Paths__Base):

    @classmethod
    def setup_class(cls):
        from tests.unit.sync.vault_test_env import Vault__Test_Env
        cls._env = Vault__Test_Env()
        cls._env.setup_single_vault(files={'notes.txt': BASE, 'other.txt': 'o\n', 'gone.txt': 'g\n'})

    def listing(self, paths=None, split=False):
        return self.sync.list_hunks(self.dir, paths=paths, split=split)

    def hunks_of(self, path, split=False):
        return [f for f in self.listing(split=split).files if str(f.path) == path][0].hunks

    def read(self, rel) -> str:
        with open(os.path.join(self.dir, rel)) as f:
            return f.read()


class Test_Commit__Patch(Commit_Patch__Base):

    def test_one_hunk_of_two_is_committed_and_the_file_keeps_both(self):
        work = edited({2: 'FIRST', 30: 'SECOND'})
        self.write('notes.txt', work)
        first, second = self.hunks_of('notes.txt')
        result = self.sync.commit(self.dir, message='first only', hunks=[str(first.hunk_id)])
        assert result['paths'] == ['notes.txt'] and result['left_uncommitted'] == ['notes.txt']
        assert self.committed()['notes.txt'] == edited({2: 'FIRST'})
        assert self.read('notes.txt') == work                                   # never written
        assert self.sync.status(self.dir)['modified'] == ['notes.txt']
        remaining = self.hunks_of('notes.txt')
        assert [h.removed for h in remaining] == [1] and 'SECOND' in str(remaining[0].text)
        assert str(remaining[0].hunk_id) != str(second.hunk_id)                 # ids name the base: HEAD moved

    def test_a_split_part_commits_one_change_of_a_hunk(self):
        self.write('notes.txt', edited({10: 'X', 14: 'Y'}))
        whole = self.hunks_of('notes.txt')
        assert len(whole) == 1 and whole[0].splittable
        parts = self.hunks_of('notes.txt', split=True)
        self.sync.commit(self.dir, message='y', hunks=[str(parts[1].hunk_id)])
        assert self.committed()['notes.txt'] == edited({14: 'Y'})

    def test_hunks_from_two_files_and_whole_file_hunks(self):
        self.write('notes.txt', edited({5: 'N'}))
        self.write('new.txt', 'brand new\n')
        os.remove(os.path.join(self.dir, 'gone.txt'))
        ids = {str(f.path): str(f.hunks[0].hunk_id) for f in self.listing().files}
        assert set(ids) == {'notes.txt', 'new.txt', 'gone.txt'}
        result = self.sync.commit(self.dir, message='two', hunks=[ids['new.txt'], ids['gone.txt']])
        assert result['paths'] == ['gone.txt', 'new.txt'] and result['left_uncommitted'] == ['notes.txt']
        committed = self.committed()
        assert committed['new.txt'] == 'brand new\n' and 'gone.txt' not in committed
        assert committed['notes.txt'] == BASE

    def test_paths_narrow_the_listing(self):
        self.write('notes.txt', edited({5: 'N'}))
        self.write('other.txt', 'O\n')
        assert [str(f.path) for f in self.listing(paths=['other.txt']).files] == ['other.txt']

    def test_a_stale_id_refuses_and_writes_nothing(self):
        self.write('notes.txt', edited({5: 'N'}))
        stale = str(self.hunks_of('notes.txt')[0].hunk_id)
        self.write('notes.txt', edited({5: 'N2'}))
        head = self.head()
        with pytest.raises(Vault__Hunk_Selection_Error, match=f'no such hunk: {stale}'):
            self.sync.commit(self.dir, message='x', hunks=[stale])
        assert self.head() == head

    def test_an_id_outside_the_named_paths_refuses(self):
        self.write('notes.txt', edited({5: 'N'}))
        self.write('other.txt', 'O\n')
        hunk = str(self.hunks_of('notes.txt')[0].hunk_id)
        with pytest.raises(Vault__Hunk_Selection_Error):
            self.sync.commit(self.dir, message='x', paths=['other.txt'], hunks=[hunk])

    def test_refused_during_a_merge(self):
        from sgit_ai.core.actions.merge.Vault__Merge__State import Vault__Merge__State
        self.write('notes.txt', edited({5: 'N'}))
        hunk  = str(self.hunks_of('notes.txt')[0].hunk_id)
        state = Vault__Merge__State()
        state.write(self.dir, state.new_state(self.head(), self.head(), self.head(), []))
        with pytest.raises(Vault__Partial_Commit_Error):
            self.sync.commit(self.dir, message='x', hunks=[hunk])

    def test_the_secret_guard_runs_on_a_chosen_hunk(self):
        import zipfile
        with zipfile.ZipFile(os.path.join(self.dir, 'backup.zip'), 'w') as z:   # binary: one whole-file hunk
            z.writestr('.sg_vault/local/vault_key', 'k')
        hunk = str(self.hunks_of('backup.zip')[0].hunk_id)
        head = self.head()
        with pytest.raises(Exception, match='backup.zip'):
            self.sync.commit(self.dir, message='zip', hunks=[hunk])
        assert self.head() == head


class Test_Commit__Patch__CLI(Commit_Patch__Base):

    def run(self, *argv) -> int:
        from sgit_ai.cli.CLI__Main import CLI__Main
        here = os.getcwd()
        os.chdir(self.dir)
        try:
            CLI__Main().run(['--base-url', 'http://127.0.0.1:9', 'commit'] + list(argv))
            return 0
        except SystemExit as e:
            return e.code or 0
        finally:
            os.chdir(here)

    def test_list_then_commit_by_id(self, capsys):
        self.write('notes.txt', edited({2: 'FIRST', 30: 'SECOND'}))
        assert self.run('--list-hunks', '--json') == 0
        listing = json.loads(capsys.readouterr().out)
        hunks   = listing['files'][0]['hunks']
        assert listing['base_commit'] == self.head() and len(hunks) == 2
        assert hunks[0]['header'] == '@@ -1,6 +1,6 @@' and '+FIRST\n' in hunks[0]['text']
        assert self.run('-m', 'second', '--hunk', hunks[1]['hunk_id'], '--json') == 0
        out = json.loads(capsys.readouterr().out)
        assert out['status'] == 'committed' and out['left_uncommitted'] == ['notes.txt']
        assert self.committed()['notes.txt'] == edited({30: 'SECOND'})

    def test_the_text_listing(self, capsys):
        self.write('notes.txt', edited({10: 'X', 14: 'Y'}))
        assert self.run('--list-hunks') == 0
        out = capsys.readouterr().out
        assert 'notes.txt  (modified)' in out and '[splittable: --split]' in out and '+X' in out
        assert self.run('--list-hunks', '--split') == 0
        assert capsys.readouterr().out.count('  h-') == 2

    def test_a_stale_id_is_a_usage_error(self, capsys):
        self.write('notes.txt', edited({2: 'FIRST'}))
        assert self.run('-m', 'x', '--hunk', 'h-000000000000') == 2
        assert 'no such hunk: h-000000000000' in capsys.readouterr().err

    def test_list_and_hunk_together_is_a_usage_error(self, capsys):
        assert self.run('--list-hunks', '--hunk', 'h-000000000000') == 2

    def test_patch_without_a_terminal_points_at_the_agent_flags(self, capsys):
        self.write('notes.txt', edited({2: 'FIRST'}))
        assert self.run('-p', '-m', 'x') == 2
        assert 'use --list-hunks to see the hunks and --hunk ID' in capsys.readouterr().err


class Test_CLI__Hunk_Prompt(Commit_Patch__Base):

    def choose(self, monkeypatch, answers: str) -> list:
        monkeypatch.setattr('sys.stdin', io.StringIO(answers))
        return CLI__Hunk_Prompt(listing=self.listing(), parts=self.listing(split=True)).choose()

    def setup_method(self):
        super().setup_method()
        self.write('notes.txt', edited({2: 'A', 10: 'B', 14: 'C', 30: 'D'}))    # hunks: [A], [B C] splittable, [D]
        self.write('other.txt', 'O\n')
        self.ids = [str(h.hunk_id) for f in self.listing().files for h in f.hunks]

    def test_y_and_n(self, monkeypatch):
        assert self.choose(monkeypatch, 'y\nn\ny\nn\n') == [self.ids[0], self.ids[2]]

    def test_a_and_d_cover_the_rest_of_the_file(self, monkeypatch):
        assert self.choose(monkeypatch, 'n\na\nn\n') == self.ids[1:3]
        assert self.choose(monkeypatch, 'd\ny\n') == [self.ids[3]]

    def test_split_then_choose_a_part(self, monkeypatch, capsys):
        chosen = self.choose(monkeypatch, 'n\ns\nn\ny\nn\nn\n')
        assert 'Split into 2 hunks.' in capsys.readouterr().out
        self.sync.commit(self.dir, message='C only', hunks=chosen)
        assert self.committed()['notes.txt'] == edited({14: 'C'})

    def test_q_keeps_what_was_decided(self, monkeypatch):
        assert self.choose(monkeypatch, 'y\nq\n') == [self.ids[0]]

    def test_j_k_navigate_and_help_prints(self, monkeypatch, capsys):
        assert self.choose(monkeypatch, 'j\nk\ny\n?\nn\nn\nn\n') == [self.ids[0]]
        assert 'split the current hunk' in capsys.readouterr().out

    def test_end_of_input_chooses_nothing(self, monkeypatch):
        assert self.choose(monkeypatch, 'y\n') == []


@pytest.mark.skipif(os.name != 'posix', reason='a pseudo-terminal is POSIX')
class Test_Commit__Patch__Terminal(Commit_Patch__Base):

    def run_in_terminal(self, answers: bytes, *argv) -> tuple:
        import pty
        import subprocess
        import sys
        import time
        master, slave = pty.openpty()
        env  = dict(os.environ, PYTHONPATH=os.getcwd())
        proc = subprocess.Popen([sys.executable, '-m', 'sgit_ai', '--base-url', 'http://127.0.0.1:9', 'commit'] + list(argv),
                                cwd=self.dir, stdin=slave, stdout=slave, stderr=slave, env=env)
        os.close(slave)
        output, deadline, sent = b'', time.time() + 60, False
        while True:
            try:
                chunk = os.read(master, 4096)
            except OSError:                                                     # the child closed the terminal
                break
            if not chunk:
                break
            output += chunk
            if not sent and b'Commit this hunk' in output:
                os.write(master, answers)
                sent = True
            if time.time() > deadline:
                proc.kill()
                break
        os.close(master)
        return proc.wait(timeout=30), output.decode('utf-8', 'replace')

    def test_patch_in_a_terminal_commits_the_chosen_hunk(self):
        self.write('notes.txt', edited({2: 'FIRST', 30: 'SECOND'}))
        code, out = self.run_in_terminal(b'n\ny\n', '-p', '-m', 'second only')
        assert code == 0, out
        assert '(1/2) Commit this hunk [y,n,q,a,d,j,k,?]?' in out and 'Committed 1 file(s)' in out
        assert self.committed()['notes.txt'] == edited({30: 'SECOND'})
        assert self.read('notes.txt') == edited({2: 'FIRST', 30: 'SECOND'})
