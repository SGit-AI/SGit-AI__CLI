from osbot_utils.type_safe.Type_Safe                                                  import Type_Safe
from osbot_utils.type_safe.primitives.domains.identifiers.safe_int.Timestamp_Now      import Timestamp_Now
from sgit_ai.safe_types.Enum__Doctor_Status                                       import Enum__Doctor_Status
from sgit_ai.safe_types.Safe_Str__Base_URL                                        import Safe_Str__Base_URL
from sgit_ai.safe_types.Safe_Str__Remote_Name                                     import Safe_Str__Remote_Name
from sgit_ai.schemas.Schema__Doctor__Check                                        import Schema__Doctor__Check


class Schema__Doctor__Report(Type_Safe):
    remote_name : Safe_Str__Remote_Name = None
    remote_url  : Safe_Str__Base_URL    = None
    started_at  : Timestamp_Now         = None       # milliseconds since epoch
    overall     : Enum__Doctor_Status   = None
    checks      : list[Schema__Doctor__Check]
