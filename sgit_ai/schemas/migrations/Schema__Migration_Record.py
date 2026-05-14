from osbot_utils.type_safe.Type_Safe                                                  import Type_Safe
from osbot_utils.type_safe.primitives.domains.identifiers.safe_int.Timestamp_Now      import Timestamp_Now
from sgit_ai.safe_types.Safe_Str__Migration_Name                                  import Safe_Str__Migration_Name
from sgit_ai.safe_types.Safe_UInt__Timestamp                                      import Safe_UInt__Timestamp


class Schema__Migration_Record(Type_Safe):
    name        : Safe_Str__Migration_Name = None
    applied_at  : Timestamp_Now            = None      # milliseconds since epoch
    duration_ms : Safe_UInt__Timestamp
    n_trees     : Safe_UInt__Timestamp                 # reuse uint — trees migrated
    n_commits   : Safe_UInt__Timestamp                 # commits rewritten
    n_refs      : Safe_UInt__Timestamp                 # refs updated
