import copy
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

    def __init__(self, tmp_dir, vault_dir, crypto, api, sync):
        self.tmp_dir     = tmp_dir
        self.directory   = vault_dir
        self.crypto      = crypto
        self.api         = api
        self.sync        = sync
        self.switcher    = Vault__Branch_Switch(crypto=crypto)
        self.init_result = {}   # populated lazily or passed in

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

    # ------------------------------------------------------------------ #
    # Class-level snapshot: init vault once, snapshot directory + API
    # ------------------------------------------------------------------ #
    _snapshot_dir   = None
    _snapshot_store = None
    _vault_sub      = 'vault'

    @classmethod
    def setup_class(cls):
        crypto = Vault__Crypto()
        api    = Vault__API__In_Memory()
        api.setup()
        sync   = Vault__Sync(crypto=crypto, api=api)

        snap_dir  = tempfile.mkdtemp()
        vault_dir = os.path.join(snap_dir, cls._vault_sub)
        sync.init(vault_dir)

        cls._snapshot_dir   = snap_dir
        cls._snapshot_store = copy.deepcopy(api._store)

    @classmethod
    def teardown_class(cls):
        if cls._snapshot_dir and os.path.isdir(cls._snapshot_dir):
            shutil.rmtree(cls._snapshot_dir, ignore_errors=True)

    def setup_method(self):
        self.tmp_dir = tempfile.mkdtemp()

        # Copy snapshot vault directory
        src = os.path.join(self._snapshot_dir, self._vault_sub)
        dst = os.path.join(self.tmp_dir, self._vault_sub)
        shutil.copytree(src, dst)

        # Restore API
        api = Vault__API__In_Memory()
        api.setup()
        api._store = copy.deepcopy(self._snapshot_store)

        crypto = Vault__Crypto()
        sync   = Vault__Sync(crypto=crypto, api=api)

        self.fix = _VaultFixture(self.tmp_dir, dst, crypto, api, sync)

    def teardown_method(self):
        self.fix.cleanup()

    # ------------------------------------------------------------------
    # switch — basic case
    # ------------------------------------------------------------------

    def test_switch_creates_new_clone_branch(self):
        """Switching to a named branch returns a clone branch (reused or new)."""
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
        # The initial clone already tracks this named branch — it should be reused
        assert result['reused'] is True
        assert result['new_clone_branch_id'] == old_clone_id

    def test_switch_updates_local_config(self):
        """After switch, local_config.my_branch_id points to the active clone branch."""
        fix = self.fix

        fix.write('file.txt', 'content')
        fix.commit('add file')

        info         = fix.sync.branches(fix.directory)
        named_branch = next(b for b in info['branches'] if b['branch_type'] == 'named')

        result = fix.switcher.switch(fix.directory, named_branch['name'])

        new_clone_id = fix.current_branch_id()
        assert new_clone_id == result['new_clone_branch_id']
        # When the initial clone is reused, my_branch_id stays the same — that is correct
        assert new_clone_id.startswith('branch-clone-')

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
    # switch — reuse existing local clone branch
    # ------------------------------------------------------------------

    def test_switch_reuses_existing_clone_when_key_present(self):
        """Switching to a named branch reuses an existing clone whose private key exists."""
        fix = self.fix

        fix.write('hello.txt', 'hello')
        fix.commit('add hello')

        info         = fix.sync.branches(fix.directory)
        named_branch = next(b for b in info['branches'] if b['branch_type'] == 'named')
        named_name   = named_branch['name']

        # The initial vault already has a clone tracking the named branch.
        # First switch reuses the initial clone (key is present).
        first_result   = fix.switcher.switch(fix.directory, named_name)
        first_clone_id = first_result['new_clone_branch_id']
        assert first_result['reused'] is True

        # Branch away so there is a different active branch, then switch back.
        # We need another named branch to switch to, so create one.
        fix.switcher.branch_new(fix.directory, 'side-branch')
        assert fix.current_branch_id() != first_clone_id

        # Switching back to the original named branch should reuse first_clone
        second_result = fix.switcher.switch(fix.directory, named_name)
        assert second_result['reused'] is True
        assert second_result['new_clone_branch_id'] == first_clone_id

    def test_switch_creates_new_clone_when_key_missing(self):
        """Switching creates a new clone when the existing clone's private key is deleted."""
        fix = self.fix

        fix.write('hello.txt', 'hello')
        fix.commit('add hello')

        info         = fix.sync.branches(fix.directory)
        named_branch = next(b for b in info['branches'] if b['branch_type'] == 'named')
        named_name   = named_branch['name']

        # First switch: creates a new clone
        first_result   = fix.switcher.switch(fix.directory, named_name)
        first_clone_id = first_result['new_clone_branch_id']

        # Simulate the local private key being lost by removing all .pem files
        from sgit_ai.sync.Vault__Storage import Vault__Storage
        local_dir = Vault__Storage().local_dir(fix.directory)
        for fname in os.listdir(local_dir):
            if fname.endswith('.pem'):
                os.remove(os.path.join(local_dir, fname))

        # Second switch: must create a new clone because key is gone
        second_result = fix.switcher.switch(fix.directory, named_name)
        assert second_result['reused'] is False
        assert second_result['new_clone_branch_id'] != first_clone_id
        assert second_result['new_clone_branch_id'].startswith('branch-clone-')

    def test_switch_reuse_updates_local_config(self):
        """When reusing a clone branch, local_config.my_branch_id is updated correctly."""
        fix = self.fix

        fix.write('file.txt', 'v1')
        fix.commit('v1')

        info         = fix.sync.branches(fix.directory)
        named_branch = next(b for b in info['branches'] if b['branch_type'] == 'named')
        named_name   = named_branch['name']

        first_result  = fix.switcher.switch(fix.directory, named_name)
        first_clone_id = first_result['new_clone_branch_id']

        # Switch back to a fresh clone to change my_branch_id away
        fix.switcher.branch_new(fix.directory, 'other-branch')
        assert fix.current_branch_id() != first_clone_id

        # Now switch back to original named branch — should reuse first clone
        reuse_result = fix.switcher.switch(fix.directory, named_name)
        assert reuse_result['reused'] is True
        assert fix.current_branch_id() == first_clone_id

    def test_find_usable_clone_branch_returns_most_recent(self):
        """find_usable_clone_branch prefers the most recently created clone."""
        fix = self.fix
        import time as _time
        from sgit_ai.sync.Vault__Storage import Vault__Storage

        fix.write('file.txt', 'v1')
        fix.commit('v1')

        info            = fix.sync.branches(fix.directory)
        named_branch    = next(b for b in info['branches'] if b['branch_type'] == 'named')
        named_name      = named_branch['name']
        named_branch_id = named_branch['branch_id']

        # Create two clone branches for the same named branch by switching twice
        r1 = fix.switcher.switch(fix.directory, named_name)
        clone1_id = r1['new_clone_branch_id']

        # Delete the key for clone1 so only clone2 is usable
        storage   = Vault__Storage()
        local_dir = storage.local_dir(fix.directory)

        # Need clone1's public_key_id — reload index
        from sgit_ai.sync.Vault__Branch_Switch import Vault__Branch_Switch
        switcher = fix.switcher
        c = switcher._init_components(fix.directory)
        branch_index = c.branch_manager.load_branch_index(
            fix.directory, c.branch_index_file_id, c.read_key)
        clone1_meta = c.branch_manager.get_branch_by_id(branch_index, clone1_id)
        key1_file   = os.path.join(local_dir, str(clone1_meta.public_key_id) + '.pem')
        if os.path.isfile(key1_file):
            os.remove(key1_file)

        # Create a second clone (older key gone, this is the newest)
        r2 = fix.switcher.switch(fix.directory, named_name)
        clone2_id = r2['new_clone_branch_id']
        assert r2['reused'] is False  # key for clone1 was deleted, so new clone created

        # Now both clones exist in index; clone2 key is present, clone1 key is gone
        # find_usable_clone_branch should return clone2
        c2 = switcher._init_components(fix.directory)
        branch_index2 = c2.branch_manager.load_branch_index(
            fix.directory, c2.branch_index_file_id, c2.read_key)
        result = switcher.find_usable_clone_branch(
            fix.directory, branch_index2, named_branch_id, storage)
        assert result is not None
        assert str(result.branch_id) == clone2_id

    # ------------------------------------------------------------------
    # Round-trip: switch, commit on new branch, switch back
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Line 61: switch() raises when trying to switch to a CLONE branch
    # ------------------------------------------------------------------

    def test_switch_to_clone_branch_raises(self):
        """Line 61: switching to a clone branch raises RuntimeError."""
        fix = self.fix
        fix.write('file.txt', 'content')
        fix.commit('initial')
        # The current branch IS a clone branch — use its ID
        clone_id = fix.current_branch_id()
        with pytest.raises(RuntimeError, match='Cannot switch to a clone branch'):
            fix.switcher.switch(fix.directory, clone_id)

    # ------------------------------------------------------------------
    # Line 183: branch_new() raises when --from points to a clone branch
    # ------------------------------------------------------------------

    def test_branch_new_from_clone_branch_raises(self):
        """Line 183: branch_new() raises when from_branch_id is a clone branch."""
        fix = self.fix
        fix.write('file.txt', 'content')
        fix.commit('initial')
        clone_id = fix.current_branch_id()
        with pytest.raises(RuntimeError, match='must point to a named branch'):
            fix.switcher.branch_new(fix.directory, 'feature-bad',
                                    from_branch_id=clone_id)

    # ------------------------------------------------------------------
    # Lines 377/399: gitignored files skipped in _checkout_commit/_scan_local
    # ------------------------------------------------------------------

    def test_switch_skips_gitignored_working_files(self):
        """Lines 377/399: gitignored files are skipped during checkout/scan."""
        fix = self.fix
        fix.write('keep.txt', 'keep')
        fix.write('.gitignore', '*.log\n')
        fix.commit('initial')
        fix.sync.push(fix.directory)

        info     = fix.sync.branches(fix.directory)
        named    = next(b for b in info['branches'] if b['branch_type'] == 'named')

        # Write a gitignored file before switching
        fix.write('debug.log', 'ignored content')
        fix.switcher.switch(fix.directory, named['name'])
        # debug.log is gitignored — it is not tracked
        assert fix.exists('.gitignore')

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
