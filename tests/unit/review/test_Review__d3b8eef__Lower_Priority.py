"""Review of dev at d3b8eef — the lower-priority items.

- push on a rewound branch said "Nothing to push"; branch switch exited 0 when its
  follow-up pull was refused
- a commit that only modifies files reported "Committed 0 file(s)"
- `tag create` without the clone's signing key said "the vault may be corrupted"
"""
import os

import pytest

from sgit_ai.core.Vault__Errors                       import Vault__Tag_Error
from sgit_ai.core.actions.branch.Vault__Branch_Switch import Vault__Branch_Switch
from tests._helpers.vault_adversary                   import Vault__Adversary
from tests._helpers.vault_test_env                    import Vault__Test_Env


def _write(d, rel, content):
    with open(os.path.join(d, rel), 'w') as f:
        f.write(content)


class Test_Review__d3b8eef__Lower_Priority:

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

    def _bob_accepted_v2_then_rewound(self):
        _write(self.s.alice_dir, 'policy.md', 'v2')
        self.s.sync.commit(self.s.alice_dir, 'v2')
        self.s.sync.push(self.s.alice_dir)
        self.s.sync.pull(self.s.bob_dir)
        adv = Vault__Adversary(self.s.api, self.s.vault_key)
        try:
            adv.move_branch(adv.named_branch(), self.s.commit_id)
        finally:
            adv.cleanup()

    def test_push_on_a_rewound_branch_says_so(self):
        self._bob_accepted_v2_then_rewound()
        assert self.s.sync.push(self.s.bob_dir)['status'] == 'rewound'

    def test_push_when_a_teammate_pushed_says_behind(self):
        _write(self.s.alice_dir, 'policy.md', 'v2')
        self.s.sync.commit(self.s.alice_dir, 'v2')
        self.s.sync.push(self.s.alice_dir)
        assert self.s.sync.push(self.s.bob_dir)['status'] == 'behind'

    def test_switch_marks_a_refused_pull(self):
        self._bob_accepted_v2_then_rewound()
        Vault__Branch_Switch(crypto=self.s.crypto).branch_new(self.s.bob_dir, 'side')
        result = self.s.sync.switch_branch(self.s.bob_dir, 'current')
        assert result['pull'].get('refused') is True

    def test_a_commit_that_only_modifies_counts_its_files(self):
        _write(self.s.alice_dir, 'policy.md', 'v2')
        assert self.s.sync.commit(self.s.alice_dir, 'v2')['files_changed'] == 1

    def test_tag_create_without_the_signing_key_says_what_is_missing(self):
        local = os.path.join(self.s.alice_dir, '.sg_vault', 'local')
        for name in os.listdir(local):
            if name.endswith('.pem'):
                os.remove(os.path.join(local, name))
        with pytest.raises(Vault__Tag_Error, match='no private signing key'):
            self.s.sync.tag_create(self.s.alice_dir, 'v1.0', self.s.commit_id)
