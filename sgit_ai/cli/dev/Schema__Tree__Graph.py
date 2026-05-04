import re
from osbot_utils.type_safe.Type_Safe                import Type_Safe
from osbot_utils.type_safe.primitives.core.Safe_Str  import Safe_Str
from osbot_utils.type_safe.primitives.core.Safe_UInt import Safe_UInt


class Safe_Str__Ratio(Safe_Str):
    """Allows digits, decimal point, and 'x' — e.g. '1.7x'."""
    regex       = re.compile(r'[^0-9.x]')
    allow_empty = True


class Schema__Tree__Graph__DepthLevel(Type_Safe):
    """Tree count histogram entry for one depth level."""
    depth      : Safe_UInt
    tree_count : Safe_UInt   # total trees at this depth (with duplicates counted)
    unique     : Safe_UInt   # distinct tree IDs at this depth


class Schema__Tree__Graph__Commit(Type_Safe):
    """Per-commit tree stats."""
    commit_id    : Safe_Str      = None
    root_tree_id : Safe_Str      = None
    total_trees  : Safe_UInt               # all trees reachable from this commit (incl. root)
    unique_new   : Safe_UInt               # trees not seen in any earlier commit
    dedup_ratio  : Safe_Str__Ratio = None  # formatted "X.Yx" e.g. "1.0x"


class Schema__Tree__Graph(Type_Safe):
    """JSON output schema for `sgit dev tree-graph`."""
    vault_id         : Safe_Str = None
    n_commits        : Safe_UInt
    total_trees      : Safe_UInt   # all (commit, tree) pairs — with repetition
    unique_trees     : Safe_UInt   # distinct tree IDs across all commits
    head_only_trees  : Safe_UInt   # trees that would be needed for HEAD-only clone
    commits          : list[Schema__Tree__Graph__Commit]
    depth_histogram  : list[Schema__Tree__Graph__DepthLevel]
