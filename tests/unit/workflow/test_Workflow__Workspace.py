"""Tests for Workflow__Workspace — on-disk state management."""
import json
import os
import shutil
import tempfile

import pytest

from sgit_ai.workflow.Workflow__Workspace              import Workflow__Workspace
from sgit_ai.workflow.Step                             import Step
from sgit_ai.safe_types.Safe_Str__Step_Name            import Safe_Str__Step_Name
from osbot_utils.type_safe.Type_Safe                   import Type_Safe
from osbot_utils.type_safe.primitives.core.Safe_Str    import Safe_Str


class Schema__Out(Type_Safe):
    result : Safe_Str = None


class _NamedStep(Step):
    name          = Safe_Str__Step_Name('my-step')
    input_schema  = None
    output_schema = Schema__Out

    def execute(self, input, workspace):
        return Schema__Out(result='ok')


class Test_Workflow__Workspace:

    def setup_method(self):
        self.tmp = tempfile.mkdtemp()

    def teardown_method(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_create_makes_directory(self):
        ws = Workflow__Workspace.create('clone', self.tmp)
        assert os.path.isdir(str(ws.workspace_dir))

    def test_create_populates_fields(self):
        ws = Workflow__Workspace.create('clone', self.tmp)
        assert str(ws.workflow_name) == 'clone'
        assert ws.work_id is not None
        assert ws.started_at is not None
        assert str(ws.workflow_version) == '1.0.0'

    def test_has_output_for_returns_false_initially(self):
        ws   = Workflow__Workspace.create('clone', self.tmp)
        step = _NamedStep()
        assert ws.has_output_for(step) is False

    def test_persist_output_creates_file(self):
        ws   = Workflow__Workspace.create('clone', self.tmp)
        step = _NamedStep()
        out  = Schema__Out(result='hello')
        ws.persist_output(step, out, index=1)
        assert ws.has_output_for(step) is True

    def test_persist_output_is_atomic(self):
        """Verify temp file is cleaned up and only the final file exists."""
        ws   = Workflow__Workspace.create('clone', self.tmp)
        step = _NamedStep()
        ws.persist_output(step, Schema__Out(result='x'), index=1)
        ws.persist_output(step, Schema__Out(result='final'), index=1)
        wdir = str(ws.workspace_dir)
        tmp_files = [f for f in os.listdir(wdir) if f.startswith('.tmp-')]
        assert len(tmp_files) == 0

    def test_read_output_for_returns_dict(self):
        ws   = Workflow__Workspace.create('clone', self.tmp)
        step = _NamedStep()
        ws.persist_output(step, Schema__Out(result='data'), index=1)
        data = ws.read_output_for(step)
        assert data.get('result') == 'data'

    def test_final_output_returns_last_step(self):
        ws    = Workflow__Workspace.create('clone', self.tmp)
        step1 = _NamedStep()
        ws.persist_output(step1, Schema__Out(result='step1-out'), index=1)

        class Step2(_NamedStep):
            name = Safe_Str__Step_Name('step2')
        step2 = Step2()
        ws.persist_output(step2, Schema__Out(result='step2_out'), index=2)
        final = ws.final_output()
        assert final.get('result') == 'step2_out'

    def test_write_and_read_manifest(self):
        ws = Workflow__Workspace.create('clone', self.tmp)
        ws.write_manifest({'status': 'running', 'steps': []})
        data = ws.read_manifest()
        assert data['status'] == 'running'

    def test_load_from_existing_workspace(self):
        ws  = Workflow__Workspace.create('push', self.tmp)
        wdir = str(ws.workspace_dir)
        ws.write_manifest({'workflow_name': 'push', 'work_id': str(ws.work_id),
                           'workflow_version': '1.0.0', 'started_at': str(ws.started_at)})
        loaded = Workflow__Workspace.load(wdir)
        assert str(loaded.workflow_name) == 'push'

    def test_load_raises_if_no_manifest(self):
        missing = os.path.join(self.tmp, 'nonexistent')
        os.makedirs(missing)
        with pytest.raises(FileNotFoundError):
            Workflow__Workspace.load(missing)

    def test_cleanup_removes_directory(self):
        ws   = Workflow__Workspace.create('clone', self.tmp)
        wdir = str(ws.workspace_dir)
        assert os.path.isdir(wdir)
        ws.cleanup()
        assert not os.path.isdir(wdir)
