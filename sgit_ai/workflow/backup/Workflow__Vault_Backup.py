from sgit_ai.safe_types.Safe_Str__Workflow_Name                        import Safe_Str__Workflow_Name
from sgit_ai.safe_types.Safe_Str__Semver                               import Safe_Str__Semver
from sgit_ai.workflow.Workflow                                         import Workflow
from sgit_ai.workflow.backup.steps.Step__Backup__Build_Zip             import Step__Backup__Build_Zip
from sgit_ai.plugins.dev.workflow.CLI__Dev__Workflow                   import register_workflow


@register_workflow
class Workflow__Vault_Backup(Workflow):
    name    = Safe_Str__Workflow_Name('backup')
    version = Safe_Str__Semver('1.0.0')
    steps   = [
        Step__Backup__Build_Zip,
    ]
