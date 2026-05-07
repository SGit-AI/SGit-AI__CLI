from osbot_utils.type_safe.Type_Safe                  import Type_Safe
from osbot_utils.type_safe.primitives.core.Safe_Str   import Safe_Str
from sgit_ai.safe_types.Safe_Str__Commit_Id           import Safe_Str__Commit_Id
from sgit_ai.safe_types.Safe_UInt__Timestamp          import Safe_UInt__Timestamp
from sgit_ai.safe_types.Safe_Str__ISO_Timestamp       import Safe_Str__ISO_Timestamp
from sgit_ai.safe_types.Safe_Str__File_Path           import Safe_Str__File_Path


class Schema__History_Log_Commit_Entry(Type_Safe):
    commit_id      : Safe_Str__Commit_Id       = None
    parent_ids     : list[Safe_Str__Commit_Id]
    timestamp_ms   : Safe_UInt__Timestamp
    timestamp_iso  : Safe_Str__ISO_Timestamp   = None
    message        : Safe_Str                  = None
    branch_id      : Safe_Str                  = None
    files_added    : list[Safe_Str__File_Path]
    files_modified : list[Safe_Str__File_Path]
    files_deleted  : list[Safe_Str__File_Path]
    patch          : Safe_Str                  = None
