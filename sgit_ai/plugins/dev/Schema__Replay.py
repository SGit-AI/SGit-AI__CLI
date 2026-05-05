import re
from osbot_utils.type_safe.Type_Safe                import Type_Safe
from osbot_utils.type_safe.primitives.core.Safe_Str  import Safe_Str
from osbot_utils.type_safe.primitives.core.Safe_UInt import Safe_UInt


class Safe_Str__Sign(Safe_Str):
    """Signed delta string: '+123 ms', '-45 ms', '0 ms'."""
    regex       = re.compile(r'[^0-9+\- ms%x.]')
    allow_empty = True


class Schema__Replay__Phase__Diff(Type_Safe):
    """Timing difference for one phase between two traces."""
    phase       : Safe_Str      = None
    a_ms        : Safe_UInt              # duration in trace A
    b_ms        : Safe_UInt              # duration in trace B
    delta_ms    : Safe_Str__Sign = None  # e.g. '+50 ms' or '-20 ms'
    pct_change  : Safe_Str__Sign = None  # e.g. '+25%'


class Schema__Replay(Type_Safe):
    """JSON output schema for `sgit dev replay`."""
    trace_file  : Safe_Str = None
    vault_id    : Safe_Str = None
    n_commits   : Safe_UInt
    n_trees     : Safe_UInt
    n_blobs     : Safe_UInt
    total_ms    : Safe_UInt
    t_commits_ms: Safe_UInt
    t_trees_ms  : Safe_UInt
    t_blobs_ms  : Safe_UInt
    t_checkout_ms: Safe_UInt
    diff_phases : list[Schema__Replay__Phase__Diff]   # populated only in --diff mode
