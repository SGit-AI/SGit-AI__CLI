"""Tests for Workflow__Pull — B15 non-B08 pull workflow structure."""
import pytest

from sgit_ai.workflow.pull.Workflow__Pull                  import Workflow__Pull
from sgit_ai.workflow.pull.Step__Pull__Derive_Keys         import Step__Pull__Derive_Keys
from sgit_ai.workflow.pull.Step__Pull__Load_Branch_Info    import Step__Pull__Load_Branch_Info
from sgit_ai.workflow.pull.Step__Pull__Fetch_Remote_Ref    import Step__Pull__Fetch_Remote_Ref
from sgit_ai.workflow.pull.Step__Pull__Fetch_Missing       import Step__Pull__Fetch_Missing
from sgit_ai.workflow.pull.Step__Pull__Merge               import Step__Pull__Merge
from sgit_ai.workflow.pull.Pull__Workspace                 import Pull__Workspace
from sgit_ai.schemas.workflow.pull.Schema__Pull__State     import Schema__Pull__State


class Test_Workflow__Pull__Structure:

    def test_workflow_name(self):
        wf = Workflow__Pull()
        assert str(wf.name) == 'pull'

    def test_workflow_version(self):
        wf = Workflow__Pull()
        assert str(wf.version) == '1.0.0'

    def test_workflow_has_five_steps(self):
        wf = Workflow__Pull()
        assert len(wf.steps) == 5

    def test_step_order(self):
        wf = Workflow__Pull()
        assert wf.steps[0] is Step__Pull__Derive_Keys
        assert wf.steps[1] is Step__Pull__Load_Branch_Info
        assert wf.steps[2] is Step__Pull__Fetch_Remote_Ref
        assert wf.steps[3] is Step__Pull__Fetch_Missing
        assert wf.steps[4] is Step__Pull__Merge

    def test_step_names(self):
        names = [str(cls().name) for cls in Workflow__Pull.steps]
        assert names == ['derive-keys', 'load-branch-info', 'fetch-remote-ref',
                         'fetch-missing', 'merge']

    def test_step_input_schema(self):
        for cls in Workflow__Pull.steps:
            assert cls.input_schema is Schema__Pull__State

    def test_step_output_schema(self):
        for cls in Workflow__Pull.steps:
            assert cls.output_schema is Schema__Pull__State


class Test_Pull__Workspace:

    def test_workspace_is_instantiable(self):
        ws = Pull__Workspace()
        assert ws.sync_client is None
        assert ws.storage is None

    def test_workspace_progress_noop_without_callback(self):
        ws = Pull__Workspace()
        ws.progress('step', 'test')   # must not raise


class Test_Schema__Pull__State:

    def test_schema_instantiates(self):
        s = Schema__Pull__State()
        assert s.vault_key is None
        assert s.directory is None

    def test_merge_status_default(self):
        s = Schema__Pull__State()
        assert s.merge_status is None

    def test_remote_reachable_default(self):
        s = Schema__Pull__State()
        assert s.remote_reachable is True

    def test_fields_populated(self):
        from sgit_ai.safe_types.Safe_Str__Vault_Key   import Safe_Str__Vault_Key
        from sgit_ai.safe_types.Safe_Str__File_Path   import Safe_Str__File_Path
        s = Schema__Pull__State(
            vault_key = Safe_Str__Vault_Key('pass:vlt01'),
            directory = Safe_Str__File_Path('/tmp/test'),
        )
        assert str(s.vault_key) == 'pass:vlt01'
        assert str(s.directory) == '/tmp/test'
