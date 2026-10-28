from osbot_utils.type_safe.Type_Safe                  import Type_Safe
from osbot_utils.type_safe.primitives.core.Safe_UInt  import Safe_UInt
from sgit_ai.schemas.diff.Schema__Rename_Pair         import Schema__Rename_Pair


class Schema__Rename_Result(Type_Safe):
    pairs      : list[Schema__Rename_Pair]
    limit_hit  : bool = False                 # the inexact pass was skipped (sources x destinations over the limit)
    candidates : Safe_UInt                    # sources x destinations the inexact pass considered
    unread     : Safe_UInt                    # blobs not readable (not local, too large): exact pass only
