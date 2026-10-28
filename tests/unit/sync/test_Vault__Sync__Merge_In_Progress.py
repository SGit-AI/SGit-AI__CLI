"""A merge with conflicts in progress (phase 0: design__00 F5, B1, B2).

- commit refuses while a conflict is unresolved: it used to commit anyway, `.conflict`
  files included, so every teammate who pulled received them (B1);
- write, stash, branch switch and checkout are refused by name, like pull and push;
- status carries, and the CLI prints, which files are still conflicted (B2)."""
import json
import os

import pytest

from sgit_ai.cli.CLI__Vault                      import CLI__Vault
from sgit_ai.core.Vault__Errors                  import (Vault__Merge_Unresolved_Error, Vault__Merge_In_Progress_Error,
                                                         Vault__Operation_In_Progress_Error, Vault__Push_With_Conflicts_Error)
from sgit_ai.core.Vault__Head_Paths              import Vault__Head_Paths
from sgit_ai.core.Vault__Operation_Guard         import Vault__Operation_Guard
from sgit_ai.core.actions.branch.Vault__Branch_Switch import Vault__Branch_Switch
from sgit_ai.core.actions.merge.Vault__Merge__Resolve import Vault__Merge__Resolve
from sgit_ai.core.actions.stash.Vault__Stash     import Vault__Stash
from sgit_ai.crypto.PKI__Crypto                  import PKI__Crypto
from sgit_ai.storage.Vault__Storage              import Vault__Storage
import tests.unit.sync.test_Vault__Sync__Pull     as pull_tests
from tests.unit.sync.vault_test_env              import Vault__Test_Env


class Test_Vault__Sync__Merge_In_Progress:

    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_single_vault()

    def setup_method(self):
        self.env       = self._env.restore()
        self.crypto    = self.env.crypto
        self.pki       = PKI__Crypto()
        self.sync      = self.env.sync
        self.directory = self.env.vault_dir
        with open(os.path.join(self.directory, 'shared.txt'), 'w') as f:
            f.write('local version')
        self.sync.commit(self.directory, message='local change')
        pull_tests.Test_Vault__Sync__Pull._simulate_remote_push(self, self.directory, {'shared.txt': 'remote version'})
        assert self.sync.pull(self.directory)['status'] == 'conflicts'
        self.head_before = self.sync.resolve_revision(self.directory, 'HEAD')

    def teardown_method(self):
        self.env.cleanup()

    def _conflict_file(self):
        return os.path.join(self.directory, 'shared.txt.conflict')

    # --- B1: commit ---------------------------------------------------------------

    def test_commit_refuses_while_a_conflict_is_unresolved(self):
        with pytest.raises(Vault__Merge_Unresolved_Error) as error:
            self.sync.commit(self.directory, message='would commit the .conflict file')
        assert error.value.paths == ['shared.txt']
        assert 'shared.txt.conflict' in str(error.value)
        assert 'sgit merge-abort' in str(error.value)
        assert self.sync.resolve_revision(self.directory, 'HEAD') == self.head_before
        assert 'shared.txt.conflict' not in Vault__Head_Paths(crypto=self.crypto).paths(self.directory)

    def test_amend_refuses_too(self):
        with pytest.raises(Vault__Merge_Unresolved_Error):
            self.sync.commit(self.directory, message='amend', amend=True)

    def test_deleting_the_conflict_file_resolves_it_and_commit_makes_the_merge(self):
        os.remove(self._conflict_file())
        result = self.sync.commit(self.directory, message='merged by hand')
        assert result['merge_commit'] is True
        assert 'shared.txt.conflict' not in Vault__Head_Paths(crypto=self.crypto).paths(self.directory)
        assert Vault__Operation_Guard().in_progress(self.directory) == ''

    def test_resolve_theirs_then_commit(self):
        Vault__Merge__Resolve().resolve_file(self.directory, 'shared.txt', 'theirs')
        result = self.sync.commit(self.directory, message='took theirs')
        assert result['merge_commit'] is True
        with open(os.path.join(self.directory, 'shared.txt')) as f:
            assert f.read() == 'remote version'

    # --- F5: the other commands -----------------------------------------------------

    def test_write_is_refused(self):
        with pytest.raises(Vault__Merge_In_Progress_Error) as error:
            self.sync.write_file(self.directory, 'other.txt', b'x')
        assert 'Cannot write: merge in progress' in str(error.value)
        assert self.sync.resolve_revision(self.directory, 'HEAD') == self.head_before

    def test_stash_is_refused(self):
        with pytest.raises(Vault__Merge_In_Progress_Error):
            Vault__Stash(crypto=self.crypto).stash(self.directory)

    def test_branch_switch_is_refused(self):
        with pytest.raises(Vault__Merge_In_Progress_Error):
            Vault__Branch_Switch(crypto=self.crypto).switch(self.directory, 'current')

    def test_pull_and_push_keep_their_message(self):
        with pytest.raises(Vault__Merge_In_Progress_Error) as error:
            self.sync.pull(self.directory)
        assert "Cannot pull: merge in progress. Use 'sgit resolve'" in str(error.value)
        with pytest.raises((Vault__Merge_In_Progress_Error, Vault__Push_With_Conflicts_Error)):
            self.sync.push(self.directory)                                 # the .conflict check comes first

    # --- B2: status -------------------------------------------------------------------

    def test_status_lists_the_unresolved_files(self):
        result = self.sync.status(self.directory)
        assert result['merge_in_progress'] is True
        assert result['merge_unresolved'] == ['shared.txt']
        os.remove(self._conflict_file())
        assert self.sync.status(self.directory)['merge_unresolved'] == []

    def test_cli_prints_the_merge_block(self, capsys):
        CLI__Vault._print_merge_block(None, self.sync.status(self.directory))
        out = capsys.readouterr().out
        assert 'Merge in progress (files style): 1 unresolved, 0 resolved' in out
        assert '! shared.txt   theirs is in shared.txt.conflict' in out
        assert 'Abandon: sgit merge-abort' in out

    def test_cli_prints_nothing_without_a_merge(self, capsys):
        CLI__Vault._print_merge_block(None, dict(merge_in_progress=False))
        assert capsys.readouterr().out == ''


class Test_Vault__Operation_Guard:

    def test_nothing_in_progress(self, tmp_path):
        Vault__Operation_Guard().check(str(tmp_path), 'commit')
        assert Vault__Operation_Guard().in_progress(str(tmp_path)) == ''

    @pytest.mark.parametrize('state_file, operation, hint', [
        ('bisect.json'                          , 'bisect', "sgit history bisect reset"),
        (os.path.join('rebase', 'state.json')   , 'rebase', "sgit history rebase --continue"),
    ])
    def test_bisect_and_rebase_state_are_recognised(self, tmp_path, state_file, operation, hint):
        local = Vault__Storage().local_dir(str(tmp_path))
        path  = os.path.join(local, state_file)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w') as f:
            json.dump({}, f)
        assert Vault__Operation_Guard().in_progress(str(tmp_path)) == operation
        with pytest.raises(Vault__Operation_In_Progress_Error) as error:
            Vault__Operation_Guard().check(str(tmp_path), 'push')
        assert f'Cannot push: {operation} in progress' in str(error.value)
        assert hint in str(error.value)
        assert not isinstance(error.value, Vault__Merge_In_Progress_Error)
