from osbot_utils.type_safe.Type_Safe                  import Type_Safe
from osbot_utils.type_safe.primitives.core.Safe_UInt  import Safe_UInt
from sgit_ai.safe_types.Safe_Str__File_Path           import Safe_Str__File_Path


class Schema__History_Diff_File(Type_Safe):
    path          : Safe_Str__File_Path = None
    lines_added   : Safe_UInt
    lines_removed : Safe_UInt
