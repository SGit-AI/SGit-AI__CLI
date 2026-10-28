from osbot_utils.type_safe.Type_Safe                  import Type_Safe
from osbot_utils.type_safe.primitives.core.Safe_UInt  import Safe_UInt
from sgit_ai.safe_types.Safe_Str__Commit_Id           import Safe_Str__Commit_Id
from sgit_ai.safe_types.Safe_Str__Content_Path        import Safe_Str__Content_Path
from sgit_ai.safe_types.Safe_Str__Schema_Version      import Safe_Str__Schema_Version
from sgit_ai.safe_types.Safe_Str__Diff_Text           import Safe_Str__Diff_Text
from sgit_ai.schemas.history.Schema__Blame_Commit     import Schema__Blame_Commit
from sgit_ai.schemas.history.Schema__Blame_Line       import Schema__Blame_Line


class Schema__Blame_Result(Type_Safe):
    schema          : Safe_Str__Schema_Version = 'history_blame_v1'
    path            : Safe_Str__Content_Path
    rev             : Safe_Str__Commit_Id      = None
    boundary_reason : Safe_Str__Diff_Text      = None      # '' root reached, 'shallow', 'offline'
    commits         : dict[Safe_Str__Commit_Id, Schema__Blame_Commit]
    lines           : list[Schema__Blame_Line]
    commits_visited : Safe_UInt
    blobs_read      : Safe_UInt
