"""`sgit commit <pathspec>` — Git's `git commit --only` (roadmap 2.3, design__03 §5.1-5.2).

HEAD's tree with only the named paths taken from the working copy; every other change
stays on disk, uncommitted. Git is the oracle for which paths a commit takes and what
they hold; the documented deviation is that sgit also takes a new file it is told about
(it has no `add`)."""
import json
import os
import shutil
import subprocess
import sys

import pytest

from sgit_ai.cli.CLI__Main                            import CLI__Main
from sgit_ai.core.Vault__Errors                       import (Vault__Pathspec_Error, Vault__Partial_Commit_Error,
                                                              Vault__Scoped_Clone_Error)
from sgit_ai.core.Vault__Head_Paths                   import Vault__Head_Paths
from sgit_ai.core.Vault__Sync__Base                   import Vault__Sync__Base
from sgit_ai.core.actions.merge.Vault__Merge__State   import Vault__Merge__State
from sgit_ai.storage.Vault__Commit                    import Vault__Commit
from sgit_ai.storage.Vault__Storage                   import Vault__Storage
from sgit_ai.storage.Vault__Sub_Tree                  import Vault__Sub_Tree
from sgit_ai.crypto.PKI__Crypto                       import PKI__Crypto
from tests.unit.sync.vault_test_env                   import Vault__Test_Env

GIT   = shutil.which('git')
FILES = {'a.txt': 'a\n', 'b.txt': 'b\n', 'docs/x.md': 'x\n', 'docs/y.md': 'y\n', 'src/z.py': 'z\n',
         'src/deep/w.py': 'w\n', 'other/o.txt': 'o\n'}


class Commit_Paths__Base:

    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_single_vault(files=FILES)

    @classmethod
    def teardown_class(cls):
        cls._env.cleanup_snapshot()

    def setup_method(self):
        self.env  = self._env.restore()
        self.sync = self.env.sync
        self.dir  = self.env.vault_dir

    def teardown_method(self):
        self.env.cleanup()

    def write(self, rel, text):
        full = os.path.join(self.dir, rel)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, 'w') as f:
            f.write(text)

    def committed(self) -> dict:
        flat = Vault__Head_Paths(crypto=self.sync.crypto).flat(self.dir)
        return {p: self.sync.sparse_cat(self.dir, p).decode() for p in sorted(flat)}

    def head(self) -> str:
        return self.sync.resolve_revision(self.dir, 'HEAD')

    def head_tree(self) -> tuple:
        c      = Vault__Sync__Base(crypto=self.sync.crypto, api=self.sync.api)._init_components(self.dir)
        commit = Vault__Commit(crypto=self.sync.crypto, pki=PKI__Crypto(), object_store=c.obj_store,
                               ref_manager=c.ref_manager).load_commit(self.head(), c.read_key)
        sub    = Vault__Sub_Tree(crypto=self.sync.crypto, obj_store=c.obj_store)
        return str(commit.tree_id), sub.flatten_dirs(str(commit.tree_id), c.read_key)

    def objects(self) -> int:
        return sum(len(files) for _, _, files in os.walk(os.path.join(self.dir, '.sg_vault', 'bare')))


