from osbot_utils.type_safe.Type_Safe                         import Type_Safe
from sgit_ai.safe_types.Safe_Str__Workflow_Name              import Safe_Str__Workflow_Name
from sgit_ai.safe_types.Safe_Str__Work_Id                    import Safe_Str__Work_Id
from sgit_ai.safe_types.Safe_Str__Semver                     import Safe_Str__Semver
from sgit_ai.safe_types.Safe_Str__ISO_Timestamp              import Safe_Str__ISO_Timestamp
from sgit_ai.safe_types.Enum__Workflow_Status                import Enum__Workflow_Status
from sgit_ai.safe_types.Safe_Str__Error_Message              import Safe_Str__Error_Message
from sgit_ai.schemas.workflow.Schema__Workflow_Step_Entry    import Schema__Workflow_Step_Entry


class Schema__Workflow_Manifest(Type_Safe):
    workflow_name    : Safe_Str__Workflow_Name
    workflow_version : Safe_Str__Semver        = None
    work_id          : Safe_Str__Work_Id
    started_at       : Safe_Str__ISO_Timestamp = None
    completed_at     : Safe_Str__ISO_Timestamp = None
    status           : Enum__Workflow_Status   = Enum__Workflow_Status.PENDING
    keep_work        : bool                    = False
    steps            : list[Schema__Workflow_Step_Entry]
    error            : Safe_Str__Error_Message = None
