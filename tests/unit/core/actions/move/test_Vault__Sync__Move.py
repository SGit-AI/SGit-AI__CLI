import copy
import json
import os
import shutil
import sys
import tempfile
import zipfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '_helpers'))
from vault_test_env import Vault__Test_Env

from sgit_ai.core.Vault__Sync                  import Vault__Sync
from sgit_ai.core.actions.move.Vault__Sync__Move import Vault__Sync__Move
from sgit_ai.crypto.Vault__Crypto              import Vault__Crypto
from sgit_ai.network.api.Vault__API__In_Memory import Vault__API__In_Memory



class Test_Vault__Sync__Move:
    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_single_vault(files={
            'hello.txt'   : 'hello world\n',
            'sub/data.txt': 'nested data',
        })

    def setup_method(self):
        self.env = self._env.restore()

    def teardown_method(self):
        self.env.cleanup()

    def _run_move(self, new_vault_key=None, dry_run=False, reason='test-rotation'):
        mover = Vault__Sync__Move(crypto=self.env.crypto, api=self.env.api)
        return mover.move(
            self.env.vault_dir,
            new_vault_key=new_vault_key,
            reason=reason,
            dry_run=dry_run,
        )

    def _old_vault_id(self):
        return self.env.crypto.derive_keys_from_vault_key(self.env.vault_key)['vault_id']

    def test_move_returns_final_state(self):
        result = self._run_move()
        assert result is not None

    def test_move_produces_new_vault_id(self):
        old_id = self._old_vault_id()
        self._run_move()
        new_key = open(os.path.join(self.env.vault_dir, '.sg_vault', 'local', 'vault_key')).read().strip()
        new_id  = self.env.crypto.derive_keys_from_vault_key(new_key)['vault_id']
        assert new_id != old_id

    def test_move_tombstones_old_vault(self):
        old_id = self._old_vault_id()
        self._run_move()
        assert self.env.api.is_tombstoned(old_id)

    def test_object_ids_are_stable_after_move(self):
        sg_dir  = os.path.join(self.env.vault_dir, '.sg_vault')
        data_dir = os.path.join(sg_dir, 'bare', 'data')
        before_ids = {f for f in os.listdir(data_dir) if f.startswith('obj-cas-imm-')}

        self._run_move()

        after_ids = {f for f in os.listdir(data_dir) if f.startswith('obj-cas-imm-')}
        assert before_ids.issubset(after_ids), (
            'All pre-move object IDs must survive key rotation '
            f'(missing: {before_ids - after_ids})'
        )

    def test_clone_from_new_vault_succeeds(self):
        self._run_move()
        new_key = open(os.path.join(self.env.vault_dir, '.sg_vault', 'local', 'vault_key')).read().strip()

        clone_dir = tempfile.mkdtemp()
        try:
            clone_sync = Vault__Sync(crypto=self.env.crypto, api=self.env.api)
            clone_sync.clone(new_key, clone_dir)
            assert os.path.isfile(os.path.join(clone_dir, 'hello.txt'))
            assert open(os.path.join(clone_dir, 'hello.txt')).read() == 'hello world\n'
            assert os.path.isfile(os.path.join(clone_dir, 'sub', 'data.txt'))
        finally:
            shutil.rmtree(clone_dir, ignore_errors=True)

    def test_sentinel_commit_is_on_named_branch(self):
        self._run_move(reason='key-rotation-test')
        new_key = open(os.path.join(self.env.vault_dir, '.sg_vault', 'local', 'vault_key')).read().strip()
        new_keys = self.env.crypto.derive_keys_from_vault_key(new_key)
        vault_id  = new_keys['vault_id']
        read_key  = new_keys['read_key_bytes']
        index_id  = new_keys.get('branch_index_file_id', '')

        if not index_id:
            pytest.skip('No branch index file ID in keys')

        raw_index = self.env.api.read(vault_id, f'bare/indexes/{index_id}')
        index_data = json.loads(self.env.crypto.decrypt(read_key, raw_index))

        named_ref_id = ''
        for branch in index_data.get('branches', []):
            if branch.get('branch_type') in ('named', 'NAMED'):
                named_ref_id = branch.get('head_ref_id', '')
                break
        assert named_ref_id, 'Named branch must have a head ref after move'

        raw_ref = self.env.api.read(vault_id, f'bare/refs/{named_ref_id}')
        ref_data = json.loads(self.env.crypto.decrypt(read_key, raw_ref))
        commit_id = ref_data.get('commit_id', '')
        assert commit_id, 'Named branch ref must have a commit_id'

    def test_named_branch_has_sentinel_message(self):
        self._run_move(reason='sentinel-check')
        new_key = open(os.path.join(self.env.vault_dir, '.sg_vault', 'local', 'vault_key')).read().strip()
        new_keys = self.env.crypto.derive_keys_from_vault_key(new_key)
        vault_id = new_keys['vault_id']
        read_key = new_keys['read_key_bytes']
        index_id = new_keys.get('branch_index_file_id', '')
        if not index_id:
            pytest.skip('No branch index file ID')

        raw_index  = self.env.api.read(vault_id, f'bare/indexes/{index_id}')
        index_data = json.loads(self.env.crypto.decrypt(read_key, raw_index))

        for branch in index_data.get('branches', []):
            if branch.get('branch_type') in ('named', 'NAMED'):
                named_ref_id = branch.get('head_ref_id', '')
                raw_ref  = self.env.api.read(vault_id, f'bare/refs/{named_ref_id}')
                ref_data = json.loads(self.env.crypto.decrypt(read_key, raw_ref))
                commit_id = ref_data.get('commit_id', '')
                raw_commit = self.env.api.read(vault_id, f'bare/data/{commit_id}')
                plaintext  = self.env.crypto.decrypt(read_key, raw_commit)
                commit_obj = json.loads(plaintext)
                msg = self.env.crypto.decrypt_metadata(read_key, commit_obj['message_enc'])
                assert 'vault-move' in msg.lower() or 'move' in msg.lower()
                return
        pytest.fail('No named branch found')

    def test_move_history_written(self):
        old_id = self._old_vault_id()
        self._run_move(reason='history-test')
        hist_path = os.path.join(self.env.vault_dir, '.sg_vault', 'local', 'move-history.json')
        assert os.path.isfile(hist_path)
        with open(hist_path) as f:
            data = json.load(f)
        moves = data.get('moves', [])
        assert len(moves) >= 1
        last = moves[-1]
        assert last.get('from_vault_id') == old_id
        assert last.get('reason') == 'history-test'

    def test_config_json_updated_with_new_vault_id(self):
        self._run_move()
        cfg_path = os.path.join(self.env.vault_dir, '.sg_vault', 'local', 'config.json')
        with open(cfg_path) as f:
            cfg = json.load(f)
        new_key = open(os.path.join(self.env.vault_dir, '.sg_vault', 'local', 'vault_key')).read().strip()
        expected_id = self.env.crypto.derive_keys_from_vault_key(new_key)['vault_id']
        assert cfg['vault_id'] == expected_id

    def test_key_generation_incremented(self):
        self._run_move()
        cfg_path = os.path.join(self.env.vault_dir, '.sg_vault', 'local', 'config.json')
        with open(cfg_path) as f:
            cfg = json.load(f)
        assert cfg.get('key_generation', 1) >= 2

    def test_no_sg_vault_new_after_successful_move(self):
        self._run_move()
        new_sg = os.path.join(self.env.vault_dir, '.sg_vault_new')
        assert not os.path.exists(new_sg), '.sg_vault_new must be removed after successful move'

    def test_backup_zip_created_before_delete(self):
        self._run_move()
        backups_dir = os.path.join(self.env.vault_dir, '.sg_vault', 'backups')
        zips = [f for f in os.listdir(backups_dir) if f.endswith('.zip')] if os.path.isdir(backups_dir) else []
        assert len(zips) >= 1, 'A backup zip must be created as part of vault move'

    def test_dry_run_does_not_modify_vault(self):
        sg_dir_before = os.path.join(self.env.vault_dir, '.sg_vault')
        old_id = self._old_vault_id()
        before_files = set(os.listdir(os.path.join(sg_dir_before, 'bare', 'data')))

        self._run_move(dry_run=True)

        after_files = set(os.listdir(os.path.join(sg_dir_before, 'bare', 'data')))
        assert before_files == after_files, 'dry_run must not modify data objects'
        assert not self.env.api.is_tombstoned(old_id), 'dry_run must not tombstone old vault'

    def test_dry_run_no_sg_vault_new(self):
        self._run_move(dry_run=True)
        new_sg = os.path.join(self.env.vault_dir, '.sg_vault_new')
        assert not os.path.exists(new_sg), 'dry_run must not create .sg_vault_new'

    def test_move_with_explicit_new_vault_key(self):
        crypto  = Vault__Crypto()
        new_key = 'explicitnewpassphrase1234:exvlt001'
        self._run_move(new_vault_key=new_key)
        actual_key = open(os.path.join(self.env.vault_dir, '.sg_vault', 'local', 'vault_key')).read().strip()
        assert actual_key == new_key

    def test_cleanup_after_interrupted_move(self):
        from sgit_ai.workflow.move.steps.Step__Move__Build_Temp_Vault import Step__Move__Build_Temp_Vault
        from sgit_ai.workflow.move.steps.Step__Move__Derive_New_Keys  import Step__Move__Derive_New_Keys
        from sgit_ai.workflow.move.steps.Step__Move__Validate_Local   import Step__Move__Validate_Local
        from sgit_ai.workflow.move.Move__Workspace                    import Move__Workspace
        from sgit_ai.schemas.workflow.move.Schema__Move__State        import Schema__Move__State
        from sgit_ai.safe_types.Safe_Str__File_Path                   import Safe_Str__File_Path

        state = Schema__Move__State(
            directory = Safe_Str__File_Path(self.env.vault_dir),
            dry_run   = False,
        )
        ws     = Move__Workspace(workspace_dir=Safe_Str__File_Path(tempfile.mkdtemp()))
        ws.api = self.env.api

        state = Step__Move__Validate_Local().execute(state, ws)
        state = Step__Move__Derive_New_Keys().execute(state, ws)
        state = Step__Move__Build_Temp_Vault().execute(state, ws)

        new_sg = os.path.join(self.env.vault_dir, '.sg_vault_new')
        assert os.path.isdir(new_sg)

        mover  = Vault__Sync__Move(crypto=self.env.crypto, api=self.env.api)
        result = mover.cleanup(self.env.vault_dir)
        assert result['renamed'] is True
        assert not os.path.isdir(new_sg), 'cleanup must rename .sg_vault_new to .sg_vault'
        assert os.path.isdir(os.path.join(self.env.vault_dir, '.sg_vault'))
