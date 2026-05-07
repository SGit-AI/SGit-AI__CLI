from osbot_utils.type_safe.Type_Safe                  import Type_Safe
from osbot_utils.type_safe.primitives.core.Safe_UInt  import Safe_UInt
from sgit_ai.safe_types.Safe_Str__Commit_Id           import Safe_Str__Commit_Id
from sgit_ai.safe_types.Safe_Str__Schema_Version      import Safe_Str__Schema_Version
from sgit_ai.schemas.history.Schema__History_Log_Commit_Entry import Schema__History_Log_Commit_Entry


class Schema__History_Log_Result(Type_Safe):
    schema       : Safe_Str__Schema_Version = None   # 'history_log_v1'
    from_commit  : Safe_Str__Commit_Id      = None
    to_commit    : Safe_Str__Commit_Id      = None
    commit_count : Safe_UInt
    commits      : list[Schema__History_Log_Commit_Entry]
