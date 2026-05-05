import re
from osbot_utils.type_safe.Type_Safe                                                   import Type_Safe
from osbot_utils.type_safe.primitives.core.Safe_Str                                    import Safe_Str
from osbot_utils.type_safe.primitives.core.Safe_UInt                                   import Safe_UInt
from osbot_utils.type_safe.primitives.domains.identifiers.safe_str.Safe_Str__Id        import Safe_Str__Id


class Safe_Str__Progress_Detail(Safe_Str):
    """Allows alphanumerics, spaces, and common punctuation for progress detail strings."""
    regex       = re.compile(r'[^a-zA-Z0-9 _.,()\-/]')
    allow_empty = True


class Schema__Step__Clone__Event(Type_Safe):
    """One recorded step/event during a pausable clone."""
    index      : Safe_UInt
    event      : Safe_Str               = None   # 'step' | 'scan_done' | 'stats'
    label      : Safe_Str               = None
    detail     : Safe_Str__Progress_Detail = None
    elapsed_ms : Safe_UInt                         # wall-clock since clone started


class Schema__Step__Clone(Type_Safe):
    """JSON output schema for `sgit dev step-clone`."""
    vault_id   : Safe_Str = None
    directory  : Safe_Str = None
    commit_id  : Safe_Str__Id = None
    total_ms   : Safe_UInt
    n_steps    : Safe_UInt
    events     : list[Schema__Step__Clone__Event]