class Test_Commit__Paths__Basics(Commit_Paths__Base):

    def test_two_of_five_changes_are_committed_and_three_stay(self):
        for rel in ('a.txt', 'b.txt', 'docs/x.md', 'src/z.py', 'other/o.txt'):
            self.write(rel, 'changed\n')
        result = self.sync.commit(self.dir, message='two', paths=['a.txt', 'docs/x.md'])
        assert result['paths'] == ['a.txt', 'docs/x.md'] and result['files_changed'] == 2
        assert result['left_uncommitted'] == ['b.txt', 'other/o.txt', 'src/z.py']
        committed = self.committed()
        assert committed['a.txt'] == committed['docs/x.md'] == 'changed\n'
        assert committed['b.txt'] == 'b\n' and committed['src/z.py'] == 'z\n'
        status = self.sync.status(self.dir)
        assert sorted(status['modified']) == ['b.txt', 'other/o.txt', 'src/z.py']
        with open(os.path.join(self.dir, 'b.txt')) as f:                         # the working copy is never written
            assert f.read() == 'changed\n'

    def test_a_deletion_by_name(self):
        os.remove(os.path.join(self.dir, 'src/z.py'))
        os.remove(os.path.join(self.dir, 'b.txt'))
        result = self.sync.commit(self.dir, message='rm', paths=['src/z.py'])
        assert result['paths'] == ['src/z.py'] and result['left_uncommitted'] == ['b.txt']
        assert 'src/z.py' not in self.committed() and 'b.txt' in self.committed()

    def test_a_folder_takes_new_files_under_it(self):
        self.write('docs/new.md', 'new\n')
        self.write('docs/x.md', 'x2\n')
        self.write('top-new.txt', 't\n')
        result = self.sync.commit(self.dir, message='docs', paths=['docs'])
        assert result['paths'] == ['docs/new.md', 'docs/x.md']
        assert result['left_uncommitted'] == ['top-new.txt']

    def test_a_new_file_by_name(self):
        self.write('fresh.txt', 'f\n')
        assert self.sync.commit(self.dir, message='new', paths=['fresh.txt'])['paths'] == ['fresh.txt']
        assert self.committed()['fresh.txt'] == 'f\n'

    def test_a_glob_crosses_folders(self):
        self.write('docs/x.md', 'x2\n')
        self.write('a.txt', 'a2\n')
        assert self.sync.commit(self.dir, message='md', paths=['*.md'])['paths'] == ['docs/x.md']

    def test_relative_to_the_current_folder(self):
        self.write('src/z.py', 'z2\n')
        self.write('a.txt', 'a2\n')
        result = self.sync.commit(self.dir, message='rel', paths=['z.py'], cwd=os.path.join(self.dir, 'src'))
        assert result['paths'] == ['src/z.py']

    def test_a_pattern_that_matches_nothing_refuses_and_writes_nothing(self):
        self.write('a.txt', 'a2\n')
        head, objects = self.head(), self.objects()
        with pytest.raises(Vault__Pathspec_Error, match="pathspec 'zzz' did not match any file known to sgit"):
            self.sync.commit(self.dir, message='x', paths=['a.txt', 'zzz'])
        assert (self.head(), self.objects()) == (head, objects)

    def test_an_unchanged_named_path_is_nothing_to_commit(self):
        self.write('b.txt', 'b2\n')
        with pytest.raises(RuntimeError, match='nothing to commit'):
            self.sync.commit(self.dir, message='x', paths=['a.txt'])

    def test_the_whole_copy_commit_is_unchanged(self):
        self.write('a.txt', 'a2\n')
        self.write('b.txt', 'b2\n')
        result = self.sync.commit(self.dir, message='all')
        assert result['files_changed'] == 2 and 'paths' not in result


class Test_Commit__Paths__Tree(Commit_Paths__Base):

    def test_selecting_every_change_gives_the_whole_copy_tree(self):
        self.write('a.txt', 'a2\n')
        self.write('src/deep/w.py', 'w2\n')
        os.remove(os.path.join(self.dir, 'docs/y.md'))
        self.write('new/n.txt', 'n\n')
        self.sync.commit(self.dir, message='p', paths=['new', 'src', 'docs/y.md', 'a.txt'])
        assert self.sync.status(self.dir)['clean']
        path_tree, _ = self.head_tree()
        with pytest.raises(RuntimeError, match='nothing to commit'):              # the whole-copy builder agrees
            self.sync.commit(self.dir, message='all')
        assert self.head_tree()[0] == path_tree

    def test_untouched_folders_keep_their_tree_ids(self):
        _, before = self.head_tree()
        self.write('src/deep/w.py', 'w2\n')
        self.write('docs/x.md', 'x2\n')                                           # changed, not named
        self.sync.commit(self.dir, message='deep', paths=['src/deep/w.py'])
        _, after = self.head_tree()
        assert after['docs'] == before['docs'] and after['other'] == before['other']
        assert after['src'] != before['src'] and after['src/deep'] != before['src/deep']


class Test_Commit__Paths__Refusals(Commit_Paths__Base):

    def test_refused_during_a_merge(self):
        state = Vault__Merge__State()
        state.write(self.dir, state.new_state(self.head(), self.head(), self.head(), []))
        self.write('a.txt', 'a2\n')
        with pytest.raises(Vault__Partial_Commit_Error, match='cannot do a partial commit during a merge'):
            self.sync.commit(self.dir, message='x', paths=['a.txt'])

    def test_escaping_the_vault_is_refused(self):
        with pytest.raises(Vault__Pathspec_Error, match='outside the vault'):
            self.sync.commit(self.dir, message='x', paths=['../elsewhere.txt'])

    def test_an_ignored_file_by_name_says_so(self):
        self.write('.gitignore', '*.log\n')
        self.write('debug.log', 'noise\n')
        with pytest.raises(Vault__Pathspec_Error, match="'debug.log' is ignored by .gitignore"):
            self.sync.commit(self.dir, message='x', paths=['debug.log'])

    def test_a_dot_conflict_file_outside_a_merge_is_an_ordinary_file(self):
        self.write('a.txt.conflict', 'theirs\n')                                 # as the whole-copy commit treats it;
        result = self.sync.commit(self.dir, message='x', paths=['a.txt.conflict'])   # during a merge, refused above
        assert result['paths'] == ['a.txt.conflict']

    def test_the_secret_guard_runs_on_the_named_paths_only(self):
        import zipfile
        with zipfile.ZipFile(os.path.join(self.dir, 'backup.zip'), 'w') as z:
            z.writestr('.sg_vault/local/vault_key', 'k')
        self.write('a.txt', 'a2\n')
        assert self.sync.commit(self.dir, message='a', paths=['a.txt'])['paths'] == ['a.txt']
        with pytest.raises(Exception, match='backup.zip'):
            self.sync.commit(self.dir, message='zip', paths=['backup.zip'])


