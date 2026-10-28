from osbot_utils.type_safe.Type_Safe               import Type_Safe
from sgit_ai.safe_types.Enum__Hunk_File_Status     import Enum__Hunk_File_Status
from sgit_ai.safe_types.Safe_Str__Content_Hash     import Safe_Str__Content_Hash
from sgit_ai.safe_types.Safe_Str__Pathspec         import Safe_Str__Pathspec
from sgit_ai.schemas.commit.Schema__Hunk           import Schema__Hunk


class Schema__File_Hunks(Type_Safe):
    path      : Safe_Str__Pathspec
    status    : Enum__Hunk_File_Status = Enum__Hunk_File_Status.MODIFIED
    binary    : bool = False
    base_hash : Safe_Str__Content_Hash
    work_hash : Safe_Str__Content_Hash
    hunks     : list[Schema__Hunk]
