from osbot_utils.type_safe.Type_Safe                    import Type_Safe
from osbot_utils.type_safe.primitives.core.Safe_Str     import Safe_Str
from sgit_ai.safe_types.Safe_Str__Commit_Id             import Safe_Str__Commit_Id
from sgit_ai.safe_types.Safe_Str__File_Path             import Safe_Str__File_Path
from sgit_ai.safe_types.Safe_Str__Schema_Version        import Safe_Str__Schema_Version
from sgit_ai.schemas.history.Schema__History_Diff_File  import Schema__History_Diff_File


class Schema__History_Diff_Result(Type_Safe):
    schema         : Safe_Str__Schema_Version  = None   # 'history_diff_v1'
    from_commit    : Safe_Str__Commit_Id       = None
    to_commit      : Safe_Str__Commit_Id       = None
    files_added    : list[Safe_Str__File_Path]
    files_modified : list[Schema__History_Diff_File]
    files_deleted  : list[Safe_Str__File_Path]
    patch          : Safe_Str                  = None