class Test_Commit__Paths__Amend(Commit_Paths__Base):

    def test_amend_overlays_the_named_path_and_keeps_the_parents(self):
        self.write('a.txt', 'a2\n')
        self.sync.commit(self.dir, message='first', paths=['a.txt'])
        parent_before = self.sync.resolve_revision(self.dir, 'HEAD~1')
        self.write('a.txt', 'a3\n')
        self.write('b.txt', 'b2\n')
        result = self.sync.commit(self.dir, message='', amend=True, paths=['a.txt'])
        assert result['message'] == 'first'
        assert self.sync.resolve_revision(self.dir, 'HEAD~1') == parent_before
        assert self.committed()['a.txt'] == 'a3\n' and self.committed()['b.txt'] == 'b\n'


class Test_Commit__Paths__Sparse(Commit_Paths__Base):

    def set_sparse(self):
        path = Vault__Storage().local_config_path(self.dir)
        with open(path) as f:
            config = json.load(f)
        config['sparse'] = True
        with open(path, 'w') as f:
            json.dump(config, f)

    def test_a_never_checked_out_path_is_not_deleted_by_a_folder(self):
        from sgit_ai.storage.Vault__Checkout_Set import Vault__Checkout_Set
        self.set_sparse()
        Vault__Checkout_Set().save(self.dir, sorted(set(FILES) - {'src/z.py'}))
        os.remove(os.path.join(self.dir, 'src/z.py'))                             # never checked out
        os.remove(os.path.join(self.dir, 'src/deep/w.py'))                        # checked out, removed
        result = self.sync.commit(self.dir, message='src', paths=['src'])
        assert result['paths'] == ['src/deep/w.py']
        assert 'src/z.py' in self.committed()


class Test_Commit__Paths__Scoped(Commit_Paths__Base):

    def test_a_named_path_outside_the_scope_is_refused(self):
        path = Vault__Storage().local_config_path(self.dir)
        with open(path) as f:
            config = json.load(f)
        config['scope_paths'] = ['docs']
        with open(path, 'w') as f:
            json.dump(config, f)
        self.write('a.txt', 'a2\n')
        self.write('docs/x.md', 'x2\n')
        with pytest.raises(Vault__Scoped_Clone_Error):
            self.sync.commit(self.dir, message='x', paths=['a.txt'])
        assert self.sync.commit(self.dir, message='docs', paths=['docs'])['paths'] == ['docs/x.md']


