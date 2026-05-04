"""Tests for remote API failure scenarios during pull and push.

These tests verify that Vault__Sync behaves correctly when the remote API
is unreachable, returns errors, or fails selectively. This catches bugs
where pull/push silently uses stale local data instead of warning the user.
"""
import copy
import os
import shutil
import tempfile

import pytest

from sgit_ai.crypto.Vault__Crypto      import Vault__Crypto
from sgit_ai.crypto.PKI__Crypto        import PKI__Crypto
from sgit_ai.core.Vault__Sync          import Vault__Sync
from sgit_ai.api.Vault__API__In_Memory import Vault__API__In_Memory


class Vault__API__Failing(Vault__API__In_Memory):
    """API that can be configured to fail on specific operations."""

    def setup(self):
        super().setup()
        self._fail_reads    = False
        self._fail_writes   = False
        self._fail_on_prefix = None   # fail only when file_id contains this
        self._call_log       = []
        return self

    def read(self, vault_id: str, file_id: str) -> bytes:
        self._call_log.append(('read', vault_id, file_id))
        if self._fail_reads:
            if self._fail_on_prefix is None or self._fail_on_prefix in file_id:
                raise RuntimeError('Simulated network error: connection refused')
        return super().read(vault_id, file_id)

    def write(self, vault_id: str, file_id: str, write_key: str, payload: bytes) -> dict:
        self._call_log.append(('write', vault_id, file_id))
        if self._fail_writes:
            if self._fail_on_prefix is None or self._fail_on_prefix in file_id:
                raise RuntimeError('Simulated network error: connection refused')
        return super().write(vault_id, file_id, write_key, payload)


