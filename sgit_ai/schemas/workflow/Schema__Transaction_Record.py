from osbot_utils.type_safe.Type_Safe              import Type_Safe
from sgit_ai.safe_types.Safe_Str__Semver          import Safe_Str__Semver
from sgit_ai.safe_types.Safe_Str__Workflow_Name   import Safe_Str__Workflow_Name
from sgit_ai.safe_types.Safe_Str__Work_Id         import Safe_Str__Work_Id
from sgit_ai.safe_types.Safe_Str__ISO_Timestamp   import Safe_Str__ISO_Timestamp
from sgit_ai.safe_types.Safe_UInt__Timestamp      import Safe_UInt__Timestamp
from sgit_ai.safe_types.Enum__Workflow_Status     import Enum__Workflow_Status
from sgit_ai.safe_types.Safe_Str__Vault_Id        import Safe_Str__Vault_Id
from sgit_ai.safe_types.Safe_Str__Branch_Name     import Safe_Str__Branch_Name
from sgit_ai.safe_types.Safe_Str__Commit_Id       import Safe_Str__Commit_Id
from sgit_ai.safe_types.Safe_Str__Error_Message   import Safe_Str__Error_Message
from sgit_ai.schemas.workflow.Schema__Step_Summary import Schema__Step_Summary


class Schema__Transaction_Record(Type_Safe):
    record_version   : Safe_Str__Semver        = None
    workflow_name    : Safe_Str__Workflow_Name
    workflow_version : Safe_Str__Semver        = None
    work_id          : Safe_Str__Work_Id
    started_at       : Safe_Str__ISO_Timestamp = None
    completed_at     : Safe_Str__ISO_Timestamp = None
    duration_ms      : Safe_UInt__Timestamp
    status           : Enum__Workflow_Status   = Enum__Workflow_Status.PENDING
    vault_id         : Safe_Str__Vault_Id      = None
    branch_name      : Safe_Str__Branch_Name   = None
    parent_commit    : Safe_Str__Commit_Id     = None
    new_commit       : Safe_Str__Commit_Id     = None
    steps_summary    : list[Schema__Step_Summary]
    error            : Safe_Str__Error_Message = None