class Test_Commit__Paths__CLI(Commit_Paths__Base):

    def run(self, *argv, cwd=None) -> tuple:
        here = os.getcwd()
        os.chdir(cwd or self.dir)
        code = 0
        try:
            CLI__Main().run(['--base-url', 'http://127.0.0.1:9', 'commit'] + list(argv))   # the test vault records no server
        except SystemExit as e:
            code = e.code or 0
        finally:
            os.chdir(here)
        return code

    def test_with_m_every_positional_is_a_path(self, capsys):
        self.write('a.txt', 'a2\n')
        self.write('b.txt', 'b2\n')
        assert self.run('-m', 'only a', 'a.txt', '--json') == 0
        out = json.loads(capsys.readouterr().out)
        assert out['status'] == 'committed' and out['paths'] == ['a.txt'] and out['left_uncommitted'] == ['b.txt']
        assert out['message'] == 'only a'

    def test_message_then_double_dash_then_paths(self, capsys):
        self.write('a.txt', 'a2\n')
        self.write('b.txt', 'b2\n')
        assert self.run('the message', '-d', '.', '--', 'b.txt') == 0
        out = capsys.readouterr().out
        assert 'Committed 1 file(s)' in out and '(1 of 2 changed; 1 left uncommitted)' in out
        assert 'Left uncommitted: a.txt' in out
        assert self.committed()['b.txt'] == 'b2\n' and self.committed()['a.txt'] == 'a\n'

    def test_double_dash_with_no_message(self, capsys):
        self.write('a.txt', 'a2\n')
        self.write('b.txt', 'b2\n')
        assert self.run('--', 'a.txt') == 0
        assert 'Committed 1 file(s)' in capsys.readouterr().out
        assert self.run('--', 'b.txt', '--json') == 1                              # after --, even --json is a path
        assert "pathspec '--json' did not match" in capsys.readouterr().err

    def test_the_legacy_message_form_is_unchanged(self, capsys):
        self.write('a.txt', 'a2\n')
        self.write('b.txt', 'b2\n')
        assert self.run('fix typo') == 0
        assert 'Committed 2 file(s)' in capsys.readouterr().out

    def test_two_positionals_without_m_is_a_usage_error(self, capsys):
        self.write('a.txt', 'a2\n')
        assert self.run('msg', 'a.txt') == 2
        assert 'sgit commit "msg" -- a.txt' in capsys.readouterr().err

    def test_m_with_a_stray_word_says_it_was_read_as_a_path(self, capsys):
        self.write('a.txt', 'a2\n')
        head = self.head()
        assert self.run('-m', 'x', 'y') == 1
        err = capsys.readouterr().err
        assert "pathspec 'y' did not match" in err and '"y" was read as a path' in err
        assert self.head() == head

    def test_refusal_as_json(self, capsys):
        assert self.run('-m', 'x', 'nope', '--json') == 1
        out = json.loads(capsys.readouterr().out)
        assert out['status'] == 'refused' and out['paths'] == ['nope']

    def test_relative_to_the_shell_folder(self, capsys):
        self.write('src/z.py', 'z2\n')
        self.write('a.txt', 'a2\n')
        assert self.run('-m', 'z', 'z.py', '-d', self.dir, '--json', cwd=os.path.join(self.dir, 'src')) == 0
        assert json.loads(capsys.readouterr().out)['paths'] == ['src/z.py']


@pytest.mark.skipif(GIT is None, reason='git is the oracle')
class Test_Commit__Paths__Git_Oracle(Commit_Paths__Base):

    SCENARIOS = {
        'files and a deletion' : (['a.txt', 'src/z.py'],),
        'a folder'             : (['docs'],),
        'a glob over folders'  : (['*.py'],),
        'dot in a sub folder'  : (['.'], 'src'),
        'parent from a folder' : (['../a.txt', 'deep'], 'src'),
    }

    def edit(self, root):
        for rel, text in (('a.txt', 'A\n'), ('b.txt', 'B\n'), ('docs/x.md', 'X\n'), ('src/deep/w.py', 'W\n')):
            with open(os.path.join(root, rel), 'w') as f:
                f.write(text)
        os.remove(os.path.join(root, 'src/z.py'))
        os.remove(os.path.join(root, 'docs/y.md'))

    def git_repo(self, tmp_path) -> str:
        repo = str(tmp_path / 'git')
        for rel, text in FILES.items():
            os.makedirs(os.path.dirname(os.path.join(repo, rel)), exist_ok=True)
            with open(os.path.join(repo, rel), 'w') as f:
                f.write(text)
        git = [GIT, '-C', repo, '-c', 'user.name=t', '-c', 'user.email=t@t', '-c', 'commit.gpgsign=false']
        subprocess.run(git[:3] + ['init', '-q'], check=True)
        subprocess.run(git + ['add', '.'], check=True)
        subprocess.run(git + ['commit', '-q', '-m', 'base'], check=True)
        return repo

    def git_committed(self, repo) -> dict:
        names = subprocess.run([GIT, '-C', repo, 'ls-tree', '-r', '--name-only', 'HEAD'],
                               capture_output=True, text=True, check=True).stdout.split()
        return {n: subprocess.run([GIT, '-C', repo, 'show', f'HEAD:{n}'], capture_output=True, text=True,
                                  check=True).stdout for n in sorted(names)}

    @pytest.mark.parametrize('name', sorted(SCENARIOS))
    def test_the_same_paths_and_contents_as_git(self, tmp_path, name):
        patterns, sub = (self.SCENARIOS[name] + ('',))[:2]
        repo = self.git_repo(tmp_path)
        self.edit(repo)
        self.edit(self.dir)
        subprocess.run([GIT, '-c', 'user.name=t', '-c', 'user.email=t@t', '-c', 'commit.gpgsign=false',
                        'commit', '-q', '-m', 'p', '--'] + patterns, cwd=os.path.join(repo, sub), check=True)
        self.sync.commit(self.dir, message='p', paths=patterns, cwd=os.path.join(self.dir, sub))
        assert self.committed() == self.git_committed(repo)
