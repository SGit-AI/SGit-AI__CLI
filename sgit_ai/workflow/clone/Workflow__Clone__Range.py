"""Workflow__Clone__Range — clone a specific commit range (range_from..range_to)."""
from sgit_ai.safe_types.Safe_Str__Workflow_Name                        import Safe_Str__Workflow_Name
from sgit_ai.safe_types.Safe_Str__Semver                               import Safe_Str__Semver
from sgit_ai.workflow.Workflow                                          import Workflow
from sgit_ai.workflow.clone.Step__Clone__Derive_Keys                    import Step__Clone__Derive_Keys
from sgit_ai.workflow.clone.Step__Clone__Check_Directory                import Step__Clone__Check_Directory
from sgit_ai.workflow.clone.Step__Clone__Download_Index                 import Step__Clone__Download_Index
from sgit_ai.workflow.clone.Step__Clone__Download_Branch_Meta           import Step__Clone__Download_Branch_Meta
from sgit_ai.workflow.clone.Step__Clone__Walk_Commits__Range            import Step__Clone__Walk_Commits__Range
from sgit_ai.workflow.clone.Step__Clone__Walk_Trees                     import Step__Clone__Walk_Trees
from sgit_ai.workflow.clone.Step__Clone__Download_Blobs                 import Step__Clone__Download_Blobs
from sgit_ai.workflow.clone.Step__Clone__Create_Clone_Branch            import Step__Clone__Create_Clone_Branch
from sgit_ai.workflow.clone.Step__Clone__Extract_Working_Copy           import Step__Clone__Extract_Working_Copy
from sgit_ai.workflow.clone.Step__Clone__Setup_Local_Config             import Step__Clone__Setup_Local_Config
from sgit_ai.plugins.dev.workflow.CLI__Dev__Workflow                    import register_workflow


@register_workflow
class Workflow__Clone__Range(Workflow):
    """Clone only commits/trees/blobs within a given range (range_from..range_to)."""
    name    = Safe_Str__Workflow_Name('clone-range')
    version = Safe_Str__Semver('1.0.0')
    steps   = [
        Step__Clone__Derive_Keys,
        Step__Clone__Check_Directory,
        Step__Clone__Download_Index,
        Step__Clone__Download_Branch_Meta,
        Step__Clone__Walk_Commits__Range,
        Step__Clone__Walk_Trees,
        Step__Clone__Download_Blobs,
        Step__Clone__Create_Clone_Branch,
        Step__Clone__Extract_Working_Copy,
        Step__Clone__Setup_Local_Config,
    ]
