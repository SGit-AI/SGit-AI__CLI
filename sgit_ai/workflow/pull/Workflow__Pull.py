"""Workflow__Pull — 5-step pull pipeline (fetch + merge without server packs)."""
from sgit_ai.safe_types.Safe_Str__Workflow_Name                    import Safe_Str__Workflow_Name
from sgit_ai.safe_types.Safe_Str__Semver                           import Safe_Str__Semver
from sgit_ai.workflow.Workflow                                      import Workflow
from sgit_ai.workflow.pull.Step__Pull__Derive_Keys                 import Step__Pull__Derive_Keys
from sgit_ai.workflow.pull.Step__Pull__Load_Branch_Info            import Step__Pull__Load_Branch_Info
from sgit_ai.workflow.pull.Step__Pull__Fetch_Remote_Ref            import Step__Pull__Fetch_Remote_Ref
from sgit_ai.workflow.pull.Step__Pull__Fetch_Missing               import Step__Pull__Fetch_Missing
from sgit_ai.workflow.pull.Step__Pull__Merge                       import Step__Pull__Merge


class Workflow__Pull(Workflow):
    """5-step pull workflow: derive_keys → load_branch_info → fetch_remote_ref → fetch_missing → merge.

    Pack-based download optimisation (B08) will insert a Step__Pull__Download_Pack
    between fetch_remote_ref and merge when that brief lands.
    """
    name    = Safe_Str__Workflow_Name('pull')
    version = Safe_Str__Semver('1.0.0')
    steps   = [
        Step__Pull__Derive_Keys,
        Step__Pull__Load_Branch_Info,
        Step__Pull__Fetch_Remote_Ref,
        Step__Pull__Fetch_Missing,
        Step__Pull__Merge,
    ]
