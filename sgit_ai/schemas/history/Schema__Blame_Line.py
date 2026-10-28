from osbot_utils.type_safe.Type_Safe                  import Type_Safe
from osbot_utils.type_safe.primitives.core.Safe_UInt  import Safe_UInt
from sgit_ai.safe_types.Safe_Str__Commit_Id           import Safe_Str__Commit_Id
from sgit_ai.safe_types.Safe_Str__Content_Path        import Safe_Str__Content_Path
from sgit_ai.safe_types.Safe_Str__Diff_Text           import Safe_Str__Diff_Text


class Schema__Blame_Line(Type_Safe):
    final_line : Safe_UInt                                 # 1-based, in the blamed revision
    orig_line  : Safe_UInt                                 # 1-based, in the commit that introduced it
    commit_id  : Safe_Str__Commit_Id = None
    orig_path  : Safe_Str__Content_Path
    text       : Safe_Str__Diff_Text = None                # the line, without its newline
