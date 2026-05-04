from osbot_utils.type_safe.Type_Safe                                                   import Type_Safe
from osbot_utils.type_safe.primitives.core.Safe_Str                                    import Safe_Str
from osbot_utils.type_safe.primitives.domains.identifiers.safe_str.Safe_Str__Id        import Safe_Str__Id


class Schema__Dump_Ref(Type_Safe):
    """Describes a single ref file found in bare/refs."""
    ref_id    : Safe_Str__Id = None   # ref file name (e.g. ref-pid-muw-{hex})
    commit_id : Safe_Str__Id = None   # resolved commit ID (None if unreadable)
    error     : Safe_Str     = None   # decryption / read error if any
