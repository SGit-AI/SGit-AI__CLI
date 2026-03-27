from osbot_utils.type_safe.Type_Safe               import Type_Safe
from osbot_utils.type_safe.primitives.core.Safe_Str  import Safe_Str
from osbot_utils.type_safe.primitives.core.Safe_UInt import Safe_UInt
from sgit_ai.safe_types.Safe_Str__File_Path        import Safe_Str__File_Path


class Schema__Diff_File(Type_Safe):
    path        : Safe_Str__File_Path = None
    status      : Safe_Str            = None   # "added" | "modified" | "deleted" | "unchanged"
    is_binary   : bool                = False
    diff_text   : Safe_Str            = None   # unified diff (text files only)
    size_before : Safe_UInt                    # bytes before (0 if added)
    size_after  : Safe_UInt                    # bytes after (0 if deleted)
    hash_before : Safe_Str            = None   # SHA-256 hex (empty if added)
    hash_after  : Safe_Str            = None   # SHA-256 hex (empty if deleted)
