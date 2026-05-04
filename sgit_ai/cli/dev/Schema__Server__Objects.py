from osbot_utils.type_safe.Type_Safe                import Type_Safe
from osbot_utils.type_safe.primitives.core.Safe_Str  import Safe_Str
from osbot_utils.type_safe.primitives.core.Safe_UInt import Safe_UInt


class Schema__Server__Objects__TypeCount(Type_Safe):
    """Object count for one object type."""
    obj_type : Safe_Str = None   # e.g. 'commit', 'tree', 'blob', 'index', 'ref', 'key', 'other'
    count    : Safe_UInt


class Schema__Server__Objects(Type_Safe):
    """JSON output schema for `sgit dev server-objects`."""
    vault_id      : Safe_Str = None
    total_objects : Safe_UInt
    by_type       : list[Schema__Server__Objects__TypeCount]
    head_reachable: Safe_UInt   # objects reachable from HEAD commit (need a sparse clone)
    history_only  : Safe_UInt   # objects only reachable via history (not HEAD)
    hot_tree_ids  : list[Safe_Str]   # top-N tree IDs referenced from multiple commits
