from osbot_utils.type_safe.Type_Safe                                                  import Type_Safe
from osbot_utils.type_safe.primitives.domains.identifiers.safe_int.Timestamp_Now      import Timestamp_Now
from sgit_ai.safe_types.Safe_Str__Secret_Key                                      import Safe_Str__Secret_Key


class Schema__Secret_Entry(Type_Safe):
    key        : Safe_Str__Secret_Key = None
    created_at : Timestamp_Now        = None       # milliseconds since epoch
