"""Fixed in 0.21.0 — nothing writes a local named ref or a baseline except verify-then-accept
(review d3b8eef N2, N3).

N2: switching to a never-fetched branch wrote its server head into the local ref with
no signature or rewind check; the pull after the switch then saw named == clone and
skipped the policy. N3: a writable pull wrote the server's ref before the policy ran,
and status wrote it with no check at all, so a refused pull (or a status) followed by a
switch round trip checked the unsigned head out; on a read-only clone a status between
two pulls got past the K2 fix.

Threat model: TM-F12.
"""
import os

import pytest

from sgit_ai.core.Vault__Errors                       import Vault__Signature_Error
from sgit_ai.core.actions.branch.Vault__Branch_Switch import Vault__Branch_Switch
from tests._helpers.vault_adversary                   import Vault__Adversary
from tests._helpers.vault_test_env                    import Vault__Test_Env


def _read(path: str) -> str:
    with open(path) as f:
        return f.read()


def _write(path: str, content: str) -> None:
    with open(path, 'w') as f:
        f.write(content)


class Test_Fixed__Verify_Then_Accept:

    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_two_clones(files={'policy.md': 'pay alice'})

    @classmethod
    def teardown_class(cls):
        cls._env.cleanup_snapshot()

    def setup_method(self):
        self.s        = self._env.restore()
        self.sync     = self.s.sync
        self.alice    = self.s.alice_dir
        self.bob      = self.s.bob_dir
        self.branches = Vault__Branch_Switch(crypto=self.s.crypto)
        self.adv      = None

    def teardown_method(self):
        if self.adv:
            self.adv.cleanup()
        self.s.cleanup()

    def _policy_on(self):
        self.sync.set_format(self.alice, add_features=['signatures-required'])
        self.sync.pull(self.bob)

    def _forge(self, branch: str = 'current') -> str:
        self.adv = self.adv or Vault__Adversary(self.s.api, self.s.vault_key)
        self.adv.pull_host()
        named  = self.adv.named_branch(branch)
        forged = self.adv.forge_commit({'policy.md': b'pay mallory'}, parent=self.adv.head_of(named),
                                       branch_id=str(named.branch_id), sign=False)
        self.adv.move_branch(named, forged)
        return forged

    def _round_trip(self, d):
        self.branches.branch_new(d, 'x')
        self.sync.switch_branch(d, 'current')

    def _local_named_head(self, d, name='current'):
        c     = self.sync._init_components(d)
        index = c.branch_manager.load_branch_index(d, c.branch_index_file_id, c.read_key)
        meta  = c.branch_manager.get_branch_by_name(index, name)
        return c.ref_manager.read_ref(str(meta.head_ref_id), c.read_key) if meta else None

    def test_N2__switch_to_a_never_fetched_branch_refuses_an_unsigned_head(self):
        self.branches.branch_new(self.alice, 'feature')
        _write(os.path.join(self.alice, 'f.md'), 'feature')
        self.sync.commit(self.alice, 'feature')
        self.sync.push(self.alice)
        self.sync.switch_branch(self.alice, 'current')
        self._policy_on()
        self._forge('feature')

        with pytest.raises(Vault__Signature_Error):
            self.sync.switch_branch(self.bob, 'feature')
        assert _read(os.path.join(self.bob, 'policy.md')) == 'pay alice'
        assert self._local_named_head(self.bob, 'feature') is None          # nothing written

    def test_N2__a_signed_never_fetched_branch_still_switches(self):
        self.branches.branch_new(self.alice, 'feature')
        _write(os.path.join(self.alice, 'f.md'), 'feature')
        self.sync.commit(self.alice, 'feature')
        self.sync.push(self.alice)
        self._policy_on()
        self.sync.switch_branch(self.bob, 'feature')
        assert _read(os.path.join(self.bob, 'f.md')) == 'feature'

    def test_N3__a_refused_pull_leaves_no_local_ref_for_a_switch_to_check_out(self):
        self._policy_on()
        before = self._local_named_head(self.bob)
        self._forge()
        with pytest.raises(Vault__Signature_Error):
            self.sync.pull(self.bob)
        assert self._local_named_head(self.bob) == before
        self._round_trip(self.bob)
        assert _read(os.path.join(self.bob, 'policy.md')) == 'pay alice'
        with pytest.raises(Vault__Signature_Error):
            self.sync.pull(self.bob)                                          # still refused afterwards

    def test_N3__status_writes_no_ref(self):
        self._policy_on()
        before = self._local_named_head(self.bob)
        self._forge()
        self.sync.status(self.bob)
        assert self._local_named_head(self.bob) == before
        self._round_trip(self.bob)
        assert _read(os.path.join(self.bob, 'policy.md')) == 'pay alice'
        with pytest.raises(Vault__Signature_Error):
            self.sync.pull(self.bob)

    def test_N3__status_between_read_only_pulls_does_not_get_past_the_policy(self):
        keys = self.s.crypto.derive_keys_from_vault_key(self.s.vault_key)
        ro   = os.path.join(self.s.tmp_dir, 'reader')
        self.sync.clone_read_only(keys['vault_id'], keys['read_key'], ro)
        self._policy_on()
        self.sync.pull_read_only(ro)
        self._forge()
        with pytest.raises(Vault__Signature_Error):
            self.sync.pull_read_only(ro)
        self.sync.status(ro)
        with pytest.raises(Vault__Signature_Error):
            self.sync.pull_read_only(ro)
        assert _read(os.path.join(ro, 'policy.md')) == 'pay alice'

    def test_a_good_pull_still_accepts_and_status_still_counts(self):
        _write(os.path.join(self.alice, 'policy.md'), 'pay alice v2')
        self.sync.commit(self.alice, 'v2')
        self.sync.push(self.alice)
        assert self.sync.status(self.bob)['push_status'] == 'behind'
        self.sync.pull(self.bob)
        assert _read(os.path.join(self.bob, 'policy.md')) == 'pay alice v2'
        assert self.sync.status(self.bob)['push_status'] == 'up_to_date'

    def test_L2__re_enabling_the_policy_does_not_lock_out_a_clone_that_missed_the_off_period(self):
        """TM-R30's remedy: the owner turns the policy off, an old client commits unsigned,
        the owner turns it on again (the new start covers that commit). A clone that did
        not pull in between used to keep its pinned older start and refuse every pull."""
        self._policy_on()
        _write(os.path.join(self.alice, 'signed.md'), 'signed under the policy')
        self.sync.commit(self.alice, 'signed')
        self.sync.push(self.alice)
        self.sync.pull(self.bob)                                              # bob's first pull under the policy
        self.sync.set_format(self.alice, remove_features=['signatures-required'])
        self._forge()                                                         # the old client's unsigned commit
        self.sync.pull(self.alice)
        self.sync.set_format(self.alice, add_features=['signatures-required'])
        self.sync.pull(self.bob)
        assert _read(os.path.join(self.bob, 'policy.md')) == 'pay mallory'
