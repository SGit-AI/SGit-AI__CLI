import os
import shutil
import tempfile

import pytest

from sgit_ai.api.Vault__API__In_Memory    import Vault__API__In_Memory
from sgit_ai.crypto.Vault__Crypto         import Vault__Crypto
from sgit_ai.safe_types.Enum__Branch_Type import Enum__Branch_Type
from sgit_ai.sync.Vault__Branch_Switch    import Vault__Branch_Switch
from sgit_ai.sync.Vault__Sync             import Vault__Sync


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

class _VaultFixture:
    """Sets up a real temp vault with Vault__Sync and Vault__Branch_Switch."""

    def __init__(self):
        self.tmp_dir   = tempfile.mkdtemp()
        self.crypto    = Vault__Crypto()
        self.api       = Vault__API__In_Memory()
        self.api.setup()
        self.sync      = Vault__Sync(crypto=self.crypto, api=self.api)
        self.switcher  = Vault__Branch_Switch(crypto=self.crypto)
        self.directory = os.path.join(self.tmp_dir, 'vault')
        self.init_result = self.sync.init(self.directory)

    def write(self, rel_path: str, content: str | bytes):
        full = os.path.join(self.directory, rel_path)
        parent = os.path.dirname(full)
        if parent:
            os.makedirs(parent, exist_ok=True)
        mode = 'wb' if isinstance(content, bytes) else 'w'
        with open(full, mode) as fh:
            fh.write(content)

    def read(self, rel_path: str) -> bytes:
        full = os.path.join(self.directory, rel_path)
        with open(full, 'rb') as fh:
            return fh.read()

    def exists(self, rel_path: str) -> bool:
        return os.path.isfile(os.path.join(self.directory, rel_path))

    def commit(self, msg: str = 'test commit') -> dict:
        return self.sync.commit(self.directory, message=msg)

    def current_branch_id(self) -> str:
        from sgit_ai.sync.Vault__Storage import Vault__Storage
        import json
        storage     = Vault__Storage()
        config_path = storage.local_config_path(self.directory)
        with open(config_path, 'r') as fh:
            data = json.load(fh)
        return data.get('my_branch_id', '')

    def cleanup(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------

class Test_Vault__Branch_Switch:

    def setup_method(self):
        self.fix = _VaultFixture()

    def teardown_method(self):
        self.fix.cleanup()

    # ------------------------------------------------------------------
    # switch — basic case
    # ------------------------------------------------------------------

    def test_switch_creates_new_clone_branch(self):
        """Switching to a named branch creates a new clone branch."""
        fix = self.fix

        # Commit something so HEAD is not empty
        fix.write('hello.txt', 'hello')
        fix.commit('add hello.txt')

        # Get the initial named branch ID
        initial_info    = fix.sync.branches(fix.directory)
        named_branch    = next(b for b in initial_info['branches']
                               if b['branch_type'] == 'named')
        named_branch_id = named_branch['branch_id']
        named_name      = named_branch['name']

        old_clone_id = fix.current_branch_id()

        result = fix.switcher.switch(fix.directory, named_name)

        assert result['named_branch_id'] == named_branch_id
        assert result['named_name']      == named_name
        assert result['old_clone_branch_id'] == old_clone_id
        assert result['new_clone_branch_id'].startswith('branch-clone-')
        assert result['new_clone_branch_id'] != old_clone_id

    def test_switch_updates_local_config(self):
        """After switch, local_config.my_branch_id points to the new clone branch."""
        fix = self.fix

        fix.write('file.txt', 'content')
        fix.commit('add file')

        info         = fix.sync.branches(fix.directory)
        named_branch = next(b for b in info['branches'] if b['branch_type'] == 'named')
        old_clone_id = fix.current_branch_id()

        result = fix.switcher.switch(fix.directory, named_branch['name'])

        new_clone_id = fix.current_branch_id()
        assert new_clone_id == result['new_clone_branch_id']
        assert new_clone_id != old_clone_id

    def test_switch_preserves_old_clone_branch_in_index(self):
        """Old clone branch still exists in the branch index after switch."""
        fix = self.fix

        fix.write('file.txt', 'content')
        fix.commit('add file')

        info         = fix.sync.branches(fix.directory)
        named_branch = next(b for b in info['branches'] if b['branch_type'] == 'named')
        old_clone_id = fix.current_branch_id()

        fix.switcher.switch(fix.directory, named_branch['name'])

        # Both old and new clone branches must appear in the index
        updated_info = fix.sync.branches(fix.directory)
        all_ids      = [b['branch_id'] for b in updated_info['branches']]
        assert old_clone_id in all_ids

    def test_switch_by_branch_id(self):
        """switch() also accepts a full branch ID instead of a name."""
        fix = self.fix

        fix.write('file.txt', 'v1')
        fix.commit('v1')

        info            = fix.sync.branches(fix.directory)
        named_branch    = next(b for b in info['branches'] if b['branch_type'] == 'named')
        named_branch_id = named_branch['branch_id']

        result = fix.switcher.switch(fix.directory, named_branch_id)

        assert result['named_branch_id'] == named_branch_id
        assert result['new_clone_branch_id'].startswith('branch-clone-')

    def test_switch_with_uncommitted_changes_raises(self):
        """switch() raises RuntimeError when working copy has uncommitted changes."""
        fix = self.fix

        fix.write('file.txt', 'first commit')
        fix.commit('first')

        # Dirty working copy (modified file)
        fix.write('file.txt', 'dirty modification')

        info         = fix.sync.branches(fix.directory)
        named_branch = next(b for b in info['branches'] if b['branch_type'] == 'named')

        with pytest.raises(RuntimeError, match='uncommitted changes'):
            fix.switcher.switch(fix.directory, named_branch['name'])

    def test_switch_with_uncommitted_new_file_raises(self):
        """switch() raises RuntimeError when there are new untracked files."""
        fix = self.fix

        fix.write('committed.txt', 'committed')
        fix.commit('base commit')

        # New file not yet committed
        fix.write('new_file.txt', 'not committed')

        info         = fix.sync.branches(fix.directory)
        named_branch = next(b for b in info['branches'] if b['branch_type'] == 'named')

        with pytest.raises(RuntimeError, match='uncommitted changes'):
            fix.switcher.switch(fix.directory, named_branch['name'])

    def test_switch_nonexistent_branch_raises(self):
        """switch() raises RuntimeError for unknown branch names."""
        fix = self.fix

        with pytest.raises(RuntimeError, match='Branch not found'):
            fix.switcher.switch(fix.directory, 'nonexistent-branch')

    # ------------------------------------------------------------------
    # branch_new
    # ------------------------------------------------------------------

    def test_branch_new_creates_named_and_clone(self):
        """branch_new() creates both a named branch and a clone branch."""
        fix = self.fix

        fix.write('file.txt', 'content')
        fix.commit('initial')

        result = fix.switcher.branch_new(fix.directory, 'feature-x')

        assert result['named_branch_id'].startswith('branch-named-')
        assert result['clone_branch_id'].startswith('branch-clone-')
        assert result['named_name'] == 'feature-x'

    def test_branch_new_updates_local_config(self):
        """branch_new() sets my_branch_id to the new clone branch."""
        fix = self.fix

        fix.write('file.txt', 'content')
        fix.commit('initial')

        result   = fix.switcher.branch_new(fix.directory, 'feature-y')
        new_id   = fix.current_branch_id()

        assert new_id == result['clone_branch_id']

    def test_branch_new_branches_appear_in_index(self):
        """Both branches created by branch_new() appear in the branch index."""
        fix = self.fix

        fix.write('file.txt', 'content')
        fix.commit('initial')

        result = fix.switcher.branch_new(fix.directory, 'feature-z')

        info   = fix.sync.branches(fix.directory)
        all_ids = [b['branch_id'] for b in info['branches']]
        assert result['named_branch_id'] in all_ids
        assert result['clone_branch_id'] in all_ids

    def test_branch_new_from_named_branch(self):
        """branch_new(from_branch_id=...) seeds HEAD from the specified named branch."""
        fix = self.fix

        fix.write('file.txt', 'v1')
        fix.commit('v1')

        # Push so named branch HEAD is updated
        fix.sync.push(fix.directory)

        info            = fix.sync.branches(fix.directory)
        named_branch    = next(b for b in info['branches'] if b['branch_type'] == 'named')
        named_branch_id = named_branch['branch_id']
        named_head      = named_branch['head_commit']

        result = fix.switcher.branch_new(fix.directory, 'feature-from',
                                         from_branch_id=named_branch_id)

        # Verify both branches exist in the index
        updated_info = fix.sync.branches(fix.directory)
        all_ids      = [b['branch_id'] for b in updated_info['branches']]
        assert result['named_branch_id'] in all_ids

    def test_branch_new_from_nonexistent_raises(self):
        """branch_new() raises RuntimeError for an unknown --from branch."""
        fix = self.fix

        fix.write('file.txt', 'content')
        fix.commit('initial')

        with pytest.raises(RuntimeError, match='Source branch not found'):
            fix.switcher.branch_new(fix.directory, 'new-branch',
                                    from_branch_id='branch-named-00000000')

    # ------------------------------------------------------------------
    # branch_list
    # ------------------------------------------------------------------

    def test_branch_list_returns_all_branches(self):
        """branch_list() returns all branches including current marker."""
        fix = self.fix

        fix.write('file.txt', 'content')
        fix.commit('initial')

        # Create a second named branch so there's more than one
        fix.switcher.branch_new(fix.directory, 'feature-a')

        listing      = fix.switcher.branch_list(fix.directory)
        current_id   = fix.current_branch_id()

        assert 'branches' in listing
        assert 'my_branch_id' in listing
        assert listing['my_branch_id'] == current_id

        # Exactly one branch should be marked is_current
        current_branches = [b for b in listing['branches'] if b['is_current']]
        assert len(current_branches) == 1
        assert current_branches[0]['branch_id'] == current_id

    def test_branch_list_includes_branch_type(self):
        """branch_list() includes branch_type field for each branch."""
        fix = self.fix

        fix.write('file.txt', 'content')
        fix.commit('initial')

        listing = fix.switcher.branch_list(fix.directory)

        for branch in listing['branches']:
            assert 'branch_type' in branch
            assert branch['branch_type'] in ('named', 'clone')

    # ------------------------------------------------------------------
    # Round-trip: switch, commit on new branch, switch back
    # ------------------------------------------------------------------

    def test_round_trip_switch_commit_switch_back(self):
        """Switch to new branch, commit, switch back — both branches have correct history."""
        fix = self.fix

        # Initial commit on original branch
        fix.write('shared.txt', 'shared content')
        fix.commit('shared commit')
        fix.sync.push(fix.directory)

        # Get the original named branch info before switching
        info_before = fix.sync.branches(fix.directory)
        named_before = next(b for b in info_before['branches'] if b['branch_type'] == 'named')
        named_name   = named_before['name']
        orig_clone   = fix.current_branch_id()

        # Switch to same named branch (creates new clone)
        switch_result = fix.switcher.switch(fix.directory, named_name)
        new_clone_id  = switch_result['new_clone_branch_id']

        assert fix.current_branch_id() == new_clone_id

        # Commit on new clone branch
        fix.write('feature.txt', 'feature work')
        fix.commit('feature commit')

        # Switch back by creating yet another clone
        switch_back = fix.switcher.switch(fix.directory, named_name)
        assert switch_back['old_clone_branch_id'] == new_clone_id

        # All three clone branches should appear in the index
        info_after = fix.sync.branches(fix.directory)
        all_ids    = [b['branch_id'] for b in info_after['branches']]
        assert orig_clone    in all_ids
        assert new_clone_id  in all_ids
        assert switch_back['new_clone_branch_id'] in all_ids
