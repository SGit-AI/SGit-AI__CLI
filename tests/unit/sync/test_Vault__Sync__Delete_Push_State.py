# Tests for brief 14: delete_on_remote must clear push_state.json to prevent dangling blob references.
import json
import os
import shutil
import tempfile

from sgit_ai.api.Vault__API__In_Memory  import Vault__API__In_Memory
from sgit_ai.crypto.Vault__Crypto       import Vault__Crypto
from sgit_ai.sync.Vault__Storage        import Vault__Storage
from sgit_ai.sync.Vault__Sync           import Vault__Sync


class Test_Vault__Sync__Delete_Push_State:

    def setup_method(self):
        self.tmp     = tempfile.mkdtemp()
        self.crypto  = Vault__Crypto()
        self.api     = Vault__API__In_Memory()
        self.api.setup()
        self.sync    = Vault__Sync(crypto=self.crypto, api=self.api)
        self.storage = Vault__Storage()

    def teardown_method(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _pushed_vault(self):
        """Init a vault, commit a file, push. Returns (vault_dir, vault_key, vault_id)."""
        vault_dir = os.path.join(self.tmp, 'vault')
        self.sync.init(vault_dir)
        with open(os.path.join(vault_dir, 'data.txt'), 'w') as fh:
            fh.write('important data')
        self.sync.commit(vault_dir, message='initial')
        self.sync.push(vault_dir)
        vault_key = open(self.storage.vault_key_path(vault_dir)).read().strip()
        keys      = self.crypto.derive_keys_from_vault_key(vault_key)
        vault_id  = keys['vault_id']
        return vault_dir, vault_key, vault_id

    def _write_stale_push_state(self, vault_dir: str, vault_id: str) -> str:
        """Simulate a stale push_state.json left by an interrupted non-first push."""
        state_path = self.storage.push_state_path(vault_dir)
        stale = {
            'vault_id':        vault_id,
            'clone_commit_id': 'obj-cas-imm-aabb11223344',
            'blobs_uploaded':  ['obj-cas-imm-aabbccdd1122', 'obj-cas-imm-112233445566'],
        }
        with open(state_path, 'w') as fh:
            json.dump(stale, fh)
        return state_path

    def _vault_with_stale_push_state(self):
        """Return vault_dir that has push_state.json simulating an interrupted push."""
        vault_dir, vault_key, vault_id = self._pushed_vault()
        state_path = self._write_stale_push_state(vault_dir, vault_id)
        return vault_dir, vault_key, vault_id, state_path

    # -- 1. Bug-reproduction: push_state.json survives delete_on_remote ------
    # (Before the brief-14 fix, this stale file would persist through delete.)

    def test_bug_stale_push_state_exists_before_delete(self):
        """Confirm that a stale push_state.json can exist before delete_on_remote (precondition)."""
        vault_dir, _, vault_id, state_path = self._vault_with_stale_push_state()
        assert os.path.isfile(state_path), (
            'stale push_state.json must exist — precondition for bug-14')
        with open(state_path) as fh:
            state = json.load(fh)
        assert state.get('blobs_uploaded'), 'stale state must contain blob ids'

    # -- 2. Fix-verification: push_state.json is gone after delete_on_remote -

    def test_delete_on_remote_clears_push_state(self):
        """After delete_on_remote, push_state.json must be absent."""
        vault_dir, _, _, state_path = self._vault_with_stale_push_state()
        assert os.path.isfile(state_path), 'precondition: push_state.json must exist'

        self.sync.delete_on_remote(vault_dir)

        assert not os.path.isfile(state_path), (
            'push_state.json must be cleared by delete_on_remote (brief-14 fix)')

    def test_delete_on_remote_clears_push_state_even_when_no_prior_push(self):
        """delete_on_remote is safe (no error) when push_state.json is absent."""
        vault_dir, _, _, state_path = self._vault_with_stale_push_state()
        os.remove(state_path)   # ensure absent before delete
        assert not os.path.isfile(state_path), 'precondition: no push_state.json'
        # Must not raise
        self.sync.delete_on_remote(vault_dir)
        assert not os.path.isfile(state_path)

    # -- 3. End-to-end: push → delete → reinit same id → re-push uploads blobs

    def test_repush_after_delete_uploads_blobs_fresh(self):
        """Blobs must be uploaded on re-push to a fresh vault; push_state must not skip them."""
        vault_dir, vault_key, vault_id, state_path = self._vault_with_stale_push_state()

        # Delete the remote vault
        self.sync.delete_on_remote(vault_dir)
        assert not os.path.isfile(state_path), 'push_state must be cleared by delete_on_remote'

        # Server store is now empty — reinit same vault_key (same vault_id) on the same dir
        self.sync.init(vault_dir, vault_key=vault_key, allow_nonempty=True)
        with open(os.path.join(vault_dir, 'data.txt'), 'w') as fh:
            fh.write('important data')
        self.sync.commit(vault_dir, message='recommit')

        # Re-push — server is empty so first_push=True, all blobs must be uploaded
        result = self.sync.push(vault_dir)
        assert result.get('objects_uploaded', 0) > 0, (
            'blobs must be re-uploaded on first push after delete; '
            'stale push_state would have caused this to be 0')
