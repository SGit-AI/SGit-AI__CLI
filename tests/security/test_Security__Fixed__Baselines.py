"""Fixed after the 00d6fc1 review — the lease and rewind baselines (review B2, B3).

The baseline is the last remote head a clone ACCEPTED for a named branch. Before:
one baseline per clone, refreshed by `sgit status` (so a lease taken after a status
was satisfied by the very push it should refuse), skipped on `branch merge`, and
rebuilt by `branch switch` from a local ref that an unguarded merge had moved (so a
rewind passed through a branch round trip, and a push put the removed commit back).
Now: one baseline per named branch, moved only by a guarded pull or merge, an
accepted rewind, or the clone's own push. Threat model: TM-F11, TM-F12.
"""
import json
import os

import pytest

from sgit_ai.core.Vault__Errors                       import Vault__Push_Lease_Error, Vault__Ref_Rewind_Error
from sgit_ai.core.actions.branch.Vault__Branch_Switch import Vault__Branch_Switch
from tests._helpers.vault_adversary                   import Vault__Adversary
from tests._helpers.vault_test_env                    import Vault__Test_Env


def _write(path: str, content: str) -> None:
    with open(path, 'w') as f:
        f.write(content)


class Test_Fixed__Baselines:

    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_two_clones(files={'policy.md': 'v1'})

    @classmethod
    def teardown_class(cls):
        cls._env.cleanup_snapshot()

    def setup_method(self):
        self.s = self._env.restore()

    def teardown_method(self):
        self.s.cleanup()

    def _commit(self, d, content, msg):
        _write(os.path.join(d, 'policy.md'), content)
        return self.s.sync.commit(d, msg)['commit_id']

    def _server_head(self) -> str:
        adv = Vault__Adversary(self.s.api, self.s.vault_key)
        try:
            return adv.head_of(adv.named_branch())
        finally:
            adv.cleanup()

    def test_B2__status_does_not_satisfy_the_lease(self):
        bob_commit = self._commit(self.s.bob_dir, 'bob', 'bob')
        self.s.sync.push(self.s.bob_dir)
        self._commit(self.s.alice_dir, 'alice', 'alice')
        assert self.s.sync.status(self.s.alice_dir)['push_status'] in ('diverged', 'behind')   # observing the server
        with pytest.raises(Vault__Push_Lease_Error):
            self.s.sync.push(self.s.alice_dir, force=True, lease='')
        assert self._server_head() == bob_commit

    def _rewind_after_bob_accepted_v2(self):
        self._commit(self.s.alice_dir, 'v2', 'v2')
        self.s.sync.push(self.s.alice_dir)
        self.s.sync.pull(self.s.bob_dir)                                     # bob accepts v2
        adv = Vault__Adversary(self.s.api, self.s.vault_key)
        try:
            adv.move_branch(adv.named_branch(), self.s.commit_id)            # a teammate rewinds current to v1
        finally:
            adv.cleanup()

    def test_B3__branch_merge_from_a_rewound_branch_is_refused(self):
        self._rewind_after_bob_accepted_v2()
        Vault__Branch_Switch(crypto=self.s.crypto).branch_new(self.s.bob_dir, 'side')
        with pytest.raises(Vault__Ref_Rewind_Error):
            self.s.sync.merge_branch(self.s.bob_dir, 'current')

    def test_B3__a_switch_round_trip_does_not_launder_a_rewind(self):
        self._rewind_after_bob_accepted_v2()
        switch = Vault__Branch_Switch(crypto=self.s.crypto)
        switch.branch_new(self.s.bob_dir, 'side')
        try:                                                                 # the reviewer's sequence: merge current
            self.s.sync.merge_branch(self.s.bob_dir, 'current')             # (now refused), then switch back
        except Vault__Ref_Rewind_Error:
            pass
        switch.switch(self.s.bob_dir, 'current')
        with pytest.raises(Vault__Ref_Rewind_Error):
            self.s.sync.pull(self.s.bob_dir)
        try:
            self.s.sync.push(self.s.bob_dir)                                 # refused, or nothing to push ...
        except Vault__Ref_Rewind_Error:
            pass
        assert self._server_head() == self.s.commit_id                       # ... it never resurrects the removed commit

    def test_a_clone_from_before_per_branch_baselines_keeps_its_baseline(self):
        self._rewind_after_bob_accepted_v2()
        local = os.path.join(self.s.bob_dir, '.sg_vault', 'local')
        with open(os.path.join(local, 'remote_heads.json')) as f:
            accepted = list(json.load(f).values())[0]
        os.remove(os.path.join(local, 'remote_heads.json'))                 # what an older clone has: the single field
        with open(os.path.join(local, 'config.json')) as f:
            cfg = json.load(f)
        cfg['last_remote_head'] = accepted
        with open(os.path.join(local, 'config.json'), 'w') as f:
            json.dump(cfg, f)
        switch = Vault__Branch_Switch(crypto=self.s.crypto)
        switch.branch_new(self.s.bob_dir, 'side')                           # migrates before the tracked branch changes
        switch.switch(self.s.bob_dir, 'current')
        with pytest.raises(Vault__Ref_Rewind_Error):
            self.s.sync.pull(self.s.bob_dir)

    def test_a_forward_move_after_status_still_pulls(self):
        self._commit(self.s.alice_dir, 'v2', 'v2')
        self.s.sync.push(self.s.alice_dir)
        self.s.sync.status(self.s.bob_dir)
        self.s.sync.pull(self.s.bob_dir)
        with open(os.path.join(self.s.bob_dir, 'policy.md')) as f:
            assert f.read() == 'v2'
