from osbot_utils.type_safe.Type_Safe             import Type_Safe
from sgit_ai.safe_types.Safe_Str__Step_Name      import Safe_Str__Step_Name
from sgit_ai.safe_types.Enum__Step_Status        import Enum__Step_Status
from sgit_ai.safe_types.Safe_UInt__Timestamp     import Safe_UInt__Timestamp


class Schema__Step_Summary(Type_Safe):
    name        : Safe_Str__Step_Name
    status      : Enum__Step_Status   = Enum__Step_Status.PENDING
    duration_ms : Safe_UInt__Timestamp
    bytes_in    : Safe_UInt__Timestamp = None
    bytes_out   : Safe_UInt__Timestamp = None
