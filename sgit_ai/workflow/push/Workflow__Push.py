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
    """6-step push workflow.

    Steps:
    1. derive_keys        — read vault_key and derive crypto keys
    2. check_clean        — abort if working copy has uncommitted changes
    3. local_inventory    — load branch info + count local-only objects
    4. fast_forward_check — fetch remote ref and verify we can push
    5. upload_objects     — upload new objects via batch API (B08 will replace with upload_pack)
    6. update_remote_ref  — write new HEAD to named branch ref on server

    B08 will insert Step__Push__Upload_Pack between fast_forward_check and
    update_remote_ref, and remove/replace upload_objects with pack-based upload.
    """
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
