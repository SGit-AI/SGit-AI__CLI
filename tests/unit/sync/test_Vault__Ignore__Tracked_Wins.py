"""P0 regression suite (decision 17): a vault that tracks .github/** before the
ignore-set change must keep those files across every command, and a fresh vault
must never add them. This is the maintainer's "no side effects on existing
vaults" condition expressed as tests — see
team/explorer/dev/impl-plans/08/17/static-publishing/12__accepted-risks.md §6.
"""
import os
import shutil
import tempfile

from sgit_ai.crypto.Vault__Crypto                     import Vault__Crypto
from sgit_ai.network.api.Vault__API__In_Memory        import Vault__API__In_Memory
from sgit_ai.core.Vault__Sync                         import Vault__Sync
from sgit_ai.core.Vault__Head_Paths                   import Vault__Head_Paths
from sgit_ai.core.actions.admin.Vault__Ignore__Apply  import Vault__Ignore__Apply


class Test_Vault__Ignore__Tracked_Wins__Vault_Level:

    def setup_method(self):
        self.crypto = Vault__Crypto()
        self.api    = Vault__API__In_Memory()
        self.api.setup()
        self.sync   = Vault__Sync(crypto=self.crypto, api=self.api)
        self.tmp    = tempfile.mkdtemp()
        self.vault  = os.path.join(self.tmp, 'vault')

    def teardown_method(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _vault_tracking_github(self):
        """A vault whose head tracks .github/workflows/x.yml — the legacy state
        that existed before .github joined ALWAYS_IGNORED_DIRS. write_file
        commits straight to the head (no work-tree scan), which is exactly how
        such vaults came to exist."""
        self.sync.init(self.vault)
        with open(os.path.join(self.vault, 'readme.md'), 'w') as f:
            f.write('hello')
        self.sync.commit(self.vault, 'initial')
        self.sync.write_file(self.vault, '.github/workflows/x.yml', b'name: ci\n')
        self.sync.push(self.vault)
        return self.vault

    def _head_paths(self):
        return Vault__Head_Paths(crypto=self.crypto).paths(self.vault)

    def test_tracked_github_file_survives_status_and_push(self):
        self._vault_tracking_github()
        status = self.sync.status(self.vault)
        assert status['clean']   is True
        assert status['deleted'] == []
        result = self.sync.push(self.vault)
        assert result['status'] in ('up_to_date',)                    # nothing to push, no deletion
        assert '.github/workflows/x.yml' in self._head_paths()

    def test_tracked_github_file_survives_an_unrelated_commit(self):
        self._vault_tracking_github()
        with open(os.path.join(self.vault, 'readme.md'), 'w') as f:
            f.write('hello v2')
        self.sync.commit(self.vault, 'edit readme')
        heads = self._head_paths()
        assert '.github/workflows/x.yml' in heads
        assert 'readme.md'               in heads

    def test_fresh_vault_never_adds_github(self):
        self.sync.init(self.vault)
        os.makedirs(os.path.join(self.vault, '.github', 'workflows'))
        with open(os.path.join(self.vault, '.github', 'workflows', 'ci.yml'), 'w') as f:
            f.write('name: ci\n')
        with open(os.path.join(self.vault, 'readme.md'), 'w') as f:
            f.write('hello')
        self.sync.commit(self.vault, 'initial')
        heads = self._head_paths()
        assert 'readme.md' in heads
        assert not any(p.startswith('.github/') for p in heads)

    def test_untracked_new_file_under_grandfathered_dir_not_added(self):
        self._vault_tracking_github()
        with open(os.path.join(self.vault, '.github', 'workflows', 'new.yml'), 'w') as f:
            f.write('name: extra\n')
        status = self.sync.status(self.vault)
        assert status['clean'] is True
        assert status['added'] == []

    def test_deleting_grandfathered_file_still_records_a_deletion(self):
        self._vault_tracking_github()
        os.remove(os.path.join(self.vault, '.github', 'workflows', 'x.yml'))
        status = self.sync.status(self.vault)
        assert status['deleted'] == ['.github/workflows/x.yml']
        self.sync.commit(self.vault, 'drop the workflow deliberately')
        assert '.github/workflows/x.yml' not in self._head_paths()

    def test_ignore_apply_removes_in_one_commit_and_keeps_work_tree(self):
        self._vault_tracking_github()
        on_disk = os.path.join(self.vault, '.github', 'workflows', 'x.yml')
        apply_action = Vault__Ignore__Apply(crypto=self.crypto, api=self.api)
        assert apply_action.tracked_under(self.vault, '.github') == ['.github/workflows/x.yml']
        result = apply_action.apply(self.vault, '.github')
        assert result['status']  == 'removed'
        assert result['removed'] == ['.github/workflows/x.yml']
        assert result['commit_id']
        assert os.path.isfile(on_disk)                                # work tree untouched
        assert '.github/workflows/x.yml' not in self._head_paths()
        status = self.sync.status(self.vault)                         # and the vault is clean:
        assert status['clean'] is True                                # the dir is now plain-ignored

    def test_ignore_apply_noop_when_nothing_tracked(self):
        self.sync.init(self.vault)
        with open(os.path.join(self.vault, 'readme.md'), 'w') as f:
            f.write('hello')
        self.sync.commit(self.vault, 'initial')
        result = Vault__Ignore__Apply(crypto=self.crypto, api=self.api).apply(self.vault, '.github')
        assert result['status']    == 'up_to_date'
        assert result['commit_id'] is None

    def test_migration_notice_shown_once(self, capsys):
        # The first scan against a head tracking .github/** emits the notice —
        # here that happens inside push's own status check during setup.
        self._vault_tracking_github()
        setup_output = capsys.readouterr().err
        assert 'sgit vault ignore --apply .github' in setup_output
        self.sync.status(self.vault)
        second = capsys.readouterr().err
        assert 'sgit vault ignore --apply .github' not in second      # once, not every command

    def test_no_notice_for_vault_without_github(self, capsys):
        self.sync.init(self.vault)
        with open(os.path.join(self.vault, 'readme.md'), 'w') as f:
            f.write('hello')
        self.sync.commit(self.vault, 'initial')
        capsys.readouterr()
        self.sync.status(self.vault)
        assert 'sgit vault ignore' not in capsys.readouterr().err

    def test_head_paths_empty_outside_a_vault(self):
        assert Vault__Head_Paths(crypto=self.crypto).paths(self.tmp) == set()

    def test_head_paths_lists_the_working_head(self):
        self._vault_tracking_github()
        assert self._head_paths() == {'readme.md', '.github/workflows/x.yml'}
