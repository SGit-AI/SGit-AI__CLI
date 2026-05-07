"""Workflow__Vault_Move — 8-step vault move/key-rotation pipeline."""
from sgit_ai.safe_types.Safe_Str__Workflow_Name                             import Safe_Str__Workflow_Name
from sgit_ai.safe_types.Safe_Str__Semver                                    import Safe_Str__Semver
from sgit_ai.workflow.Workflow                                              import Workflow
from sgit_ai.workflow.move.steps.Step__Move__Validate_Local                 import Step__Move__Validate_Local
from sgit_ai.workflow.move.steps.Step__Move__Derive_New_Keys                import Step__Move__Derive_New_Keys
from sgit_ai.workflow.move.steps.Step__Move__Build_Temp_Vault               import Step__Move__Build_Temp_Vault
from sgit_ai.workflow.move.steps.Step__Move__Write_Sentinel_Commits         import Step__Move__Write_Sentinel_Commits
from sgit_ai.workflow.move.steps.Step__Move__Push_To_Target                 import Step__Move__Push_To_Target
from sgit_ai.workflow.move.steps.Step__Move__Verify_Target                  import Step__Move__Verify_Target
from sgit_ai.workflow.move.steps.Step__Move__Backup_Old_Vault               import Step__Move__Backup_Old_Vault
from sgit_ai.workflow.move.steps.Step__Move__Delete_Source                  import Step__Move__Delete_Source
from sgit_ai.plugins.dev.workflow.CLI__Dev__Workflow                        import register_workflow


@register_workflow
class Workflow__Vault_Move(Workflow):
    name    = Safe_Str__Workflow_Name('vault-move')
    version = Safe_Str__Semver('1.0.0')
    steps   = [
        Step__Move__Validate_Local,
        Step__Move__Derive_New_Keys,
        Step__Move__Build_Temp_Vault,
        Step__Move__Write_Sentinel_Commits,
        Step__Move__Push_To_Target,
        Step__Move__Verify_Target,
        Step__Move__Backup_Old_Vault,
        Step__Move__Delete_Source,
    ]
