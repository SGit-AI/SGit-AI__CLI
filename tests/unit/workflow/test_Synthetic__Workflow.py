"""Synthetic 3-step workflow fixture tests — happy path, resume, abort, atomic-write."""
import json
import os
import shutil
import tempfile

import pytest

from osbot_utils.type_safe.Type_Safe                   import Type_Safe
from osbot_utils.type_safe.primitives.core.Safe_Str    import Safe_Str
from sgit_ai.workflow.Step                             import Step
from sgit_ai.workflow.Workflow                         import Workflow
from sgit_ai.workflow.Workflow__Workspace              import Workflow__Workspace
from sgit_ai.workflow.Workflow__Runner                 import Workflow__Runner
from sgit_ai.safe_types.Safe_Str__Step_Name            import Safe_Str__Step_Name
from sgit_ai.safe_types.Safe_Str__Workflow_Name        import Safe_Str__Workflow_Name
from sgit_ai.safe_types.Safe_Str__Semver               import Safe_Str__Semver


# ------------------------------------------------------------------
# Synthetic schemas
# ------------------------------------------------------------------

class Schema__Synth__Input(Type_Safe):
    seed : Safe_Str = None

class Schema__S1__Output(Type_Safe):
    value_a : Safe_Str = None

class Schema__S2__Output(Type_Safe):
    value_b : Safe_Str = None

class Schema__S3__Output(Type_Safe):
    final   : Safe_Str = None


# ------------------------------------------------------------------
# Synthetic steps
# ------------------------------------------------------------------

class Step__Synth__A(Step):
    name          = Safe_Str__Step_Name('step-a')
    input_schema  = Schema__Synth__Input
    output_schema = Schema__S1__Output

    def execute(self, input, workspace):
        return Schema__S1__Output(value_a='result_a')


class Step__Synth__B(Step):
    name          = Safe_Str__Step_Name('step-b')
    input_schema  = Schema__S1__Output
    output_schema = Schema__S2__Output

    def execute(self, input, workspace):
        return Schema__S2__Output(value_b='result_b')


class Step__Synth__C(Step):
    name          = Safe_Str__Step_Name('step-c')
    input_schema  = Schema__S2__Output
    output_schema = Schema__S3__Output

    def execute(self, input, workspace):
        return Schema__S3__Output(final='result_c')


class Step__Synth__Failing(Step):
    name          = Safe_Str__Step_Name('step-fail')
    input_schema  = Schema__Synth__Input
    output_schema = Schema__S1__Output

    def execute(self, input, workspace):
        raise RuntimeError('intentional failure in step-fail')


# ------------------------------------------------------------------
# Synthetic workflows
# ------------------------------------------------------------------

class Workflow__Synth__Happy(Workflow):
    name    = Safe_Str__Workflow_Name('synth-happy')
    version = Safe_Str__Semver('1.0.0')
    steps   = [Step__Synth__A, Step__Synth__B, Step__Synth__C]


class Workflow__Synth__Fail_At_B(Workflow):
    name    = Safe_Str__Workflow_Name('synth-fail-b')
    version = Safe_Str__Semver('1.0.0')
    steps   = [Step__Synth__A, Step__Synth__Failing, Step__Synth__C]


class Workflow__Synth__V2(Workflow):
    name    = Safe_Str__Workflow_Name('synth-happy')
    version = Safe_Str__Semver('2.0.0')
    steps   = [Step__Synth__A]


# ------------------------------------------------------------------
# Tests: happy path
# ------------------------------------------------------------------

