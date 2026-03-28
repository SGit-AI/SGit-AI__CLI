from osbot_utils.type_safe.Type_Safe               import Type_Safe
from osbot_utils.type_safe.primitives.core.Safe_Str  import Safe_Str
from osbot_utils.type_safe.primitives.core.Safe_UInt import Safe_UInt


class Schema__Dump_Diff(Type_Safe):
    """Result of comparing two Schema__Dump_Result snapshots (diff-state)."""

    # Source labels for display
    label_a : Safe_Str = None   # e.g. 'local' or path to dump file
    label_b : Safe_Str = None   # e.g. 'remote' or path to dump file

    # Refs that differ between A and B
    refs_only_in_a   : list[Safe_Str]   # ref IDs present in A but not B
    refs_only_in_b   : list[Safe_Str]   # ref IDs present in B but not A
    refs_diverged    : list[Safe_Str]   # ref IDs present in both but pointing to different commits

    # Objects
    objects_only_in_a : list[Safe_Str]  # object IDs in A but not in B
    objects_only_in_b : list[Safe_Str]  # object IDs in B but not in A

    # Branch metadata differences (branch_ids where something differs)
    branches_only_in_a   : list[Safe_Str]
    branches_only_in_b   : list[Safe_Str]
    branches_head_differ : list[Safe_Str]  # branch_ids where head_commit differs

    # Dangling objects on either side
    dangling_in_a : list[Safe_Str]
    dangling_in_b : list[Safe_Str]

    # Commit chain divergence: commits reachable from A but not B (and vice versa)
    commits_only_in_a : list[Safe_Str]
    commits_only_in_b : list[Safe_Str]

    # Counts (for quick summary)
    total_diffs         : Safe_UInt
    refs_diff_count     : Safe_UInt
    objects_diff_count  : Safe_UInt
    branches_diff_count : Safe_UInt

    # Whether the two dumps are identical
    identical : bool = False
