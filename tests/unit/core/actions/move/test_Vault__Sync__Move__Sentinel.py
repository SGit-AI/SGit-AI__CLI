import base64
import json
import os
import shutil
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '_helpers'))
from vault_test_env import Vault__Test_Env

from sgit_ai.core.Vault__Sync                  import Vault__Sync
from sgit_ai.core.actions.move.Vault__Sync__Move import Vault__Sync__Move
from sgit_ai.core.actions.branch.Vault__Branch_Switch import Vault__Branch_Switch
from sgit_ai.crypto.Vault__Crypto              import Vault__Crypto
from sgit_ai.crypto.PKI__Crypto               import PKI__Crypto
from sgit_ai.crypto.Vault__Key_Manager        import Vault__Key_Manager
from sgit_ai.network.api.Vault__API__In_Memory import Vault__API__In_Memory
from sgit_ai.storage.Vault__Object_Store      import Vault__Object_Store
from sgit_ai.storage.Vault__Ref_Manager       import Vault__Ref_Manager
from sgit_ai.schemas.Schema__Branch_Index     import Schema__Branch_Index


def _named_branch_sentinel(vault_dir, crypto, api):
    key_path  = os.path.join(vault_dir, '.sg_vault', 'local', 'vault_key')
    vault_key = open(key_path).read().strip()
    keys      = crypto.derive_keys_from_vault_key(vault_key)
    vault_id  = keys['vault_id']
    read_key  = keys['read_key_bytes']
    index_id  = keys.get('branch_index_file_id', '')

    raw_idx   = api.read(vault_id, f'bare/indexes/{index_id}')
    idx_data  = json.loads(crypto.decrypt(read_key, raw_idx))

    for branch in idx_data.get('branches', []):
        if branch.get('branch_type') not in ('named', 'NAMED'):
            continue
        head_ref_id = branch.get('head_ref_id', '')
        raw_ref     = api.read(vault_id, f'bare/refs/{head_ref_id}')
        ref_data    = json.loads(crypto.decrypt(read_key, raw_ref))
        commit_id   = ref_data.get('commit_id', '')
        raw_commit  = api.read(vault_id, f'bare/data/{commit_id}')
        commit_obj  = json.loads(crypto.decrypt(read_key, raw_commit))
        msg         = crypto.decrypt_metadata(read_key, commit_obj['message_enc'])
        return branch, commit_obj, msg, vault_id, read_key, index_id

    return None, None, None, None, None, None