class Test_Synthetic__Workflow__Happy:

    def setup_method(self):
        self.tmp = tempfile.mkdtemp()

    def teardown_method(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _make_runner(self, wf, keep_work=True):
        ws = Workflow__Workspace.create(wf.workflow_name(), self.tmp,
                                        workflow_version=wf.workflow_version())
        return Workflow__Runner(workflow=wf, workspace=ws, keep_work=keep_work)

    def test_happy_path_runs_all_steps(self):
        runner = self._make_runner(Workflow__Synth__Happy())
        result = runner.run()
        assert result.get('final') == 'result_c'

    def test_manifest_status_success(self):
        wf     = Workflow__Synth__Happy()
        ws     = Workflow__Workspace.create(wf.workflow_name(), self.tmp,
                                            workflow_version=wf.workflow_version())
        runner = Workflow__Runner(workflow=wf, workspace=ws, keep_work=True)
        runner.run()
        manifest = ws.read_manifest()
        assert manifest['status'] == 'success'

    def test_all_steps_completed_in_manifest(self):
        wf     = Workflow__Synth__Happy()
        ws     = Workflow__Workspace.create(wf.workflow_name(), self.tmp,
                                            workflow_version=wf.workflow_version())
        runner = Workflow__Runner(workflow=wf, workspace=ws, keep_work=True)
        runner.run()
        manifest = ws.read_manifest()
        for entry in manifest['steps']:
            assert entry['status'] == 'completed', f'{entry["name"]} not completed'

    def test_workspace_cleaned_on_success_by_default(self):
        wf     = Workflow__Synth__Happy()
        ws     = Workflow__Workspace.create(wf.workflow_name(), self.tmp,
                                            workflow_version=wf.workflow_version())
        wdir   = str(ws.workspace_dir)
        runner = Workflow__Runner(workflow=wf, workspace=ws, keep_work=False)
        runner.run()
        assert not os.path.isdir(wdir)

    def test_workspace_kept_when_keep_work_true(self):
        runner = self._make_runner(Workflow__Synth__Happy(), keep_work=True)
        wdir   = str(runner.workspace.workspace_dir)
        runner.run()
        assert os.path.isdir(wdir)


# ------------------------------------------------------------------
# Tests: resume from step 2 (step-a already done)
# ------------------------------------------------------------------

class Test_Synthetic__Workflow__Resume:

    def setup_method(self):
        self.tmp = tempfile.mkdtemp()

    def teardown_method(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_resume_skips_completed_step(self):
        wf = Workflow__Synth__Happy()
        ws = Workflow__Workspace.create(wf.workflow_name(), self.tmp,
                                        workflow_version=wf.workflow_version())
        # Pre-persist step-a output so it appears already done
        step_a = Step__Synth__A()
        ws.persist_output(step_a, Schema__S1__Output(value_a='pre_done'), index=1)

        runner = Workflow__Runner(workflow=wf, workspace=ws, keep_work=True)
        result = runner.run()
        assert result.get('final') == 'result_c'

        # Verify step-a output was NOT overwritten
        data = ws.read_output_for(step_a)
        assert data.get('value_a') == 'pre_done'

    def test_resume_completes_remaining_steps(self):
        wf = Workflow__Synth__Happy()
        ws = Workflow__Workspace.create(wf.workflow_name(), self.tmp,
                                        workflow_version=wf.workflow_version())
        step_a = Step__Synth__A()
        step_b = Step__Synth__B()
        ws.persist_output(step_a, Schema__S1__Output(value_a='a'), index=1)
        ws.persist_output(step_b, Schema__S2__Output(value_b='b'), index=2)

        runner = Workflow__Runner(workflow=wf, workspace=ws, keep_work=True)
        result = runner.run()
        # Only step-c should have run; final output is step-c
        assert result.get('final') == 'result_c'


# ------------------------------------------------------------------
# Tests: abort on step failure
# ------------------------------------------------------------------

class Test_Synthetic__Workflow__Abort:

    def setup_method(self):
        self.tmp = tempfile.mkdtemp()

    def teardown_method(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_failure_raises_runtime_error(self):
        wf     = Workflow__Synth__Fail_At_B()
        ws     = Workflow__Workspace.create(wf.workflow_name(), self.tmp,
                                            workflow_version=wf.workflow_version())
        runner = Workflow__Runner(workflow=wf, workspace=ws, keep_work=True)
        with pytest.raises(RuntimeError, match='intentional failure'):
            runner.run()

    def test_manifest_status_failed_on_error(self):
        wf     = Workflow__Synth__Fail_At_B()
        ws     = Workflow__Workspace.create(wf.workflow_name(), self.tmp,
                                            workflow_version=wf.workflow_version())
        runner = Workflow__Runner(workflow=wf, workspace=ws, keep_work=True)
        with pytest.raises(RuntimeError):
            runner.run()
        manifest = ws.read_manifest()
        assert manifest['status'] == 'failed'

    def test_workspace_preserved_on_failure(self):
        wf     = Workflow__Synth__Fail_At_B()
        ws     = Workflow__Workspace.create(wf.workflow_name(), self.tmp,
                                            workflow_version=wf.workflow_version())
        wdir   = str(ws.workspace_dir)
        runner = Workflow__Runner(workflow=wf, workspace=ws, keep_work=False)
        with pytest.raises(RuntimeError):
            runner.run()
        # Workspace stays on disk even when keep_work=False, because it failed
        assert os.path.isdir(wdir)

    def test_step_before_failure_is_completed(self):
        wf     = Workflow__Synth__Fail_At_B()
        ws     = Workflow__Workspace.create(wf.workflow_name(), self.tmp,
                                            workflow_version=wf.workflow_version())
        runner = Workflow__Runner(workflow=wf, workspace=ws, keep_work=True)
        with pytest.raises(RuntimeError):
            runner.run()
        manifest = ws.read_manifest()
        assert manifest['steps'][0]['status'] == 'completed'   # step-a done
        assert manifest['steps'][1]['status'] == 'failed'       # step-fail


# ------------------------------------------------------------------
# Tests: cross-version resume refusal
# ------------------------------------------------------------------

class Test_Synthetic__Workflow__Version_Guard:

    def setup_method(self):
        self.tmp = tempfile.mkdtemp()

    def teardown_method(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_cross_major_version_refused(self):
        # Create a workspace with v1.0.0 manifest
        wf_v1 = Workflow__Synth__Happy()
        ws    = Workflow__Workspace.create(wf_v1.workflow_name(), self.tmp,
                                           workflow_version='1.0.0')
        ws.write_manifest({'workflow_name': 'synth-happy', 'workflow_version': '1.0.0',
                           'work_id': str(ws.work_id), 'started_at': '', 'steps': []})

        # Try to resume with v2.0.0
        wf_v2  = Workflow__Synth__V2()
        runner = Workflow__Runner(workflow=wf_v2, workspace=ws, keep_work=True)
        with pytest.raises(RuntimeError, match='Cannot resume'):
            runner.run()

    def test_same_major_version_allowed(self):
        wf  = Workflow__Synth__Happy()
        ws  = Workflow__Workspace.create(wf.workflow_name(), self.tmp,
                                         workflow_version='1.0.0')
        ws.write_manifest({'workflow_name': 'synth-happy', 'workflow_version': '1.2.0',
                           'work_id': str(ws.work_id), 'started_at': '', 'steps': []})

        runner = Workflow__Runner(workflow=wf, workspace=ws, keep_work=True)
        result = runner.run()  # should not raise
        assert 'final' in result


# ------------------------------------------------------------------
# Tests: atomic write
# ------------------------------------------------------------------

class Test_Synthetic__Workflow__Atomic_Write:

    def setup_method(self):
        self.tmp = tempfile.mkdtemp()

    def teardown_method(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_no_temp_files_after_persist(self):
        ws   = Workflow__Workspace.create('test', self.tmp)
        step = Step__Synth__A()
        ws.persist_output(step, Schema__S1__Output(value_a='x'), index=1)
        wdir = str(ws.workspace_dir)
        tmp_files = [f for f in os.listdir(wdir) if f.startswith('.tmp-')]
        assert len(tmp_files) == 0

    def test_atomic_write_produces_valid_json(self):
        ws   = Workflow__Workspace.create('test', self.tmp)
        step = Step__Synth__A()
        ws.persist_output(step, Schema__S1__Output(value_a='atomic'), index=1)
        data = ws.read_output_for(step)
        assert data['value_a'] == 'atomic'

    def test_manifest_atomic_write(self):
        ws = Workflow__Workspace.create('test', self.tmp)
        ws.write_manifest({'status': 'running', 'steps': []})
        data = ws.read_manifest()
        assert data['status'] == 'running'
