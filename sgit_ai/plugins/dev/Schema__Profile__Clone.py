from osbot_utils.type_safe.Type_Safe                import Type_Safe
from osbot_utils.type_safe.primitives.core.Safe_Str  import Safe_Str
from osbot_utils.type_safe.primitives.core.Safe_UInt import Safe_UInt
from sgit_ai.safe_types.Safe_Str__Vault_Path         import Safe_Str__Vault_Path


class Schema__Profile__Clone__Phase(Type_Safe):
    """Wall-clock timing for one phase of the clone operation."""
    name       : Safe_Str   = None   # e.g. 'commits', 'trees', 'blobs', 'checkout'
    duration_ms: Safe_UInt           # wall-clock in milliseconds
    count      : Safe_UInt           # number of objects downloaded in this phase


class Schema__Profile__Clone(Type_Safe):
    """JSON output schema for `sgit dev profile clone`."""
    vault_id      : Safe_Str         = None
    directory     : Safe_Str__Vault_Path = None
    sparse        : Safe_UInt          # 1 = sparse, 0 = full
    total_ms      : Safe_UInt
    n_commits     : Safe_UInt
    n_trees       : Safe_UInt
    n_blobs       : Safe_UInt
    t_commits_ms  : Safe_UInt
    t_trees_ms    : Safe_UInt
    t_blobs_ms    : Safe_UInt
    t_checkout_ms : Safe_UInt
    phases        : list[Schema__Profile__Clone__Phase]
