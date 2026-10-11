"""Fixed in 0.21.1 — three answers a host could give that the client took as control.

Threat model: TM-F33 (an empty batch reply counted as a successful push), TM-F34 (an empty
listing made a clone that had already synced re-upload its stale refs with no compare-and-swap),
TM-F35 (a garbled branch index on clone degraded to a policy-less index). All three were found by
the round-1 tool-assisted review: the host-boundary dossier (`review/findings/audit-context-host.json`
AC-H-001, AC-H-003) and the verify-then-accept dossier (`audit-context-verify.json` AC-V-001),
then reproduced with the lying hosts below. The host is A1 alone: no read key is needed to
answer `{}`, `[]` or random bytes.

Each `Host__*` is a real Vault__API__In_Memory over the test vault's own store, differing in
one answer. Every attack test fails on the code before the fix; the controls pass on both.
"""
import os

import pytest

from sgit_ai.network.api.Vault__API__In_Memory import Vault__API__In_Memory
from tests._helpers.vault_test_env             import Vault__Test_Env


class Host__Empty_Reply(Vault__API__In_Memory):
    """Acknowledges a batch, a write or a delete with an empty body and writes nothing."""
    def batch(self, vault_id, write_key, operations):
        return {}
    def write(self, vault_id, file_id, write_key, payload):
        return {}
    def delete(self, vault_id, file_id, write_key):
        return {}


class Host__Empty_Listing(Vault__API__In_Memory):
    """Lists no files for any prefix, whatever it holds."""
    def list_files(self, vault_id, prefix=''):
        return []


def _write(directory, name, text):
    with open(os.path.join(directory, name), 'w') as f:
        f.write(text)


def _lying(cls, snapshot):
    host = cls(); host.setup(); host._store = snapshot.api._store
    return host


class Test_Fixed__Empty_Batch_Reply:

    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_two_clones(files={'a.md': 'v1'})

    @classmethod
    def teardown_class(cls):
        cls._env.cleanup_snapshot()

    def setup_method(self):
        self.s = self._env.restore()

    def teardown_method(self):
        self.s.cleanup()

    def test_TM_F33__a_push_the_host_acknowledged_with_nothing_is_not_pushed(self):
        """Before: push returned status 'pushed' (objects_uploaded 1) although the host
        wrote nothing; the next clone would never see the commit."""
        _write(self.s.alice_dir, 'a.md', 'v2'); self.s.sync.commit(self.s.alice_dir, 'v2')
        self.s.sync.api = _lying(Host__Empty_Reply, self.s)
        with pytest.raises(RuntimeError, match='did not accept|did not answer|results'):
            self.s.sync.push(self.s.alice_dir)

    def test_control__an_honest_host_pushes(self):
        _write(self.s.alice_dir, 'a.md', 'v2'); self.s.sync.commit(self.s.alice_dir, 'v2')
        assert self.s.sync.push(self.s.alice_dir)['status'] == 'pushed'


class Test_Fixed__Empty_Listing_After_Sync:

    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_two_clones(files={'a.md': 'v1'})

    @classmethod
    def teardown_class(cls):
        cls._env.cleanup_snapshot()

    def setup_method(self):
        self.s = self._env.restore()
        _write(self.s.alice_dir, 'a.md', 'alice-v2'); self.s.sync.commit(self.s.alice_dir, 'alice v2')
        self.s.sync.push(self.s.alice_dir)
        self.ref_keys = [k for k in self.s.api._store if '/bare/refs/' in k]
        self.before   = {k: self.s.api._store[k] for k in self.ref_keys}

    def teardown_method(self):
        self.s.cleanup()

    def test_TM_F34__a_clone_that_has_synced_refuses_to_resync_over_an_empty_listing(self):
        """Before: Bob (behind Alice) was told the vault was empty, took it for a first push,
        and plain-wrote his stale refs over the host's: the shared branch rewound to Bob's
        head, authored by a legitimate key."""
        _write(self.s.bob_dir, 'b.md', 'bob'); self.s.sync.commit(self.s.bob_dir, 'bob, never pulled alice')
        self.s.sync.api = _lying(Host__Empty_Listing, self.s)
        with pytest.raises(RuntimeError, match='lists no files|already synced|refusing'):
            self.s.sync.push(self.s.bob_dir)
        assert {k: self.s.api._store.get(k) for k in self.ref_keys} == self.before

    def test_control__an_honest_listing_lets_bob_pull_then_push(self):
        _write(self.s.bob_dir, 'b.md', 'bob'); self.s.sync.commit(self.s.bob_dir, 'bob')
        assert self.s.sync.push(self.s.bob_dir)['status'] == 'pushed'


class Test_Fixed__Garbled_Index_On_Clone:

    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_two_clones(files={'policy.md': 'pay alice'})

    @classmethod
    def teardown_class(cls):
        cls._env.cleanup_snapshot()

    def setup_method(self):
        self.s = self._env.restore()
        self.s.sync.set_format(self.s.alice_dir, add_features=['signatures-required'])
        c = self.s.sync._init_components(self.s.alice_dir)
        self.index_key = [k for k in self.s.api._store if k.endswith(str(c.branch_index_file_id))][0]
        self.new_dir   = os.path.join(self.s.tmp_dir, 'newcomer')

    def teardown_method(self):
        self.s.cleanup()

    def test_TM_F35__an_index_that_is_present_but_unreadable_refuses_the_clone(self):
        """Before: the clone 'degraded' to a synthesised single-branch index with no features,
        so the newcomer ran with signatures-required off for a vault that had it on."""
        self.s.api._store[self.index_key] = os.urandom(200)
        with pytest.raises(RuntimeError, match='branch index|cannot be read|refusing'):
            self.s.sync.clone(self.s.vault_key, self.new_dir)
        assert not os.path.isfile(os.path.join(self.new_dir, '.sg_vault', 'local', 'vault_key'))

    def test_control__an_honest_index_clones_with_the_policy(self):
        self.s.sync.clone(self.s.vault_key, self.new_dir)
        c   = self.s.sync._init_components(self.new_dir)
        idx = c.branch_manager.load_branch_index(self.new_dir, c.branch_index_file_id, c.read_key)
        assert 'signatures-required' in [str(f) for f in idx.features]

    def test_residual_TM_R29__an_index_the_host_withholds_still_clones_without_the_policy(self):
        """Accepted: a fresh clone cannot tell an old single-branch vault from a host that
        deleted the index. Documented under TM-R29; this test proves the gap is still open."""
        del self.s.api._store[self.index_key]
        self.s.sync.clone(self.s.vault_key, self.new_dir)
        c   = self.s.sync._init_components(self.new_dir)
        idx = c.branch_manager.load_branch_index(self.new_dir, c.branch_index_file_id, c.read_key)
        assert 'signatures-required' not in [str(f) for f in idx.features]
