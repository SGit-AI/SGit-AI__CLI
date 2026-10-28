from osbot_utils.type_safe.Type_Safe                   import Type_Safe
from osbot_utils.type_safe.primitives.core.Safe_UInt   import Safe_UInt
from sgit_ai.safe_types.Safe_Str__Content_Path         import Safe_Str__Content_Path
from sgit_ai.safe_types.Safe_UInt__Rename_Score        import Safe_UInt__Rename_Score


class Schema__History_Rename(Type_Safe):
    """A renamed file in `history log --json` / `history diff --json` (files_renamed)."""
    old_path      : Safe_Str__Content_Path
    new_path      : Safe_Str__Content_Path
    score         : Safe_UInt__Rename_Score
    exact         : bool = False
    lines_added   : Safe_UInt
    lines_removed : Safe_UInt
