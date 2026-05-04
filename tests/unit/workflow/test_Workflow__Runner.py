"""Tests for Workflow__Runner."""
import os
import shutil
import tempfile

import pytest

from sgit_ai.workflow.Workflow__Runner    import Workflow__Runner
from sgit_ai.workflow.Workflow__Workspace import Workflow__Workspace
from sgit_ai.safe_types.Enum__Transaction_Log_Mode import Enum__Transaction_Log_Mode

# Re-use the synthetic fixtures from the other test module
from tests.unit.workflow.test_Synthetic__Workflow import (
    Workflow__Synth__Happy,
    Workflow__Synth__Fail_At_B,
)


class Test_Workflow__Runner:

    def setup_method(self):
        self.tmp = tempfile.mkdtemp()

    def teardown_method(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _make(self, wf, keep=True, log_mode=Enum__Transaction_Log_Mode.OFF):
        ws = Workflow__Workspace.create(wf.workflow_name(), self.tmp,
                                        workflow_version=wf.workflow_version())
        return Workflow__Runner(workflow=wf, workspace=ws, keep_work=keep,
                                log_mode=log_mode)

    def test_runner_default_log_mode_is_off(self):
        runner = Workflow__Runner()
        assert runner.log_mode == Enum__Transaction_Log_Mode.OFF

    def test_run_returns_final_output(self):
        runner = self._make(Workflow__Synth__Happy())
        result = runner.run()
        assert isinstance(result, dict)

    def test_run_writes_manifest(self):
        wf     = Workflow__Synth__Happy()
        ws     = Workflow__Workspace.create(wf.workflow_name(), self.tmp,
                                            workflow_version=wf.workflow_version())
        runner = Workflow__Runner(workflow=wf, workspace=ws, keep_work=True)
        runner.run()
        manifest = ws.read_manifest()
        assert manifest['workflow_name'] == 'synth-happy'

    def test_failed_workflow_raises(self):
        runner = self._make(Workflow__Synth__Fail_At_B())
        with pytest.raises(RuntimeError):
            runner.run()

    def test_transaction_log_off_no_disk_write(self):
        runner = self._make(Workflow__Synth__Happy(), log_mode=Enum__Transaction_Log_Mode.OFF)
        runner.run()
        # No vault directory → no log written; just verify no error
        # (workspace was cleaned; check tmp has no transactions dir)
        assert not os.path.exists(os.path.join(self.tmp, '.sg_vault'))