class Test_Vault__Sync__Move__Sentinel:
    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_single_vault(files={'a.txt': 'alpha', 'b.txt': 'beta'})

    def setup_method(self):
        self.env = self._env.restore()

    def teardown_method(self):
        self.env.cleanup()

    def _move(self, reason='sentinel-test'):
        mover = Vault__Sync__Move(crypto=self.env.crypto, api=self.env.api)
        mover.move(self.env.vault_dir, reason=reason)

    def _old_vault_id(self):
        return self.env.crypto.derive_keys_from_vault_key(self.env.vault_key)['vault_id']

    def test_sentinel_message_format(self):
        old_id = self._old_vault_id()
        self._move(reason='rotation-test')
        _, _, msg, vault_id, _, _ = _named_branch_sentinel(
            self.env.vault_dir, self.env.crypto, self.env.api)
        assert 'vault-move' in msg.lower()
        assert vault_id in msg
        assert 'rotation-test' in msg

    def test_sentinel_parent_is_old_head(self):
        # Capture old HEAD commit id before move
        old_key      = self.env.vault_key
        old_keys     = self.env.crypto.derive_keys_from_vault_key(old_key)
        old_vault_id = old_keys['vault_id']
        old_read_key = old_keys['read_key_bytes']
        old_index_id = old_keys.get('branch_index_file_id', '')

        raw_idx  = self.env.api.read(old_vault_id, f'bare/indexes/{old_index_id}')
        idx_data = json.loads(self.env.crypto.decrypt(old_read_key, raw_idx))
        old_head_commit_id = None
        for branch in idx_data.get('branches', []):
            if branch.get('branch_type') in ('named', 'NAMED'):
                head_ref_id = branch.get('head_ref_id', '')
                raw_ref  = self.env.api.read(old_vault_id, f'bare/refs/{head_ref_id}')
                ref_data = json.loads(self.env.crypto.decrypt(old_read_key, raw_ref))
                old_head_commit_id = ref_data.get('commit_id', '')
                break

        self._move()
        _, commit_obj, _, _, _, _ = _named_branch_sentinel(
            self.env.vault_dir, self.env.crypto, self.env.api)

        parents = commit_obj.get('parents', [])
        assert old_head_commit_id in parents, (
            f'sentinel parent {parents} does not contain old HEAD {old_head_commit_id}'
        )

    def test_sentinel_tree_unchanged(self):
        old_key      = self.env.vault_key
        old_keys     = self.env.crypto.derive_keys_from_vault_key(old_key)
        old_vault_id = old_keys['vault_id']
        old_read_key = old_keys['read_key_bytes']
        old_index_id = old_keys.get('branch_index_file_id', '')

        raw_idx  = self.env.api.read(old_vault_id, f'bare/indexes/{old_index_id}')
        idx_data = json.loads(self.env.crypto.decrypt(old_read_key, raw_idx))
        old_parent_tree_id = None
        for branch in idx_data.get('branches', []):
            if branch.get('branch_type') in ('named', 'NAMED'):
                head_ref_id = branch.get('head_ref_id', '')
                raw_ref  = self.env.api.read(old_vault_id, f'bare/refs/{head_ref_id}')
                ref_data = json.loads(self.env.crypto.decrypt(old_read_key, raw_ref))
                parent_id = ref_data.get('commit_id', '')
                raw_parent = self.env.api.read(old_vault_id, f'bare/data/{parent_id}')
                parent_obj = json.loads(self.env.crypto.decrypt(old_read_key, raw_parent))
                old_parent_tree_id = parent_obj.get('tree_id', '')
                break

        self._move()
        _, commit_obj, _, vault_id, read_key, _ = _named_branch_sentinel(
            self.env.vault_dir, self.env.crypto, self.env.api)

        assert commit_obj.get('tree_id') == old_parent_tree_id, (
            'sentinel must reuse parent tree (no file changes)'
        )

    def test_sentinel_signed_by_new_branch_key(self):
        self._move()
        _, commit_obj, _, vault_id, read_key, index_id = _named_branch_sentinel(
            self.env.vault_dir, self.env.crypto, self.env.api)

        sig_b64 = commit_obj.get('signature', '')
        if not sig_b64:
            pytest.skip('sentinel has no signature (branch had no signing key)')

        # Load public key from new vault's bare/keys/
        new_sg_dir = os.path.join(self.env.vault_dir, '.sg_vault')

        raw_idx  = self.env.api.read(vault_id, f'bare/indexes/{index_id}')
        idx_data = json.loads(self.env.crypto.decrypt(read_key, raw_idx))
        pub_key_id = None
        for branch in idx_data.get('branches', []):
            if branch.get('branch_type') in ('named', 'NAMED'):
                pub_key_id = branch.get('public_key_id', '')
                break

        if not pub_key_id:
            pytest.skip('no public_key_id on named branch')

        pki        = PKI__Crypto()
        key_mgr    = Vault__Key_Manager(vault_path=new_sg_dir, crypto=self.env.crypto, pki=pki)
        public_key = key_mgr.load_public_key(pub_key_id, read_key)

        # Reconstruct signed bytes: commit JSON with signature set to null
        # (matches the data that was signed before the signature field was populated)
        commit_copy = dict(commit_obj)
        commit_copy['signature'] = None
        signed_bytes = json.dumps(commit_copy).encode('utf-8')
        sig_raw      = base64.b64decode(sig_b64)
        assert pki.verify(public_key, sig_raw, signed_bytes), (
            'sentinel signature does not verify under the new branch public key'
        )

    def test_sentinel_is_new_head(self):
        self._move(reason='head-check')
        _, _, msg, vault_id, read_key, index_id = _named_branch_sentinel(
            self.env.vault_dir, self.env.crypto, self.env.api)
        assert 'vault-move' in msg.lower(), 'HEAD commit after move must be the sentinel'

    def test_sentinel_per_active_branch(self):
        crypto  = Vault__Crypto()
        api     = Vault__API__In_Memory()
        api.setup()
        sync     = Vault__Sync(crypto=crypto, api=api)
        switcher = Vault__Branch_Switch(crypto=crypto)

        tmp      = tempfile.mkdtemp()
        vault_dir = os.path.join(tmp, 'vault')
        try:
            sync.init(vault_dir)
            with open(os.path.join(vault_dir, 'base.txt'), 'w') as fh:
                fh.write('base')
            sync.commit(vault_dir, message='base')
            sync.push(vault_dir)

            branches = sync.branches(vault_dir)
            main_b   = next(b for b in branches['branches'] if b['branch_type'] == 'named')
            switcher.branch_new(vault_dir, 'feat1', from_branch_id=main_b['branch_id'])
            switcher.switch(vault_dir, 'feat1')
            with open(os.path.join(vault_dir, 'feat1.txt'), 'w') as fh:
                fh.write('feat1')
            sync.commit(vault_dir, message='feat1 commit')
            sync.push(vault_dir)

            switcher.branch_new(vault_dir, 'feat2', from_branch_id=main_b['branch_id'])
            switcher.switch(vault_dir, 'feat2')
            with open(os.path.join(vault_dir, 'feat2.txt'), 'w') as fh:
                fh.write('feat2')
            sync.commit(vault_dir, message='feat2 commit')
            sync.push(vault_dir)

            vault_key = open(os.path.join(vault_dir, '.sg_vault', 'local', 'vault_key')).read().strip()
            keys      = crypto.derive_keys_from_vault_key(vault_key)
            vault_id  = keys['vault_id']
            read_key  = keys['read_key_bytes']
            index_id  = keys.get('branch_index_file_id', '')

            from sgit_ai.core.actions.move.Vault__Sync__Move import Vault__Sync__Move as _M
            _M(crypto=crypto, api=api).move(vault_dir, reason='multi-branch')

            new_key      = open(os.path.join(vault_dir, '.sg_vault', 'local', 'vault_key')).read().strip()
            new_keys     = crypto.derive_keys_from_vault_key(new_key)
            new_vault_id = new_keys['vault_id']
            new_read_key = new_keys['read_key_bytes']
            new_index_id = new_keys.get('branch_index_file_id', '')

            raw_idx2  = api.read(new_vault_id, f'bare/indexes/{new_index_id}')
            idx_data2 = json.loads(crypto.decrypt(new_read_key, raw_idx2))

            sentinel_count = 0
            n_named_post   = 0
            for branch in idx_data2.get('branches', []):
                if branch.get('branch_type') not in ('named', 'NAMED'):
                    continue
                n_named_post += 1
                head_ref_id = branch.get('head_ref_id', '')
                raw_ref  = api.read(new_vault_id, f'bare/refs/{head_ref_id}')
                ref_data = json.loads(crypto.decrypt(new_read_key, raw_ref))
                commit_id = ref_data.get('commit_id', '')
                raw_commit = api.read(new_vault_id, f'bare/data/{commit_id}')
                commit_obj = json.loads(crypto.decrypt(new_read_key, raw_commit))
                msg = crypto.decrypt_metadata(new_read_key, commit_obj['message_enc'])
                if 'vault-move' in msg.lower():
                    sentinel_count += 1

            assert n_named_post >= 1, 'must have at least one named branch after move'
            assert sentinel_count == n_named_post, (
                f'expected {n_named_post} sentinel commits (one per named branch), got {sentinel_count}'
            )
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_sentinel_round_trip_via_clone(self):
        self._move(reason='clone-check')
        new_key = open(os.path.join(self.env.vault_dir, '.sg_vault', 'local', 'vault_key')).read().strip()

        clone_dir = tempfile.mkdtemp()
        try:
            clone_sync = Vault__Sync(crypto=self.env.crypto, api=self.env.api)
            clone_sync.clone(new_key, clone_dir)

            # The clone's HEAD should include the sentinel as the latest commit
            clone_keys     = self.env.crypto.derive_keys_from_vault_key(new_key)
            clone_vault_id = clone_keys['vault_id']
            clone_read_key = clone_keys['read_key_bytes']
            clone_index_id = clone_keys.get('branch_index_file_id', '')

            raw_idx  = self.env.api.read(clone_vault_id, f'bare/indexes/{clone_index_id}')
            idx_data = json.loads(self.env.crypto.decrypt(clone_read_key, raw_idx))

            for branch in idx_data.get('branches', []):
                if branch.get('branch_type') in ('named', 'NAMED'):
                    head_ref_id = branch.get('head_ref_id', '')
                    raw_ref  = self.env.api.read(clone_vault_id, f'bare/refs/{head_ref_id}')
                    ref_data = json.loads(self.env.crypto.decrypt(clone_read_key, raw_ref))
                    commit_id = ref_data.get('commit_id', '')
                    raw_commit = self.env.api.read(clone_vault_id, f'bare/data/{commit_id}')
                    commit_obj = json.loads(self.env.crypto.decrypt(clone_read_key, raw_commit))
                    msg = self.env.crypto.decrypt_metadata(clone_read_key, commit_obj['message_enc'])
                    assert 'vault-move' in msg.lower(), (
                        f'clone HEAD should be the sentinel; got: {msg[:60]}'
                    )
                    return
            pytest.fail('No named branch found in clone')
        finally:
            shutil.rmtree(clone_dir, ignore_errors=True)
