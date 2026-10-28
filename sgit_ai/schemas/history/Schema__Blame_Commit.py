from osbot_utils.type_safe.Type_Safe                  import Type_Safe
from sgit_ai.safe_types.Safe_Str__Commit_Id           import Safe_Str__Commit_Id
from sgit_ai.safe_types.Safe_Str__Content_Path        import Safe_Str__Content_Path
from sgit_ai.safe_types.Safe_Str__Diff_Text           import Safe_Str__Diff_Text
from sgit_ai.safe_types.Safe_UInt__Timestamp          import Safe_UInt__Timestamp


class Schema__Blame_Commit(Type_Safe):
    timestamp_ms  : Safe_UInt__Timestamp
    author        : Safe_Str__Diff_Text    = None          # branch name, else the signing key id
    author_key_id : Safe_Str__Diff_Text    = None
    summary       : Safe_Str__Diff_Text    = None          # first line of the message
    boundary      : bool = False                           # the root, a shallow boundary, or history not local
    previous_id   : Safe_Str__Commit_Id    = None
    previous_path : Safe_Str__Content_Path = None
