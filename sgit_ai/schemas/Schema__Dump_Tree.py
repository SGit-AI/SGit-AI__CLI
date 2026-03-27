from osbot_utils.type_safe.Type_Safe               import Type_Safe
from osbot_utils.type_safe.primitives.core.Safe_Str  import Safe_Str
from osbot_utils.type_safe.primitives.core.Safe_UInt import Safe_UInt


class Schema__Dump_Tree(Type_Safe):
    """Describes a single tree object decoded during tree traversal."""
    tree_id      : Safe_Str  = None   # obj-cas-imm-{hash}
    entry_count  : Safe_UInt           # number of entries in this tree
    blob_ids     : list[Safe_Str]      # blob IDs referenced by this tree (direct)
    sub_tree_ids : list[Safe_Str]      # sub-tree IDs referenced by this tree
    error        : Safe_Str  = None   # decode error if any
