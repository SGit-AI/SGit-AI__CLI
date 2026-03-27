from osbot_utils.type_safe.Type_Safe               import Type_Safe
from osbot_utils.type_safe.primitives.core.Safe_Str  import Safe_Str
from osbot_utils.type_safe.primitives.core.Safe_UInt import Safe_UInt
from sgit_ai.safe_types.Safe_Str__File_Path        import Safe_Str__File_Path
from sgit_ai.safe_types.Safe_Str__Diff_Mode        import Safe_Str__Diff_Mode
from sgit_ai.schemas.Schema__Diff_File             import Schema__Diff_File


class Schema__Diff_Result(Type_Safe):
    directory      : Safe_Str__File_Path = None
    mode           : Safe_Str__Diff_Mode = None   # "head" | "remote" | "commit"
    commit_id      : Safe_Str            = None   # which commit was diffed against
    files          : list[Schema__Diff_File]
    added_count    : Safe_UInt
    modified_count : Safe_UInt
    deleted_count  : Safe_UInt
