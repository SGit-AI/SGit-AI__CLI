from osbot_utils.type_safe.Type_Safe                      import Type_Safe
from sgit_ai.safe_types.Enum__Doctor_Status           import Enum__Doctor_Status
from sgit_ai.safe_types.Safe_Str__Base_URL            import Safe_Str__Base_URL
from sgit_ai.safe_types.Safe_Str__ISO_Timestamp       import Safe_Str__ISO_Timestamp
from sgit_ai.safe_types.Safe_Str__Remote_Name         import Safe_Str__Remote_Name
from sgit_ai.schemas.Schema__Doctor__Check            import Schema__Doctor__Check


class Schema__Doctor__Report(Type_Safe):
    remote_name : Safe_Str__Remote_Name   = None
    remote_url  : Safe_Str__Base_URL      = None
    started_at  : Safe_Str__ISO_Timestamp = None
    overall     : Enum__Doctor_Status     = None
    checks      : list[Schema__Doctor__Check]
