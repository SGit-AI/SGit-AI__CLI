"""--cleanup semantic tests — Brief 03 §3h."""
import json
import os
import shutil
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '_helpers'))
from vault_test_env import Vault__Test_Env

from sgit_ai.core.Vault__Sync                   import Vault__Sync
from sgit_ai.core.actions.move.Vault__Sync__Move  import Vault__Sync__Move
from sgit_ai.crypto.Vault__Crypto               import Vault__Crypto
from sgit_ai.network.api.Vault__API__In_Memory  import Vault__API__In_Memory
from sgit_ai.workflow.move.Move__Workspace      import Move__Workspace
from sgit_ai.schemas.workflow.move.Schema__Move__State import Schema__Move__State
from sgit_ai.safe_types.Safe_Str__File_Path     import Safe_Str__File_Path
from sgit_ai.safe_types.Safe_Str__Commit_Message import Safe_Str__Commit_Message


def _build_interrupted_state(env):
    """Run steps 1–3 (build temp vault) but stop before rename.
    Leaves .sg_vault/ (old) and .sg_vault_new/ (new) both present."""
    from sgit_ai.workflow.move.steps.Step__Move__Validate_Local   import Step__Move__Validate_Local
    from sgit_ai.workflow.move.steps.Step__Move__Derive_New_Keys  import Step__Move__Derive_New_Keys
    from sgit_ai.workflow.move.steps.Step__Move__Build_Temp_Vault import Step__Move__Build_Temp_Vault

    state = Schema__Move__State(
        directory = Safe_Str__File_Path(os.path.abspath(env.vault_dir)),
        reason    = Safe_Str__Commit_Message('cleanup-test'),
        dry_run   = False,
    )
    ws_dir = tempfile.mkdtemp()
    ws     = Move__Workspace(workspace_dir=Safe_Str__File_Path(ws_dir))
    ws.api = env.api

    state = Step__Move__Validate_Local().execute(state, ws)
    state = Step__Move__Derive_New_Keys().execute(state, ws)
    state = Step__Move__Build_Temp_Vault().execute(state, ws)

    shutil.rmtree(ws_dir, ignore_errors=True)
    return state


class Test_Vault__Sync__Move__Cleanup:
    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_single_vault(files={'item.txt': 'content'})

    def setup_method(self):
        self.env = self._env.restore()

    def teardown_method(self):
        self.env.cleanup()

    def _mover(self):
        return Vault__Sync__Move(crypto=self.env.crypto, api=self.env.api)

    # 1. cleanup finishes the rename when .sg_vault_new/ exists
    def test_cleanup_finishes_local_rename(self):
        _build_interrupted_state(self.env)
        assert os.path.isdir(os.path.join(self.env.vault_dir, '.sg_vault_new')), \
            'precondition: .sg_vault_new/ must be present'

        result = self._mover().cleanup(self.env.vault_dir)

        assert result['renamed'] is True
        assert not os.path.isdir(os.path.join(self.env.vault_dir, '.sg_vault_new')), \
            '.sg_vault_new/ must be gone after cleanup'
        assert os.path.isdir(os.path.join(self.env.vault_dir, '.sg_vault')), \
            '.sg_vault/ must be the new vault after cleanup'

    # 2. cleanup leaves vault in a functional state after rename
    def test_cleanup_vault_is_functional_after_rename(self):
        _build_interrupted_state(self.env)
        self._mover().cleanup(self.env.vault_dir)

        # Should be able to read the vault key and status
        key_path = os.path.join(self.env.vault_dir, '.sg_vault', 'local', 'vault_key')
        assert os.path.isfile(key_path)
        new_key = open(key_path).read().strip()
        # Basic crypto sanity: can derive keys from new vault key
        new_keys = self.env.crypto.derive_keys_from_vault_key(new_key)
        assert new_keys.get('vault_id')

    # 3. cleanup is idempotent when old vault already tombstoned
    def test_cleanup_idempotent_when_old_vault_tombstoned(self):
        # Do a full move so old vault is tombstoned, then call cleanup
        # (move-history exists but no .sg_vault_new/)
        old_id    = self.env.crypto.derive_keys_from_vault_key(self.env.vault_key)['vault_id']
        self._mover().move(self.env.vault_dir, reason='pre-cleanup')
        assert self.env.api.is_tombstoned(old_id)

        # Now retry cleanup — should hit "no pending move" since everything is done
        with pytest.raises(RuntimeError, match='[Nn]o pending'):
            self._mover().cleanup(self.env.vault_dir)

    # 4. cleanup with no pending move errors clearly
    def test_cleanup_with_no_pending_move_errors_clearly(self):
        # No .sg_vault_new/ and no in-progress move-history
        new_sg_dir = os.path.join(self.env.vault_dir, '.sg_vault_new')
        assert not os.path.isdir(new_sg_dir)

        with pytest.raises(RuntimeError) as exc_info:
            self._mover().cleanup(self.env.vault_dir)
        assert 'pending' in str(exc_info.value).lower() or 'clean' in str(exc_info.value).lower()
