"""A pull (and so a push's implicit pull) does not walk the head's trees when the server's
head is the one this clone last accepted and the commit with its root tree is local:
nothing on the server is new to it (report of 26 Oct: that walk was 5 of a push's 7
minutes on the newsroom vault). A head the clone has not accepted — another clone's
push, or no record of what was accepted — takes the full fetch as before."""
import os

import pytest

from sgit_ai.storage.Vault__Object_Store import Vault__Object_Store
from tests._helpers.pack_env             import Pack__Env
from tests._helpers.vault_test_env       import TEST_VAULT_KEY

SKIPPED  = "No missing objects to fetch (the server's head is the one this clone last accepted)"
FETCHING = 'Fetching missing objects from server'


def _pull_steps(sync, directory):
    events = []
    result = sync.pull(directory, on_progress=lambda kind, msg, detail='': events.append((kind, msg)))
    return result, [msg for kind, msg in events if kind == 'step']


class Test_Pull__Skips_Walk_When_Head_Accepted:

    def setup_method(self):
        self.env = Pack__Env()
        self.sync, self.a, key = self.env.normal_vault(self.env.text_files(3), vault_key=TEST_VAULT_KEY)
        self.sync_b, self.b = self.env.clone(key, 'b')
        self.env.write(self.a, {'local.md': b'not pushed yet\n'})
        self.sync.commit(self.a, message='ahead of the server')               # clone head != named head

    def test_the_head_this_clone_pushed_is_not_walked_again(self):
        _, steps = _pull_steps(self.sync, self.a)
        assert SKIPPED in steps and FETCHING not in steps

    def test_another_clones_push_is_fetched_in_full(self):
        self.env.write(self.b, {'from-b.md': b'b was here\n'})
        self.sync_b.commit(self.b, message='from b'); self.sync_b.push(self.b)
        result, steps = _pull_steps(self.sync, self.a)
        assert FETCHING in steps and SKIPPED not in steps
        assert os.path.isfile(os.path.join(self.a, 'from-b.md'))
        _, steps = _pull_steps(self.sync, self.a)                             # accepted now: skipped again
        assert SKIPPED in steps or FETCHING not in steps

    def test_no_record_of_an_accepted_head_means_the_full_fetch(self):
        local = os.path.join(self.a, '.sg_vault', 'local')
        os.rename(os.path.join(local, 'remote_heads.json'), os.path.join(local, 'remote_heads.json.away'))
        try:
            with pytest.raises(Exception):                                     # the missing record refuses the pull itself
                self.sync.pull(self.a)                                         # (review d3b8eef L1), not just the skip
        finally:
            os.rename(os.path.join(local, 'remote_heads.json.away'), os.path.join(local, 'remote_heads.json'))

    def test_a_missing_root_tree_means_the_full_fetch(self):
        c    = self.sync._init_components(self.a)
        from sgit_ai.storage.Vault__Commit import Vault__Commit
        vc   = Vault__Commit(crypto=self.sync.crypto, pki=c.pki, object_store=c.obj_store, ref_manager=c.ref_manager)
        head = self.sync._read_remote_baseline(self.a, c.storage, self.sync._tracked_named_ref_id(self.a))
        tree = str(vc.load_commit(head, c.read_key).tree_id)
        os.remove(c.obj_store.object_path(tree))
        _, steps = _pull_steps(self.sync, self.a)
        assert FETCHING in steps and SKIPPED not in steps
        assert c.obj_store.exists(tree)                                        # fetched back

    def test_a_push_after_the_skip_sends_the_local_commit(self):
        result = self.sync.push(self.a)
        assert result['status'] == 'pushed' and result['commits_pushed'] == 1
        self.sync_b.pull(self.b)
        assert os.path.isfile(os.path.join(self.b, 'local.md'))
