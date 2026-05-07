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
from sgit_ai.workflow.move.Workflow__Vault_Move import Workflow__Vault_Move

class _FailingStep:
    """Minimal step replacement that always raises."""
    name = 'fail-injected'

    class _Impl:
        def is_done(self, ws): return False
        def validate_input(self, i): pass
        def validate_output(self, o): pass
        def execute(self, inp, ws):
            raise RuntimeError('injected failure')

    def __new__(cls):
        return cls._Impl()


def _make_failing_workflow(fail_at_index: int):
    """Return a Workflow__Vault_Move subclass where step `fail_at_index` is replaced."""
    from sgit_ai.workflow.move.steps.Step__Move__Validate_Local   import Step__Move__Validate_Local
    from sgit_ai.workflow.move.steps.Step__Move__Derive_New_Keys  import Step__Move__Derive_New_Keys
    from sgit_ai.workflow.move.steps.Step__Move__Build_Temp_Vault import Step__Move__Build_Temp_Vault
    from sgit_ai.workflow.move.steps.Step__Move__Write_Sentinel_Commits import Step__Move__Write_Sentinel_Commits
    from sgit_ai.workflow.move.steps.Step__Move__Push_To_Target   import Step__Move__Push_To_Target
    from sgit_ai.workflow.move.steps.Step__Move__Verify_Target    import Step__Move__Verify_Target
    from sgit_ai.workflow.move.steps.Step__Move__Backup_Old_Vault import Step__Move__Backup_Old_Vault
    from sgit_ai.workflow.move.steps.Step__Move__Delete_Source    import Step__Move__Delete_Source

    original = [
        Step__Move__Validate_Local,
        Step__Move__Derive_New_Keys,
        Step__Move__Build_Temp_Vault,
        Step__Move__Write_Sentinel_Commits,
        Step__Move__Push_To_Target,
        Step__Move__Verify_Target,
        Step__Move__Backup_Old_Vault,
        Step__Move__Delete_Source,
    ]
    modified = list(original)
    modified[fail_at_index] = _FailingStep

    class FailWorkflow(Workflow__Vault_Move):
        steps = modified

    return FailWorkflow


def _run_failing_move(env, fail_at_index):
    """Run the move workflow with a failure injected at step `fail_at_index` (0-based)."""
    import shutil
    from sgit_ai.safe_types.Safe_Str__Vault_Key      import Safe_Str__Vault_Key
    from sgit_ai.safe_types.Safe_Str__Commit_Message import Safe_Str__Commit_Message

    state = Schema__Move__State(
        directory = Safe_Str__File_Path(os.path.abspath(env.vault_dir)),
        reason    = Safe_Str__Commit_Message('failure-test'),
        dry_run   = False,
    )
    ws     = Move__Workspace(workspace_dir=Safe_Str__File_Path(tempfile.mkdtemp()))
    ws.api = env.api
    try:
        _make_failing_workflow(fail_at_index)().execute(state, ws)
    finally:
        if ws.workspace_dir and os.path.isdir(str(ws.workspace_dir)):
            shutil.rmtree(str(ws.workspace_dir), ignore_errors=True)


def _vault_is_intact(env):
    """Assert .sg_vault/ is a valid, working vault directory."""
    sg_dir = os.path.join(env.vault_dir, '.sg_vault')
    assert os.path.isdir(sg_dir), '.sg_vault/ must still exist'
    assert os.path.isfile(os.path.join(sg_dir, 'local', 'vault_key')), 'vault_key must exist'
    status = env.sync.status(env.vault_dir)
    assert status is not None, 'status() must work on vault after failure'


def _old_vault_key(env):
    return env.vault_key


def _old_vault_id(env):
    return env.crypto.derive_keys_from_vault_key(env.vault_key)['vault_id']


