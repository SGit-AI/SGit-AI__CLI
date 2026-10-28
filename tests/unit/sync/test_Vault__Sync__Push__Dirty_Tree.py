"""Push with uncommitted changes (Git-parity 2.3 prerequisite, design__03 §5.4).

Push no longer refuses a dirty working copy. Its implicit pull still protects it: an
uncommitted edit the incoming commits do not touch is carried over; one they would
change refuses the pull, and so the push, before anything is written."""
import os

import pytest

from sgit_ai.core.Vault__Errors           import Vault__Dirty_Working_Tree_Error
from tests.unit.sync.vault_test_env       import Vault__Test_Env


class Test_Vault__Sync__Push__Dirty_Tree:

    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_two_clones(files={'shared.txt': 'base\n', 'alice-only.txt': 'a\n'})

    def setup_method(self):
        self.env   = self._env.restore()
        self.sync  = self.env.sync
        self.alice = self.env.alice_dir
        self.bob   = self.env.bob_dir

    def teardown_method(self):
        self.env.cleanup()

    def write(self, directory, rel, text):
        with open(os.path.join(directory, rel), 'w') as f:
            f.write(text)

    def read(self, directory, rel):
        with open(os.path.join(directory, rel)) as f:
            return f.read()

    def test_a_dirty_file_the_incoming_commits_do_not_touch_is_kept_and_the_push_goes_through(self):
        self.write(self.alice, 'alice-only.txt', 'alice 2\n')
        self.sync.commit(self.alice, message='alice')
        self.sync.push(self.alice)
        self.write(self.bob, 'bob.txt', 'bob\n')
        self.sync.commit(self.bob, message='bob')
        self.write(self.bob, 'shared.txt', 'bob is still editing\n')            # uncommitted
        assert self.sync.push(self.bob)['status'] == 'pushed'
        assert self.read(self.bob, 'shared.txt') == 'bob is still editing\n'
        assert self.read(self.bob, 'alice-only.txt') == 'alice 2\n'

    def test_a_dirty_file_the_pull_would_change_refuses_before_anything_is_written(self):
        self.write(self.alice, 'shared.txt', 'alice changed it\n')
        self.sync.commit(self.alice, message='alice')
        self.sync.push(self.alice)
        self.write(self.bob, 'bob.txt', 'bob\n')
        self.sync.commit(self.bob, message='bob')
        head = self.sync.resolve_revision(self.bob, 'HEAD')
        self.write(self.bob, 'shared.txt', 'bob is still editing\n')
        with pytest.raises(Vault__Dirty_Working_Tree_Error):
            self.sync.push(self.bob)
        assert self.read(self.bob, 'shared.txt') == 'bob is still editing\n'
        assert self.sync.resolve_revision(self.bob, 'HEAD') == head
