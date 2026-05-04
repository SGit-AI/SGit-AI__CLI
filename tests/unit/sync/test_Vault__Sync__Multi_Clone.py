"""Tests for multi-clone collaboration workflows.

These tests simulate two users (Alice and Bob) working on the same vault
via separate clones sharing a single in-memory API backend. This catches
bugs where pull/push only works within a single clone's local state.
"""
import os

import pytest

from sgit_ai.crypto.Vault__Crypto      import Vault__Crypto
from sgit_ai.crypto.PKI__Crypto        import PKI__Crypto
from sgit_ai.core.Vault__Sync          import Vault__Sync
from sgit_ai.api.Vault__API__In_Memory import Vault__API__In_Memory
from tests.unit.sync.vault_test_env    import Vault__Test_Env


class Test_Vault__Sync__Multi_Clone:
    """Two independent clones (Alice and Bob) sharing one remote API."""

    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_two_clones()

    @classmethod
    def teardown_class(cls):
        if cls._env:
            cls._env.cleanup_snapshot()

    def setup_method(self):
        self.env       = self._env.restore()
        self.crypto    = self.env.crypto
        self.api       = self.env.api
        self.alice_dir = self.env.alice_dir
        self.bob_dir   = self.env.bob_dir

    def teardown_method(self):
        self.env.cleanup()

    # ------------------------------------------------------------------ #
    # Basic push → pull between two clones
    # ------------------------------------------------------------------ #

    def test_alice_pushes_bob_pulls(self):
        """Alice adds a file and pushes; Bob pulls and sees it."""
        alice_dir  = self.alice_dir
        bob_dir    = self.bob_dir
        alice_sync = Vault__Sync(crypto=self.crypto, api=self.api)
        bob_sync   = Vault__Sync(crypto=self.crypto, api=self.api)

        # Alice commits and pushes
        with open(os.path.join(alice_dir, 'alice.txt'), 'w') as f:
            f.write('hello from alice')
        alice_sync.commit(alice_dir, message='alice adds file')
        push_result = alice_sync.push(alice_dir)
        assert push_result['status'] == 'pushed'

        # Bob pulls
        pull_result = bob_sync.pull(bob_dir)
        assert pull_result['status'] == 'merged'
        assert 'alice.txt' in pull_result['added']

        bob_file = os.path.join(bob_dir, 'alice.txt')
        assert os.path.isfile(bob_file)
        with open(bob_file) as f:
            assert f.read() == 'hello from alice'

    def test_bob_pushes_alice_pulls(self):
        """Reverse direction: Bob pushes, Alice pulls."""
        alice_dir  = self.alice_dir
        bob_dir    = self.bob_dir
        alice_sync = Vault__Sync(crypto=self.crypto, api=self.api)
        bob_sync   = Vault__Sync(crypto=self.crypto, api=self.api)

        # Bob commits and pushes
        with open(os.path.join(bob_dir, 'bob.txt'), 'w') as f:
            f.write('hello from bob')
        bob_sync.commit(bob_dir, message='bob adds file')
        push_result = bob_sync.push(bob_dir)
        assert push_result['status'] == 'pushed'

        # Alice pulls
        pull_result = alice_sync.pull(alice_dir)
        assert pull_result['status'] == 'merged'
        assert 'bob.txt' in pull_result['added']

        alice_file = os.path.join(alice_dir, 'bob.txt')
        assert os.path.isfile(alice_file)
        with open(alice_file) as f:
            assert f.read() == 'hello from bob'

    # ------------------------------------------------------------------ #
    # Round-trip: push → pull → push → pull
    # ------------------------------------------------------------------ #

    def test_round_trip_push_pull(self):
        """Alice pushes, Bob pulls, Bob pushes, Alice pulls."""
        alice_dir  = self.alice_dir
        bob_dir    = self.bob_dir
        alice_sync = Vault__Sync(crypto=self.crypto, api=self.api)
        bob_sync   = Vault__Sync(crypto=self.crypto, api=self.api)

        # Alice → push
        with open(os.path.join(alice_dir, 'round1.txt'), 'w') as f:
            f.write('round 1 from alice')
        alice_sync.commit(alice_dir, message='round 1')
        alice_sync.push(alice_dir)

        # Bob ← pull
        bob_sync.pull(bob_dir)
        assert os.path.isfile(os.path.join(bob_dir, 'round1.txt'))

        # Bob → push
        with open(os.path.join(bob_dir, 'round2.txt'), 'w') as f:
            f.write('round 2 from bob')
        bob_sync.commit(bob_dir, message='round 2')
        bob_sync.push(bob_dir)

        # Alice ← pull
        pull_result = alice_sync.pull(alice_dir)
        assert pull_result['status'] == 'merged'
        assert os.path.isfile(os.path.join(alice_dir, 'round2.txt'))
        with open(os.path.join(alice_dir, 'round2.txt')) as f:
            assert f.read() == 'round 2 from bob'

    # ------------------------------------------------------------------ #
    # Concurrent edits — non-conflicting
    # ------------------------------------------------------------------ #

    def test_concurrent_edits_no_conflict(self):
        """Both edit different files; push/pull merges cleanly."""
        alice_dir  = self.alice_dir
        bob_dir    = self.bob_dir
        alice_sync = Vault__Sync(crypto=self.crypto, api=self.api)
        bob_sync   = Vault__Sync(crypto=self.crypto, api=self.api)

        # Alice commits locally
        with open(os.path.join(alice_dir, 'alice_only.txt'), 'w') as f:
            f.write('alice content')
        alice_sync.commit(alice_dir, message='alice edit')
        alice_sync.push(alice_dir)

        # Bob commits locally (doesn't know about Alice's push yet)
        with open(os.path.join(bob_dir, 'bob_only.txt'), 'w') as f:
            f.write('bob content')
        bob_sync.commit(bob_dir, message='bob edit')

        # Bob pushes — should auto-pull Alice's changes and merge
        push_result = bob_sync.push(bob_dir)
        assert push_result['status'] == 'pushed'

        # Bob should now have both files
        assert os.path.isfile(os.path.join(bob_dir, 'alice_only.txt'))
        assert os.path.isfile(os.path.join(bob_dir, 'bob_only.txt'))

        # Alice pulls Bob's changes
        pull_result = alice_sync.pull(alice_dir)
        assert pull_result['status'] == 'merged'
        assert os.path.isfile(os.path.join(alice_dir, 'bob_only.txt'))

    # ------------------------------------------------------------------ #
    # Concurrent edits — conflicting
    # ------------------------------------------------------------------ #

    def test_concurrent_edits_with_conflict(self):
        """Both edit the same file; pull detects conflict."""
        alice_dir  = self.alice_dir
        bob_dir    = self.bob_dir
        alice_sync = Vault__Sync(crypto=self.crypto, api=self.api)
        bob_sync   = Vault__Sync(crypto=self.crypto, api=self.api)

        # Alice pushes her version
        with open(os.path.join(alice_dir, 'shared.txt'), 'w') as f:
            f.write('alice version')
        alice_sync.commit(alice_dir, message='alice edits shared')
        alice_sync.push(alice_dir)

        # Bob commits his version (diverged)
        with open(os.path.join(bob_dir, 'shared.txt'), 'w') as f:
            f.write('bob version')
        bob_sync.commit(bob_dir, message='bob edits shared')

        # Bob pulls — should detect conflict
        pull_result = bob_sync.pull(bob_dir)
        assert pull_result['status'] == 'conflicts'
        assert 'shared.txt' in pull_result['conflicts']

    # ------------------------------------------------------------------ #
    # Pull when already up to date (after a full round-trip)
    # ------------------------------------------------------------------ #

    def test_pull_after_push_is_up_to_date(self):
        """After Alice pushes and Bob pulls, Bob's next pull is up to date."""
        alice_dir  = self.alice_dir
        bob_dir    = self.bob_dir
        alice_sync = Vault__Sync(crypto=self.crypto, api=self.api)
        bob_sync   = Vault__Sync(crypto=self.crypto, api=self.api)

        # Alice pushes
        with open(os.path.join(alice_dir, 'file.txt'), 'w') as f:
            f.write('content')
        alice_sync.commit(alice_dir, message='add file')
        alice_sync.push(alice_dir)

        # Bob pulls
        bob_sync.pull(bob_dir)

        # Bob pulls again — should be up to date
        result = bob_sync.pull(bob_dir)
        assert result['status'] == 'up_to_date'
        assert result['message'] == 'Already up to date'

    # ------------------------------------------------------------------ #
    # Multiple files over multiple rounds
    # ------------------------------------------------------------------ #

    def test_multi_round_multi_file(self):
        """Several rounds of push/pull with multiple files each time."""
        alice_dir  = self.alice_dir
        bob_dir    = self.bob_dir
        alice_sync = Vault__Sync(crypto=self.crypto, api=self.api)
        bob_sync   = Vault__Sync(crypto=self.crypto, api=self.api)

        # Round 1: Alice pushes 3 files
        for i in range(3):
            with open(os.path.join(alice_dir, f'a{i}.txt'), 'w') as f:
                f.write(f'alice file {i}')
        alice_sync.commit(alice_dir, message='alice batch 1')
        alice_sync.push(alice_dir)

        # Bob pulls round 1
        bob_sync.pull(bob_dir)
        for i in range(3):
            assert os.path.isfile(os.path.join(bob_dir, f'a{i}.txt'))

        # Round 2: Bob pushes 2 files
        for i in range(2):
            with open(os.path.join(bob_dir, f'b{i}.txt'), 'w') as f:
                f.write(f'bob file {i}')
        bob_sync.commit(bob_dir, message='bob batch 1')
        bob_sync.push(bob_dir)

        # Alice pulls round 2
        alice_sync.pull(alice_dir)
        for i in range(2):
            assert os.path.isfile(os.path.join(alice_dir, f'b{i}.txt'))

        # Both should have all 5 files
        for name in ['a0.txt', 'a1.txt', 'a2.txt', 'b0.txt', 'b1.txt']:
            assert os.path.isfile(os.path.join(alice_dir, name))
            assert os.path.isfile(os.path.join(bob_dir, name))

    # ------------------------------------------------------------------ #
    # File deletion propagation
    # ------------------------------------------------------------------ #

    def test_delete_propagates_across_clones(self):
        """Alice adds a file, pushes; Bob pulls, deletes it, pushes; Alice pulls."""
        alice_dir  = self.alice_dir
        bob_dir    = self.bob_dir
        alice_sync = Vault__Sync(crypto=self.crypto, api=self.api)
        bob_sync   = Vault__Sync(crypto=self.crypto, api=self.api)

        # Alice adds file and pushes
        with open(os.path.join(alice_dir, 'doomed.txt'), 'w') as f:
            f.write('will be deleted')
        alice_sync.commit(alice_dir, message='add doomed')
        alice_sync.push(alice_dir)

        # Bob pulls, then deletes the file
        bob_sync.pull(bob_dir)
        assert os.path.isfile(os.path.join(bob_dir, 'doomed.txt'))
        os.remove(os.path.join(bob_dir, 'doomed.txt'))
        bob_sync.commit(bob_dir, message='delete doomed')
        bob_sync.push(bob_dir)

        # Alice pulls — file should be gone
        pull_result = alice_sync.pull(alice_dir)
        assert pull_result['status'] == 'merged'
        assert not os.path.isfile(os.path.join(alice_dir, 'doomed.txt'))

    # ------------------------------------------------------------------ #
    # File modification propagation
    # ------------------------------------------------------------------ #

    def test_modification_propagates_across_clones(self):
        """Alice adds a file, pushes; Bob pulls, modifies it, pushes; Alice pulls."""
        alice_dir  = self.alice_dir
        bob_dir    = self.bob_dir
        alice_sync = Vault__Sync(crypto=self.crypto, api=self.api)
        bob_sync   = Vault__Sync(crypto=self.crypto, api=self.api)

        # Alice adds file and pushes
        with open(os.path.join(alice_dir, 'shared.txt'), 'w') as f:
            f.write('version 1')
        alice_sync.commit(alice_dir, message='add shared')
        alice_sync.push(alice_dir)

        # Bob pulls first to get Alice's file, then modifies and pushes
        pull1 = bob_sync.pull(bob_dir)
        assert pull1['status'] == 'merged'
        assert os.path.isfile(os.path.join(bob_dir, 'shared.txt'))

        with open(os.path.join(bob_dir, 'shared.txt'), 'w') as f:
            f.write('version 2 by bob')
        bob_sync.commit(bob_dir, message='modify shared')
        bob_sync.push(bob_dir)

        # Alice pulls — should see Bob's version
        pull_result = alice_sync.pull(alice_dir)
        assert pull_result['status'] == 'merged'
        with open(os.path.join(alice_dir, 'shared.txt')) as f:
            assert f.read() == 'version 2 by bob'