class Test_Vault__Sync__Remote_Failure:

    # ------------------------------------------------------------------ #
    # Class-level snapshot state
    # ------------------------------------------------------------------ #
    _snapshot_dir   = None
    _snapshot_store = None
    _vault_sub      = 'vault'

    @classmethod
    def setup_class(cls):
        """Create a vault, commit, push once; snapshot directory + API state."""
        crypto = Vault__Crypto()
        api    = Vault__API__Failing()
        api.setup()
        sync   = Vault__Sync(crypto=crypto, api=api)

        snap_dir  = tempfile.mkdtemp()
        directory = os.path.join(snap_dir, cls._vault_sub)

        sync.init(directory)
        with open(os.path.join(directory, 'initial.txt'), 'w') as f:
            f.write('initial content')
        sync.commit(directory, message='initial commit')
        sync.push(directory)

        cls._snapshot_dir   = snap_dir
        cls._snapshot_store = copy.deepcopy(api._store)

    @classmethod
    def teardown_class(cls):
        if cls._snapshot_dir and os.path.isdir(cls._snapshot_dir):
            shutil.rmtree(cls._snapshot_dir, ignore_errors=True)

    def setup_method(self):
        self.tmp_dir = tempfile.mkdtemp()

        # Copy the snapshot vault directory
        src = os.path.join(self._snapshot_dir, self._vault_sub)
        dst = os.path.join(self.tmp_dir, self._vault_sub)
        shutil.copytree(src, dst)

        # Restore API state into a fresh Vault__API__Failing
        self.api = Vault__API__Failing()
        self.api.setup()
        self.api._store = copy.deepcopy(self._snapshot_store)

        self.crypto = Vault__Crypto()
        self.sync   = Vault__Sync(crypto=self.crypto, api=self.api)
        self._directory = dst

    def teardown_method(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def _init_and_push(self, name='vault'):
        """Return the pre-init'd vault directory (already done in setup_class)."""
        if name == 'vault':
            return self._directory
        # For Alice/Bob tests, create a fresh vault in tmp_dir
        directory = os.path.join(self.tmp_dir, name)
        self.sync.init(directory)
        with open(os.path.join(directory, 'initial.txt'), 'w') as f:
            f.write('initial content')
        self.sync.commit(directory, message='initial commit')
        self.sync.push(directory)
        return directory

    # ------------------------------------------------------------------ #
    # Pull with remote ref fetch failure
    # ------------------------------------------------------------------ #

    def test_pull_remote_unreachable_returns_warning(self):
        """When remote ref fetch fails, pull should return remote_unreachable flag."""
        directory = self._directory

        # Break the remote — refs reads will fail
        self.api._fail_reads    = True
        self.api._fail_on_prefix = 'refs/'

        result = self.sync.pull(directory)
        assert result['status'] == 'up_to_date'
        assert result.get('remote_unreachable') is True
        assert 'remote_error' in result

    def test_pull_remote_unreachable_does_not_silently_succeed(self):
        """Pull must NOT return a clean 'Already up to date' when remote is down."""
        directory = self._directory

        self.api._fail_reads     = True
        self.api._fail_on_prefix = 'refs/'

        result = self.sync.pull(directory)
        # The critical assertion: it should NOT say "Already up to date" cleanly
        if result['status'] == 'up_to_date':
            assert result.get('remote_unreachable') is True, \
                'Pull reported up_to_date without checking remote — stale data bug!'

    def test_pull_remote_all_reads_fail(self):
        """When ALL reads fail, pull should handle gracefully."""
        directory = self._directory

        self.api._fail_reads = True  # all reads fail

        result = self.sync.pull(directory)
        # Should either return remote_unreachable or raise — not silently succeed
        if result['status'] == 'up_to_date':
            assert result.get('remote_unreachable') is True

    # ------------------------------------------------------------------ #
    # Pull with stale local data after remote diverges
    # ------------------------------------------------------------------ #

    def test_pull_detects_remote_divergence(self):
        """Two-clone scenario: Alice pushes, Bob's pull detects the change."""
        # Set up Alice and Bob sharing the same API
        alice_dir = os.path.join(self.tmp_dir, 'alice')
        self.sync.init(alice_dir)
        vault_key = open(os.path.join(alice_dir, '.sg_vault', 'local', 'vault_key')).read().strip()
        with open(os.path.join(alice_dir, 'init.txt'), 'w') as f:
            f.write('init')
        self.sync.commit(alice_dir, message='initial commit')
        self.sync.push(alice_dir)

        bob_dir = os.path.join(self.tmp_dir, 'bob')
        bob_sync = Vault__Sync(crypto=self.crypto, api=self.api)
        bob_sync.clone(vault_key, bob_dir)

        # Alice pushes a change
        with open(os.path.join(alice_dir, 'new.txt'), 'w') as f:
            f.write('alice was here')
        self.sync.commit(alice_dir, message='alice change')
        self.sync.push(alice_dir)

        # Bob pulls — must NOT get "up to date"
        result = bob_sync.pull(bob_dir)
        assert result['status'] == 'merged', \
            f'Expected merged but got {result["status"]}: {result.get("message")}'
        assert os.path.isfile(os.path.join(bob_dir, 'new.txt'))

    def test_pull_with_failed_remote_after_divergence(self):
        """Alice pushes but Bob's remote fetch fails — Bob should see remote_unreachable."""
        alice_dir = os.path.join(self.tmp_dir, 'alice')
        self.sync.init(alice_dir)
        vault_key = open(os.path.join(alice_dir, '.sg_vault', 'local', 'vault_key')).read().strip()
        with open(os.path.join(alice_dir, 'init.txt'), 'w') as f:
            f.write('init')
        self.sync.commit(alice_dir, message='initial commit')
        self.sync.push(alice_dir)

        bob_dir = os.path.join(self.tmp_dir, 'bob')
        bob_sync = Vault__Sync(crypto=self.crypto, api=self.api)
        bob_sync.clone(vault_key, bob_dir)

        # Alice pushes a change
        with open(os.path.join(alice_dir, 'diverged.txt'), 'w') as f:
            f.write('alice diverges')
        self.sync.commit(alice_dir, message='alice diverges')
        self.sync.push(alice_dir)

        # Break remote for Bob — only ref reads fail
        self.api._fail_reads     = True
        self.api._fail_on_prefix = 'refs/'

        # Bob pulls — remote has diverged but Bob can't fetch the ref
        result = bob_sync.pull(bob_dir)
        # Should warn about remote unreachable, not silently claim up-to-date
        assert result.get('remote_unreachable') is True or result['status'] == 'merged', \
            f'Pull silently succeeded with stale data: {result}'

    # ------------------------------------------------------------------ #
    # Push with remote failure
    # ------------------------------------------------------------------ #

    def test_push_with_write_failure_raises(self):
        """Push should fail clearly when writes to remote fail."""
        directory = self._directory

        with open(os.path.join(directory, 'new.txt'), 'w') as f:
            f.write('new content')
        self.sync.commit(directory, message='add new file')

        self.api._fail_writes = True

        with pytest.raises(Exception):
            self.sync.push(directory)

    # ------------------------------------------------------------------ #
    # Verify API call logging
    # ------------------------------------------------------------------ #

    def test_pull_actually_calls_remote_api(self):
        """Verify that pull makes at least one API read call for the remote ref."""
        directory = self._directory
        self.api._call_log.clear()

        self.sync.pull(directory)

        read_calls = [c for c in self.api._call_log if c[0] == 'read']
        ref_reads  = [c for c in read_calls if 'refs/' in c[2]]
        assert len(ref_reads) > 0, \
            'Pull did not make any API read calls for remote refs!'
