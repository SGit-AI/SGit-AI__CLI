from osbot_utils.type_safe.Type_Safe                  import Type_Safe
from sgit_ai.safe_types.Safe_UInt__Line_Number        import Safe_UInt__Line_Number


class Schema__Line_Hunk(Type_Safe):
    """One maximal changed region between a base and a side, as half-open line ranges
    (0-based). A pure insertion has base_start == base_end; a pure deletion has
    side_start == side_end."""
    base_start : Safe_UInt__Line_Number
    base_end   : Safe_UInt__Line_Number
    side_start : Safe_UInt__Line_Number
    side_end   : Safe_UInt__Line_Number
