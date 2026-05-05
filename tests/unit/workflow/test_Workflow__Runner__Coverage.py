"""Coverage tests for Workflow__Runner paths not hit by the synthetic tests."""
import json
import os
import shutil
import tempfile

import pytest

from sgit_ai.safe_types.Enum__Transaction_Log_Mode import Enum__Transaction_Log_Mode
from sgit_ai.workflow.Workflow__Runner    import Workflow__Runner
from sgit_ai.workflow.Workflow__Workspace import Workflow__Workspace

from sgit_ai.workflow.Step                     import Step
from sgit_ai.workflow.Workflow                 import Workflow
from sgit_ai.safe_types.Safe_Str__Step_Name   import Safe_Str__Step_Name
from sgit_ai.safe_types.Safe_Str__Workflow_Name import Safe_Str__Workflow_Name
from sgit_ai.safe_types.Safe_Str__Semver      import Safe_Str__Semver

from tests.unit.workflow.test_Synthetic__Workflow import (
    Workflow__Synth__Happy,
    Workflow__Synth__Fail_At_B,
    Step__Synth__A,
    Schema__S1__Output,
    Schema__Synth__Input,
)


class Step__Synth__Raise_Value_Error(Step):
    name          = Safe_Str__Step_Name('step-value-error')
    input_schema  = Schema__Synth__Input
    output_schema = Schema__S1__Output

    def execute(self, input, workspace):
        raise ValueError('typed exception preserved')


class Workflow__Synth__Typed_Exc(Workflow):
    def step_classes(self): return [Step__Synth__Raise_Value_Error]
    def workflow_name(self):    return Safe_Str__Workflow_Name('synth-typed-exc')
    def workflow_version(self): return Safe_Str__Semver('1.0.0')


