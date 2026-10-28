from osbot_utils.type_safe.Type_Safe                import Type_Safe
from sgit_ai.safe_types.Safe_Str__Content_Path      import Safe_Str__Content_Path
from sgit_ai.safe_types.Safe_UInt__Rename_Score     import Safe_UInt__Rename_Score


class Schema__Rename_Pair(Type_Safe):
    old_path : Safe_Str__Content_Path
    new_path : Safe_Str__Content_Path
    score    : Safe_UInt__Rename_Score
    exact    : bool = False
