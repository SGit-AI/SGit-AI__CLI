from osbot_utils.type_safe.Type_Safe                                                   import Type_Safe
from osbot_utils.type_safe.primitives.core.Safe_UInt                                   import Safe_UInt
from osbot_utils.type_safe.primitives.domains.identifiers.safe_str.Safe_Str__Id        import Safe_Str__Id
from sgit_ai.safe_types.Safe_Str__File_Path                                            import Safe_Str__File_Path
from sgit_ai.safe_types.Safe_Str__Diff_Mode                                            import Safe_Str__Diff_Mode
from sgit_ai.schemas.Schema__Diff_File                                                 import Schema__Diff_File


class Schema__Diff_Result(Type_Safe):
    directory      : Safe_Str__File_Path = None
    mode           : Safe_Str__Diff_Mode = None   # "head" | "remote" | "commit"
    commit_id      : Safe_Str__Id        = None   # first commit (or only commit diffed against)
    commit_id_b    : Safe_Str__Id        = None   # second commit (only set for commit-to-commit diffs)
    files          : list[Schema__Diff_File]
    added_count    : Safe_UInt
    modified_count : Safe_UInt
    deleted_count  : Safe_UInt