class Test_Workflow__Runner__Transaction_Log:

    def setup_method(self):
        self.tmp = tempfile.mkdtemp()

    def teardown_method(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _make(self, wf, log_mode=Enum__Transaction_Log_Mode.WRITES, keep=True):
        ws = Workflow__Workspace.create(wf.workflow_name(), self.tmp,
                                        workflow_version=wf.workflow_version())
        return Workflow__Runner(workflow=wf, workspace=ws, keep_work=keep,
                                log_mode=log_mode)

    def test_writes_mode_does_not_raise(self):
        runner = self._make(Workflow__Synth__Happy(), log_mode=Enum__Transaction_Log_Mode.WRITES)
        result = runner.run()
        assert isinstance(result, dict)

    def test_all_mode_does_not_raise(self):
        runner = self._make(Workflow__Synth__Happy(), log_mode=Enum__Transaction_Log_Mode.ALL)
        runner.run()

    def test_transaction_log_written_inside_sg_vault(self):
        sg_vault = os.path.join(self.tmp, '.sg_vault', 'local')
        os.makedirs(sg_vault, exist_ok=True)
        wf = Workflow__Synth__Happy()
        ws = Workflow__Workspace.create(wf.workflow_name(), self.tmp,
                                        workflow_version=wf.workflow_version())
        runner = Workflow__Runner(workflow=wf, workspace=ws, keep_work=True,
                                  log_mode=Enum__Transaction_Log_Mode.WRITES)
        runner.run()
        tx_dir = os.path.join(sg_vault, 'transactions')
        assert os.path.isdir(tx_dir)
        log_files = os.listdir(tx_dir)
        assert len(log_files) == 1
        line = open(os.path.join(tx_dir, log_files[0])).readline().strip()
        record = json.loads(line)
        assert record['workflow_name'] == 'synth-happy'
        assert record['status'] == 'success'

    def test_transaction_log_on_failure(self):
        sg_vault = os.path.join(self.tmp, '.sg_vault', 'local')
        os.makedirs(sg_vault, exist_ok=True)
        wf = Workflow__Synth__Fail_At_B()
        ws = Workflow__Workspace.create(wf.workflow_name(), self.tmp,
                                        workflow_version=wf.workflow_version())
        runner = Workflow__Runner(workflow=wf, workspace=ws, keep_work=True,
                                  log_mode=Enum__Transaction_Log_Mode.WRITES)
        with pytest.raises(RuntimeError):
            runner.run()
        tx_dir   = os.path.join(sg_vault, 'transactions')
        log_files = os.listdir(tx_dir)
        assert len(log_files) == 1
        line = open(os.path.join(tx_dir, log_files[0])).readline().strip()
        record = json.loads(line)
        assert record['status'] == 'failed'
        assert record['error'] is not None

    def test_transaction_record_has_step_summaries(self):
        sg_vault = os.path.join(self.tmp, '.sg_vault', 'local')
        os.makedirs(sg_vault, exist_ok=True)
        wf = Workflow__Synth__Happy()
        ws = Workflow__Workspace.create(wf.workflow_name(), self.tmp,
                                        workflow_version=wf.workflow_version())
        runner = Workflow__Runner(workflow=wf, workspace=ws, keep_work=True,
                                  log_mode=Enum__Transaction_Log_Mode.WRITES)
        runner.run()
        tx_dir = os.path.join(sg_vault, 'transactions')
        line = open(os.path.join(tx_dir, os.listdir(tx_dir)[0])).readline().strip()
        record = json.loads(line)
        assert 'steps_summary' in record
        assert len(record['steps_summary']) == 3

    def test_transaction_log_not_written_without_sg_vault(self):
        wf = Workflow__Synth__Happy()
        ws = Workflow__Workspace.create(wf.workflow_name(), self.tmp,
                                        workflow_version=wf.workflow_version())
        runner = Workflow__Runner(workflow=wf, workspace=ws, keep_work=True,
                                  log_mode=Enum__Transaction_Log_Mode.WRITES)
        runner.run()
        # No .sg_vault/local dir → no transactions written, but no error either
        assert not os.path.exists(os.path.join(self.tmp, '.sg_vault', 'local', 'transactions'))


class Test_Workflow__Runner__Helpers:

    def setup_method(self):
        self.tmp = tempfile.mkdtemp()

    def teardown_method(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _runner(self):
        wf = Workflow__Synth__Happy()
        ws = Workflow__Workspace.create(wf.workflow_name(), self.tmp)
        return Workflow__Runner(workflow=wf, workspace=ws)

    def test_now_ms_returns_int(self):
        r = self._runner()
        assert isinstance(r._now_ms(), int)

    def test_now_iso_returns_utc_string(self):
        r   = self._runner()
        iso = r._now_iso()
        assert iso.endswith('Z')
        assert 'T' in iso

    def test_now_ms_increases_over_time(self):
        import time
        r  = self._runner()
        t0 = r._now_ms()
        time.sleep(0.01)
        t1 = r._now_ms()
        assert t1 >= t0


class Test_Workflow__Runner__ManifestFields:

    def setup_method(self):
        self.tmp = tempfile.mkdtemp()

    def teardown_method(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _make(self, wf, keep=True):
        ws = Workflow__Workspace.create(wf.workflow_name(), self.tmp,
                                        workflow_version=wf.workflow_version())
        return Workflow__Runner(workflow=wf, workspace=ws, keep_work=keep)

    def test_manifest_has_work_id(self):
        wf     = Workflow__Synth__Happy()
        ws     = Workflow__Workspace.create(wf.workflow_name(), self.tmp,
                                            workflow_version=wf.workflow_version())
        runner = Workflow__Runner(workflow=wf, workspace=ws, keep_work=True)
        runner.run()
        manifest = ws.read_manifest()
        assert 'work_id' in manifest
        assert manifest['work_id']

    def test_manifest_has_keep_work_field(self):
        wf     = Workflow__Synth__Happy()
        ws     = Workflow__Workspace.create(wf.workflow_name(), self.tmp,
                                            workflow_version=wf.workflow_version())
        runner = Workflow__Runner(workflow=wf, workspace=ws, keep_work=True)
        runner.run()
        manifest = ws.read_manifest()
        assert 'keep_work' in manifest

    def test_manifest_step_entries_have_duration(self):
        wf     = Workflow__Synth__Happy()
        ws     = Workflow__Workspace.create(wf.workflow_name(), self.tmp,
                                            workflow_version=wf.workflow_version())
        runner = Workflow__Runner(workflow=wf, workspace=ws, keep_work=True)
        runner.run()
        manifest = ws.read_manifest()
        for entry in manifest['steps']:
            assert 'duration_ms' in entry
            assert isinstance(entry['duration_ms'], int)

    def test_failed_step_has_failed_status_in_manifest(self):
        wf     = Workflow__Synth__Fail_At_B()
        ws     = Workflow__Workspace.create(wf.workflow_name(), self.tmp,
                                            workflow_version=wf.workflow_version())
        runner = Workflow__Runner(workflow=wf, workspace=ws, keep_work=True)
        with pytest.raises(RuntimeError):
            runner.run()
        manifest = ws.read_manifest()
        statuses = [e['status'] for e in manifest['steps']]
        assert 'failed' in statuses

    def test_error_message_stored_in_manifest(self):
        wf     = Workflow__Synth__Fail_At_B()
        ws     = Workflow__Workspace.create(wf.workflow_name(), self.tmp,
                                            workflow_version=wf.workflow_version())
        runner = Workflow__Runner(workflow=wf, workspace=ws, keep_work=True)
        with pytest.raises(RuntimeError):
            runner.run()
        manifest = ws.read_manifest()
        assert manifest['error'] is not None
        assert 'intentional failure' in manifest['error']

    def test_completed_at_always_set(self):
        wf     = Workflow__Synth__Happy()
        ws     = Workflow__Workspace.create(wf.workflow_name(), self.tmp,
                                            workflow_version=wf.workflow_version())
        runner = Workflow__Runner(workflow=wf, workspace=ws, keep_work=True)
        runner.run()
        manifest = ws.read_manifest()
        assert manifest['completed_at'] is not None


class Test_Workflow__Runner__ExceptionPreservation:

    def setup_method(self):
        self.tmp = tempfile.mkdtemp()

    def teardown_method(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_typed_exception_preserved_through_runner(self):
        """Workflow__Runner re-raises the original exception type, not RuntimeError."""
        wf     = Workflow__Synth__Typed_Exc()
        ws     = Workflow__Workspace.create(wf.workflow_name(), self.tmp,
                                            workflow_version=wf.workflow_version())
        runner = Workflow__Runner(workflow=wf, workspace=ws, keep_work=True)
        with pytest.raises(ValueError, match='typed exception preserved'):
            runner.run()

    def test_runtime_error_still_propagates(self):
        wf     = Workflow__Synth__Fail_At_B()
        ws     = Workflow__Workspace.create(wf.workflow_name(), self.tmp,
                                            workflow_version=wf.workflow_version())
        runner = Workflow__Runner(workflow=wf, workspace=ws, keep_work=True)
        with pytest.raises(RuntimeError):
            runner.run()
