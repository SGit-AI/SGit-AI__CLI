from osbot_utils.type_safe.Type_Safe                                                   import Type_Safe
from osbot_utils.type_safe.primitives.core.Safe_Str                                    import Safe_Str
from osbot_utils.type_safe.primitives.core.Safe_UInt                                   import Safe_UInt
from osbot_utils.type_safe.primitives.domains.identifiers.safe_str.Safe_Str__Id        import Safe_Str__Id


class Schema__Dump_Branch(Type_Safe):
    """Describes one branch from the branch index."""
    branch_id   : Safe_Str__Id = None
    name        : Safe_Str     = None
    branch_type : Safe_Str     = None   # 'named' or 'clone'
    head_ref_id : Safe_Str__Id = None
    head_commit : Safe_Str__Id = None   # resolved commit ID (None if unresolvable)
    created_at  : Safe_UInt             # timestamp_ms
