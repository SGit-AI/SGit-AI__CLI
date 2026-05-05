"""Tests for Workflow__Push — B15 non-B08 push workflow structure."""
from sgit_ai.workflow.push.Workflow__Push                       import Workflow__Push
from sgit_ai.workflow.push.Step__Push__Derive_Keys              import Step__Push__Derive_Keys
from sgit_ai.workflow.push.Step__Push__Check_Clean              import Step__Push__Check_Clean
from sgit_ai.workflow.push.Step__Push__Local_Inventory          import Step__Push__Local_Inventory
from sgit_ai.workflow.push.Step__Push__Fast_Forward_Check       import Step__Push__Fast_Forward_Check
from sgit_ai.workflow.push.Step__Push__Upload_Objects           import Step__Push__Upload_Objects
from sgit_ai.workflow.push.Step__Push__Update_Remote_Ref        import Step__Push__Update_Remote_Ref
from sgit_ai.workflow.push.Push__Workspace                      import Push__Workspace
from sgit_ai.schemas.workflow.push.Schema__Push__State          import Schema__Push__State


class Test_Workflow__Push__Structure:

    def test_workflow_name(self):
        wf = Workflow__Push()
        assert str(wf.name) == 'push'

    def test_workflow_version(self):
        wf = Workflow__Push()
        assert str(wf.version) == '1.0.0'

    def test_workflow_has_six_steps(self):
        wf = Workflow__Push()
        assert len(wf.steps) == 6

    def test_step_order(self):
        wf = Workflow__Push()
        assert wf.steps[0] is Step__Push__Derive_Keys
        assert wf.steps[1] is Step__Push__Check_Clean
        assert wf.steps[2] is Step__Push__Local_Inventory
        assert wf.steps[3] is Step__Push__Fast_Forward_Check
        assert wf.steps[4] is Step__Push__Upload_Objects
        assert wf.steps[5] is Step__Push__Update_Remote_Ref

    def test_step_names(self):
        names = [str(cls().name) for cls in Workflow__Push.steps]
        assert names == ['derive-keys', 'check-clean', 'local-inventory',
                         'fast-forward-check', 'upload-objects', 'update-remote-ref']

    def test_step_schemas(self):
        for cls in Workflow__Push.steps:
            assert cls.input_schema  is Schema__Push__State
            assert cls.output_schema is Schema__Push__State

    def test_check_clean_before_upload(self):
        """Ensure the clean check comes before any upload steps."""
        wf    = Workflow__Push()
        names = [str(cls().name) for cls in wf.steps]
        assert names.index('check-clean') < names.index('upload-objects')

    def test_fast_forward_check_before_upload(self):
        names = [str(cls().name) for cls in Workflow__Push.steps]
        assert names.index('fast-forward-check') < names.index('upload-objects')


class Test_Push__Workspace:

    def test_workspace_instantiates(self):
        ws = Push__Workspace()
        assert ws.sync_client is None
        assert ws.storage is None

    def test_progress_noop_without_callback(self):
        ws = Push__Workspace()
        ws.progress('step', 'test')


class Test_Schema__Push__State:

    def test_schema_instantiates(self):
        s = Schema__Push__State()
        assert s.vault_key is None
        assert s.force is False

    def test_can_fast_forward_default(self):
        s = Schema__Push__State()
        assert s.can_fast_forward is False

    def test_remote_ref_updated_default(self):
        s = Schema__Push__State()
        assert s.remote_ref_updated is False

    def test_working_copy_clean_default(self):
        s = Schema__Push__State()
        assert s.working_copy_clean is False
