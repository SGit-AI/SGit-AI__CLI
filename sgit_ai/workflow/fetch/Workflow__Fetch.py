"""Workflow__Fetch — 4-step fetch pipeline (fetch without merge)."""
from sgit_ai.safe_types.Safe_Str__Workflow_Name                      import Safe_Str__Workflow_Name
from sgit_ai.safe_types.Safe_Str__Semver                             import Safe_Str__Semver
from sgit_ai.workflow.Workflow                                        import Workflow
from sgit_ai.workflow.fetch.Step__Fetch__Derive_Keys                 import Step__Fetch__Derive_Keys
from sgit_ai.workflow.fetch.Step__Fetch__Load_Branch_Info            import Step__Fetch__Load_Branch_Info
from sgit_ai.workflow.fetch.Step__Fetch__Fetch_Remote_Ref            import Step__Fetch__Fetch_Remote_Ref
from sgit_ai.workflow.fetch.Step__Fetch__Fetch_Missing               import Step__Fetch__Fetch_Missing
from sgit_ai.plugins.dev.workflow.CLI__Dev__Workflow                 import register_workflow


@register_workflow
class Workflow__Fetch(Workflow):
    """4-step fetch workflow: derive_keys → load_branch_info → fetch_remote_ref → fetch_missing."""
    name    = Safe_Str__Workflow_Name('fetch')
    version = Safe_Str__Semver('1.0.0')
    steps   = [
        Step__Fetch__Derive_Keys,
        Step__Fetch__Load_Branch_Info,
        Step__Fetch__Fetch_Remote_Ref,
        Step__Fetch__Fetch_Missing,
    ]
