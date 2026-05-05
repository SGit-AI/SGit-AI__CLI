"""Workflow__Push — 6-step push pipeline."""
from sgit_ai.safe_types.Safe_Str__Workflow_Name                       import Safe_Str__Workflow_Name
from sgit_ai.safe_types.Safe_Str__Semver                              import Safe_Str__Semver
from sgit_ai.workflow.Workflow                                         import Workflow
from sgit_ai.workflow.push.Step__Push__Derive_Keys                    import Step__Push__Derive_Keys
from sgit_ai.workflow.push.Step__Push__Check_Clean                    import Step__Push__Check_Clean
from sgit_ai.workflow.push.Step__Push__Local_Inventory                import Step__Push__Local_Inventory
from sgit_ai.workflow.push.Step__Push__Fast_Forward_Check             import Step__Push__Fast_Forward_Check
from sgit_ai.workflow.push.Step__Push__Upload_Objects                 import Step__Push__Upload_Objects
from sgit_ai.workflow.push.Step__Push__Update_Remote_Ref              import Step__Push__Update_Remote_Ref


class Workflow__Push(Workflow):
    """6-step push workflow: derive_keys → check_clean → local_inventory → fast_forward_check → upload_objects → update_remote_ref."""
    name    = Safe_Str__Workflow_Name('push')
    version = Safe_Str__Semver('1.0.0')
    steps   = [
        Step__Push__Derive_Keys,
        Step__Push__Check_Clean,
        Step__Push__Local_Inventory,
        Step__Push__Fast_Forward_Check,
        Step__Push__Upload_Objects,
        Step__Push__Update_Remote_Ref,
    ]
