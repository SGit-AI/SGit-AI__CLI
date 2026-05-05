"""Workflow__Fetch — 4-step fetch pipeline (fetch without merge)."""
from sgit_ai.safe_types.Safe_Str__Workflow_Name                      import Safe_Str__Workflow_Name
from sgit_ai.safe_types.Safe_Str__Semver                             import Safe_Str__Semver
from sgit_ai.workflow.Workflow                                        import Workflow
from sgit_ai.workflow.fetch.Step__Fetch__Derive_Keys                 import Step__Fetch__Derive_Keys
from sgit_ai.workflow.fetch.Step__Fetch__Load_Branch_Info            import Step__Fetch__Load_Branch_Info
from sgit_ai.workflow.fetch.Step__Fetch__Fetch_Remote_Ref            import Step__Fetch__Fetch_Remote_Ref
from sgit_ai.workflow.fetch.Step__Fetch__Fetch_Missing               import Step__Fetch__Fetch_Missing


class Workflow__Fetch(Workflow):
    """4-step fetch workflow: derive_keys → load_branch_info → fetch_remote_ref → fetch_missing.

    Fetch downloads remote state without merging into the working copy.
    A subsequent sgit pull (or Workflow__Pull) performs the merge.
    Pack-based optimisation (B08) will add Step__Fetch__Download_Pack between
    fetch_remote_ref and fetch_missing when that brief lands.
    """
    name    = Safe_Str__Workflow_Name('fetch')
    version = Safe_Str__Semver('1.0.0')
    steps   = [
        Step__Fetch__Derive_Keys,
        Step__Fetch__Load_Branch_Info,
        Step__Fetch__Fetch_Remote_Ref,
        Step__Fetch__Fetch_Missing,
    ]
