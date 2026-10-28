"""Renames in history show / diff / log (design__04 step 4) on a real vault: R rows, Git's
rename header and patch (git as the oracle), JSON files_renamed, -M / --no-renames, and
log --file --follow."""
import json
import os
import shutil
import subprocess

import pytest

from sgit_ai.cli.CLI__Main                      import CLI__Main
from sgit_ai.core.actions.diff.Vault__Diff      import Vault__Diff
from sgit_ai.core.actions.diff.Vault__Renames   import Vault__Renames
from sgit_ai.crypto.Vault__Crypto               import Vault__Crypto
from tests.unit.sync.vault_test_env             import Vault__Test_Env

GIT  = shutil.which('git')
BODY = ''.join(f'line {i}\n' for i in range(40))


class Test_Vault__Diff__Renames:

    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_single_vault(files={'docs/guide.md': BODY, 'docs/same.md': 'same\n', 'keep.txt': 'k\n'})

    def setup_method(self):
        self.env  = self._env.restore()
        self.sync = self.env.sync
        self.dir  = self.env.vault_dir

    def teardown_method(self):
        self.env.cleanup()

    def move(self, old, new, text=None):
        with open(os.path.join(self.dir, old)) as f:
            data = f.read()
        os.remove(os.path.join(self.dir, old))
        os.makedirs(os.path.dirname(os.path.join(self.dir, new)) or self.dir, exist_ok=True)
        with open(os.path.join(self.dir, new), 'w') as f:
            f.write(text if text is not None else data)

    def commit_moves(self) -> tuple:
        before = self.sync.resolve_revision(self.dir, 'HEAD')
        self.move('docs/guide.md', 'manual/guide-v2.md', BODY.replace('line 7\n', 'line SEVEN\n'))
        self.move('docs/same.md', 'archive/same.md')
        return before, self.sync.commit(self.dir, message='moves')['commit_id']

    def cli(self, *argv) -> int:
        here = os.getcwd()
        os.chdir(self.dir)
        try:
            CLI__Main().run(['--base-url', 'http://127.0.0.1:9'] + list(argv))
            return 0
        except SystemExit as e:
            return e.code or 0
        finally:
            os.chdir(here)

    def test_show_lists_renames_with_their_scores(self):
        _, cid = self.commit_moves()
        _, result = Vault__Diff(crypto=Vault__Crypto()).show_commit(self.dir, cid)
        rows = {(str(f.status), str(f.old_path or ''), str(f.path), int(f.similarity)) for f in result.files}
        assert rows == {('renamed', 'docs/same.md', 'archive/same.md', 100),
                        ('renamed', 'docs/guide.md', 'manual/guide-v2.md', 96)}

    @pytest.mark.skipif(GIT is None, reason='git is the oracle')
    def test_the_rename_patch_is_gits(self, tmp_path):
        _, cid = self.commit_moves()
        _, result = Vault__Diff(crypto=Vault__Crypto()).show_commit(self.dir, cid)
        ours = next(str(f.diff_text) for f in result.files if str(f.path) == 'manual/guide-v2.md')
        repo = tmp_path / 'repo'
        (repo / 'docs').mkdir(parents=True)
        (repo / 'docs' / 'guide.md').write_text(BODY)
        git = ['git', '-C', str(repo), '-c', 'user.name=t', '-c', 'user.email=t@t', '-c', 'commit.gpgsign=false']
        subprocess.run(git[:3] + ['init', '-q'], check=True)
        subprocess.run(git + ['add', '-A'], check=True)
        subprocess.run(git + ['commit', '-q', '-m', 'a'], check=True)
        (repo / 'docs' / 'guide.md').unlink()
        (repo / 'manual').mkdir()
        (repo / 'manual' / 'guide-v2.md').write_text(BODY.replace('line 7\n', 'line SEVEN\n'))
        subprocess.run(git + ['add', '-A'], check=True)
        theirs = subprocess.run(git + ['diff', '--cached', '-M', '--no-color'], capture_output=True,
                                check=True).stdout.decode()
        theirs = ''.join(l for l in theirs.splitlines(keepends=True) if not l.startswith('index '))
        assert ours == theirs

    def test_no_renames_and_the_threshold(self):
        before, cid = self.commit_moves()
        off = Vault__Diff(crypto=Vault__Crypto(), renames=Vault__Renames(enabled=False)).diff_commits(self.dir, before, cid)
        assert sorted(str(f.status) for f in off.files) == ['added', 'added', 'deleted', 'deleted']
        strict = Vault__Diff(crypto=Vault__Crypto(), renames=Vault__Renames(min_score=98)).diff_commits(self.dir, before, cid)
        assert sorted(str(f.status) for f in strict.files) == ['added', 'deleted', 'renamed']   # the exact one stays

    def test_log_json_has_files_renamed_and_not_added_or_deleted(self, capsys):
        before, cid = self.commit_moves()
        assert self.cli('history', 'log', f'{before}..{cid}', '--json') == 0
        entry = json.loads(capsys.readouterr().out)['commits'][-1]
        assert entry['files_added'] == [] and entry['files_deleted'] == []
        assert {(r['old_path'], r['new_path'], r['score'], r['exact']) for r in entry['files_renamed']} == \
               {('docs/same.md', 'archive/same.md', 100, True), ('docs/guide.md', 'manual/guide-v2.md', 96, False)}

    def test_cli_rows_and_no_renames(self, capsys):
        before, cid = self.commit_moves()
        assert self.cli('history', 'show', cid, '--files-only') == 0
        out = capsys.readouterr().out
        assert 'R096  docs/guide.md -> manual/guide-v2.md' in out and 'R100  docs/same.md -> archive/same.md' in out
        assert '2 renamed' in out
        assert self.cli('history', 'show', cid, '--files-only', '--no-renames') == 0
        assert 'renamed' not in capsys.readouterr().out
        assert self.cli('history', 'show', cid, '--files-only', '-M99') == 0
        assert 'R096' not in capsys.readouterr().out

    def test_percent_options_as_git_reads_them(self):
        r = Vault__Renames()
        assert [r.percent_from_option(t) for t in ('9', '90', '90%', '0.9', '5', '50%', '', '100%')] == \
               [90, 90, 90, 90, 50, 50, 50, 100]

    def test_log_file_follow(self, capsys):
        self.commit_moves()
        with open(os.path.join(self.dir, 'manual/guide-v2.md'), 'a') as f:
            f.write('appended\n')
        self.sync.commit(self.dir, message='append')
        plain  = Vault__Diff(crypto=Vault__Crypto()).log_file(self.dir, 'manual/guide-v2.md')
        follow = Vault__Diff(crypto=Vault__Crypto()).log_file(self.dir, 'manual/guide-v2.md', follow=True)
        assert [e['status'] for e in plain] == ['modified', 'added']
        assert [e['status'] for e in follow][:2] == ['modified', 'renamed'] and follow[-1]['path'] == 'docs/guide.md'
        assert follow[1]['old_path'] == 'docs/guide.md' and len(follow) == 3
        assert self.cli('history', 'log', '--file', 'manual/guide-v2.md', '--follow') == 0
        assert '(docs/guide.md -> manual/guide-v2.md)' in capsys.readouterr().out
