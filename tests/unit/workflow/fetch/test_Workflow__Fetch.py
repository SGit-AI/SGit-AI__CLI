"""Tests for Workflow__Fetch — B15 non-B08 fetch workflow structure."""
from sgit_ai.workflow.fetch.Workflow__Fetch                   import Workflow__Fetch
from sgit_ai.workflow.fetch.Step__Fetch__Derive_Keys          import Step__Fetch__Derive_Keys
from sgit_ai.workflow.fetch.Step__Fetch__Load_Branch_Info     import Step__Fetch__Load_Branch_Info
from sgit_ai.workflow.fetch.Step__Fetch__Fetch_Remote_Ref     import Step__Fetch__Fetch_Remote_Ref
from sgit_ai.workflow.fetch.Step__Fetch__Fetch_Missing        import Step__Fetch__Fetch_Missing
from sgit_ai.workflow.fetch.Fetch__Workspace                  import Fetch__Workspace
from sgit_ai.schemas.workflow.fetch.Schema__Fetch__State      import Schema__Fetch__State


class Test_Workflow__Fetch__Structure:

    def test_workflow_name(self):
        wf = Workflow__Fetch()
        assert str(wf.name) == 'fetch'

    def test_workflow_version(self):
        wf = Workflow__Fetch()
        assert str(wf.version) == '1.0.0'

    def test_workflow_has_four_steps(self):
        wf = Workflow__Fetch()
        assert len(wf.steps) == 4

    def test_step_order(self):
        wf = Workflow__Fetch()
        assert wf.steps[0] is Step__Fetch__Derive_Keys
        assert wf.steps[1] is Step__Fetch__Load_Branch_Info
        assert wf.steps[2] is Step__Fetch__Fetch_Remote_Ref
        assert wf.steps[3] is Step__Fetch__Fetch_Missing

    def test_step_names(self):
        names = [str(cls().name) for cls in Workflow__Fetch.steps]
        assert names == ['derive-keys', 'load-branch-info', 'fetch-remote-ref', 'fetch-missing']

    def test_step_schemas(self):
        for cls in Workflow__Fetch.steps:
            assert cls.input_schema  is Schema__Fetch__State
            assert cls.output_schema is Schema__Fetch__State

    def test_fetch_is_subset_of_pull(self):
        """Fetch workflow has no merge step — it stops after downloading objects."""
        wf    = Workflow__Fetch()
        names = [str(cls().name) for cls in wf.steps]
        assert 'merge' not in names


class Test_Fetch__Workspace:

    def test_workspace_instantiates(self):
        ws = Fetch__Workspace()
        assert ws.sync_client is None
        assert ws.storage is None

    def test_progress_noop_without_callback(self):
        ws = Fetch__Workspace()
        ws.progress('step', 'test')


class Test_Schema__Fetch__State:

    def test_schema_instantiates(self):
        s = Schema__Fetch__State()
        assert s.vault_key is None

    def test_remote_reachable_default(self):
        s = Schema__Fetch__State()
        assert s.remote_reachable is True
