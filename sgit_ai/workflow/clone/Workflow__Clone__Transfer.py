"""Workflow__Clone__Transfer — 5-step transfer-import pipeline."""
from sgit_ai.safe_types.Safe_Str__Workflow_Name                              import Safe_Str__Workflow_Name
from sgit_ai.safe_types.Safe_Str__Semver                                     import Safe_Str__Semver
from sgit_ai.workflow.Workflow                                               import Workflow
from sgit_ai.workflow.clone.Step__Transfer__Receive                          import Step__Transfer__Receive
from sgit_ai.workflow.clone.Step__Transfer__Check_Directory                  import Step__Transfer__Check_Directory
from sgit_ai.workflow.clone.Step__Transfer__Init_Vault                       import Step__Transfer__Init_Vault
from sgit_ai.workflow.clone.Step__Transfer__Write_Files                      import Step__Transfer__Write_Files
from sgit_ai.workflow.clone.Step__Transfer__Commit_And_Configure             import Step__Transfer__Commit_And_Configure
from sgit_ai.plugins.dev.workflow.CLI__Dev__Workflow                         import register_workflow


@register_workflow
class Workflow__Clone__Transfer(Workflow):
    name    = Safe_Str__Workflow_Name('clone-transfer')
    version = Safe_Str__Semver('1.0.0')
    steps   = [
        Step__Transfer__Receive,
        Step__Transfer__Check_Directory,
        Step__Transfer__Init_Vault,
        Step__Transfer__Write_Files,
        Step__Transfer__Commit_And_Configure,
    ]