class Test_Vault__Sync__Move__Transaction:
    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_single_vault(files={'file.txt': 'data'})

    def setup_method(self):
        self.env = self._env.restore()

    def teardown_method(self):
        self.env.cleanup()

    def test_failure_in_step_1_validate_local(self):
        old_id = _old_vault_id(self.env)
        with pytest.raises(RuntimeError, match='injected'):
            _run_failing_move(self.env, fail_at_index=0)
        _vault_is_intact(self.env)
        assert not os.path.exists(os.path.join(self.env.vault_dir, '.sg_vault_new'))
        assert not self.env.api.is_tombstoned(old_id)

    def test_failure_in_step_2_derive_keys(self):
        old_id = _old_vault_id(self.env)
        with pytest.raises(RuntimeError, match='injected'):
            _run_failing_move(self.env, fail_at_index=1)
        _vault_is_intact(self.env)
        assert not self.env.api.is_tombstoned(old_id)

    def test_failure_in_step_3_build_temp_vault(self):
        old_id  = _old_vault_id(self.env)
        old_key = _old_vault_key(self.env)
        with pytest.raises(RuntimeError, match='injected'):
            _run_failing_move(self.env, fail_at_index=2)
        _vault_is_intact(self.env)
        assert not self.env.api.is_tombstoned(old_id)
        current_key = open(os.path.join(self.env.vault_dir, '.sg_vault', 'local', 'vault_key')).read().strip()
        assert current_key == old_key, 'vault_key must not change after step-3 failure'

    def test_failure_in_step_4_write_sentinel(self):
        old_id  = _old_vault_id(self.env)
        old_key = _old_vault_key(self.env)
        with pytest.raises(RuntimeError, match='injected'):
            _run_failing_move(self.env, fail_at_index=3)
        _vault_is_intact(self.env)
        assert not self.env.api.is_tombstoned(old_id)
        current_key = open(os.path.join(self.env.vault_dir, '.sg_vault', 'local', 'vault_key')).read().strip()
        assert current_key == old_key

    def test_failure_in_step_5_push_to_target(self):
        old_id  = _old_vault_id(self.env)
        old_key = _old_vault_key(self.env)
        with pytest.raises(RuntimeError, match='injected'):
            _run_failing_move(self.env, fail_at_index=4)
        _vault_is_intact(self.env)
        assert not self.env.api.is_tombstoned(old_id)
        current_key = open(os.path.join(self.env.vault_dir, '.sg_vault', 'local', 'vault_key')).read().strip()
        assert current_key == old_key

    def test_failure_in_step_6_verify_target(self):
        old_id  = _old_vault_id(self.env)
        old_key = _old_vault_key(self.env)
        with pytest.raises(RuntimeError, match='injected'):
            _run_failing_move(self.env, fail_at_index=5)
        _vault_is_intact(self.env)
        assert not self.env.api.is_tombstoned(old_id)
        current_key = open(os.path.join(self.env.vault_dir, '.sg_vault', 'local', 'vault_key')).read().strip()
        assert current_key == old_key

    def test_failure_in_step_7_backup(self):
        old_id  = _old_vault_id(self.env)
        old_key = _old_vault_key(self.env)
        with pytest.raises(RuntimeError, match='injected'):
            _run_failing_move(self.env, fail_at_index=6)
        _vault_is_intact(self.env)
        assert not self.env.api.is_tombstoned(old_id), (
            'old vault must NOT be tombstoned when backup step fails (pre-destructive boundary)'
        )
        current_key = open(os.path.join(self.env.vault_dir, '.sg_vault', 'local', 'vault_key')).read().strip()
        assert current_key == old_key

    def test_failure_in_step_8_delete_source(self):
        old_id = _old_vault_id(self.env)
        with pytest.raises(RuntimeError, match='injected'):
            _run_failing_move(self.env, fail_at_index=7)
        # After step 7 completed, .sg_vault_new/ was built and pushed but rename didn't run
        # .sg_vault/ is the original; .sg_vault_new/ may exist for --cleanup
        assert os.path.isdir(os.path.join(self.env.vault_dir, '.sg_vault')), \
            '.sg_vault/ must still be present for recovery'

    def test_move_retryable_after_pre_destructive_failure(self):
        for step_idx in range(6):  # steps 1–6 (0-indexed 0–5)
            env = self._env.restore()
            try:
                with pytest.raises(RuntimeError, match='injected'):
                    _run_failing_move(env, fail_at_index=step_idx)
                # Re-run the full move (no failure injection)
                mover = Vault__Sync__Move(crypto=env.crypto, api=env.api)
                mover.move(env.vault_dir, reason='retry-after-failure')
                new_key = open(os.path.join(env.vault_dir, '.sg_vault', 'local', 'vault_key')).read().strip()
                clone_dir = tempfile.mkdtemp()
                try:
                    Vault__Sync(crypto=env.crypto, api=env.api).clone(new_key, clone_dir)
                    assert os.path.isfile(os.path.join(clone_dir, 'file.txt'))
                finally:
                    shutil.rmtree(clone_dir, ignore_errors=True)
            finally:
                env.cleanup()

    def test_step_8b_idempotent_when_already_tombstoned(self):
        old_id  = _old_vault_id(self.env)
        old_keys = self.env.crypto.derive_keys_from_vault_key(self.env.vault_key)
        write_key = old_keys['write_key']

        self.env.api.tombstone_vault(old_id, write_key)
        assert self.env.api.is_tombstoned(old_id)

        mover  = Vault__Sync__Move(crypto=self.env.crypto, api=self.env.api)
        # cleanup with no .sg_vault_new/ and no pending move should raise clearly
        with pytest.raises(RuntimeError, match='[Nn]o pending'):
            mover.cleanup(self.env.vault_dir)
