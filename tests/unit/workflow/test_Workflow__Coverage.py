"""Coverage gap-fill for Workflow.py and Workflow__Workspace.py.

All tests are purely local (filesystem + in-memory) — no network, no crypto,
completes in well under 100 ms each.
"""
import os
import shutil
import tempfile

import pytest

from osbot_utils.type_safe.Type_Safe             import Type_Safe
from osbot_utils.type_safe.primitives.core.Safe_Str import Safe_Str
from sgit_ai.safe_types.Safe_Str__Step_Name      import Safe_Str__Step_Name
from sgit_ai.safe_types.Safe_Str__Workflow_Name  import Safe_Str__Workflow_Name
from sgit_ai.safe_types.Safe_Str__Semver         import Safe_Str__Semver
from sgit_ai.workflow.Step                       import Step
from sgit_ai.workflow.Workflow                   import Workflow
from sgit_ai.workflow.Workflow__Workspace        import Workflow__Workspace


# ── minimal schemas & steps ────────────────────────────────────────────────

class Schema__Cov(Type_Safe):
    value : Safe_Str = None

class _StepCov(Step):
    name          = Safe_Str__Step_Name('cov-step')
    input_schema  = Schema__Cov
    output_schema = Schema__Cov
    def execute(self, input, workspace):
        return Schema__Cov(value='done')

class _StepNoSchema(Step):
    name          = Safe_Str__Step_Name('no-schema-step')
    input_schema  = None
    output_schema = None
    def execute(self, input, workspace):
        return Schema__Cov(value='no-schema')

class _WorkflowCov(Workflow):
    name    = Safe_Str__Workflow_Name('cov-wf')
    version = Safe_Str__Semver('1.0.0')
    steps   = [_StepCov]


# ── Workflow.py coverage ───────────────────────────────────────────────────

class Test_Workflow__Name_Fallback:

    def test_workflow_name_returns_class_name_when_none(self):
        """Line 18: name=None → class name fallback."""
        class Unnamed(Workflow):
            steps = []
        assert Unnamed().workflow_name() == 'Unnamed'

    def test_workflow_version_returns_default_when_none(self):
        class Unversioned(Workflow):
            steps = []
        assert Unversioned().workflow_version() == '1.0.0'


class Test_Workflow__Execute:
    """Lines 30-41: Workflow.execute() called directly (not via Runner)."""

    def setup_method(self):
        self.tmp = tempfile.mkdtemp()

    def teardown_method(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_execute_runs_step_and_returns_final_output(self):
        wf    = _WorkflowCov()
        ws    = Workflow__Workspace.create('cov-wf', self.tmp)
        inp   = Schema__Cov(value='in')
        result = wf.execute(inp, ws)
        assert result.get('value') == 'done'

    def test_execute_skips_done_step(self):
        """is_done() returns True → loads output from workspace, doesn't re-execute."""
        wf   = _WorkflowCov()
        ws   = Workflow__Workspace.create('cov-wf', self.tmp)
        step = _StepCov()
        ws.persist_output(step, Schema__Cov(value='predone'), index=1)
        result = wf.execute(Schema__Cov(value='ignored'), ws)
        assert result.get('value') == 'predone'

    def test_execute_with_multi_step_chain(self):
        class _StepB(Step):
            name          = Safe_Str__Step_Name('step-b')
            input_schema  = Schema__Cov
            output_schema = Schema__Cov
            def execute(self, input, workspace):
                return Schema__Cov(value='bout')

        class _TwoStepWf(Workflow):
            steps = [_StepCov, _StepB]

        ws     = Workflow__Workspace.create('two-step', self.tmp)
        result = _TwoStepWf().execute(Schema__Cov(value='start'), ws)
        assert result.get('value') == 'bout'


# ── Workflow__Workspace.py coverage ───────────────────────────────────────

class Test_Workflow__Workspace__Coverage:

    def setup_method(self):
        self.tmp = tempfile.mkdtemp()

    def teardown_method(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    # Lines 68-72: _step_path(step, index=None) glob fallback
    def test_step_path_without_index_finds_existing_file(self):
        ws   = Workflow__Workspace.create('test', self.tmp)
        step = _StepCov()
        ws.persist_output(step, Schema__Cov(value='x'), index=3)
        found = ws._step_path(step)   # index=None → glob
        assert found.endswith('.json')
        assert os.path.isfile(found)

    def test_step_path_without_index_returns_default_when_no_file(self):
        ws   = Workflow__Workspace.create('test', self.tmp)
        step = _StepCov()
        path = ws._step_path(step)    # index=None, no file → default
        assert path.endswith('__cov-step.json')

    # Lines 91-95: gather_input_for() with a schema
    def test_gather_input_for_returns_schema_instance(self):
        ws   = Workflow__Workspace.create('test', self.tmp)
        step = _StepCov()             # input_schema = Schema__Cov
        inp  = ws.gather_input_for(step)
        assert isinstance(inp, Schema__Cov)

    def test_gather_input_for_returns_none_when_no_schema(self):
        ws   = Workflow__Workspace.create('test', self.tmp)
        step = _StepNoSchema()        # input_schema = None
        assert ws.gather_input_for(step) is None

    # Lines 101, 107-108: load_output_schema_for() FileNotFoundError path
    def test_load_output_schema_for_returns_empty_schema_when_no_file(self):
        ws   = Workflow__Workspace.create('test', self.tmp)
        step = _StepCov()
        result = ws.load_output_schema_for(step)  # no file → except → schema()
        assert isinstance(result, Schema__Cov)

    def test_load_output_schema_for_returns_none_when_no_output_schema(self):
        ws   = Workflow__Workspace.create('test', self.tmp)
        step = _StepNoSchema()        # output_schema = None
        assert ws.load_output_schema_for(step) is None

    # Line 118: read_output_for() FileNotFoundError
    def test_read_output_for_raises_when_no_file(self):
        ws   = Workflow__Workspace.create('test', self.tmp)
        step = _StepCov()
        with pytest.raises(FileNotFoundError):
            ws.read_output_for(step)

    # Line 125: final_output() with empty workspace
    def test_final_output_returns_empty_dict_when_no_steps(self):
        ws = Workflow__Workspace.create('test', self.tmp)
        assert ws.final_output() == {}

    # Lines 167-172: _atomic_write exception cleanup
    def test_atomic_write_cleans_up_temp_on_rename_failure(self, monkeypatch):
        ws   = Workflow__Workspace.create('test', self.tmp)
        wdir = str(ws.workspace_dir)

        def bad_rename(src, dst):
            raise OSError('rename blocked')

        monkeypatch.setattr(os, 'rename', bad_rename)
        with pytest.raises(OSError, match='rename blocked'):
            ws._atomic_write(os.path.join(wdir, 'x.json'), '{}')
        # No leftover .tmp- files
        tmp_files = [f for f in os.listdir(wdir) if f.startswith('.tmp-')]
        assert len(tmp_files) == 0

    def test_atomic_write_reraises_even_when_unlink_fails(self, monkeypatch):
        ws   = Workflow__Workspace.create('test', self.tmp)
        wdir = str(ws.workspace_dir)

        monkeypatch.setattr(os, 'rename', lambda s, d: (_ for _ in ()).throw(OSError('rename blocked')))
        monkeypatch.setattr(os, 'unlink', lambda p: (_ for _ in ()).throw(OSError('unlink blocked')))
        with pytest.raises(OSError, match='rename blocked'):
            ws._atomic_write(os.path.join(wdir, 'x.json'), '{}')
