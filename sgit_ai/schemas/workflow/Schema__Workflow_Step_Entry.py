from osbot_utils.type_safe.Type_Safe           import Type_Safe
from sgit_ai.safe_types.Safe_Str__Step_Name    import Safe_Str__Step_Name
from sgit_ai.safe_types.Enum__Step_Status      import Enum__Step_Status
from sgit_ai.safe_types.Safe_UInt__Timestamp   import Safe_UInt__Timestamp
from sgit_ai.safe_types.Safe_Str__ISO_Timestamp import Safe_Str__ISO_Timestamp


class Schema__Workflow_Step_Entry(Type_Safe):
    step_index  : Safe_UInt__Timestamp        # ordinal within the workflow
    name        : Safe_Str__Step_Name
    status      : Enum__Step_Status           = Enum__Step_Status.PENDING
    started_at  : Safe_Str__ISO_Timestamp     = None
    completed_at: Safe_Str__ISO_Timestamp     = None
    duration_ms : Safe_UInt__Timestamp
