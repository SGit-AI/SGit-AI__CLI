from osbot_utils.type_safe.Type_Safe               import Type_Safe
from sgit_ai.safe_types.Safe_Str__Commit_Id        import Safe_Str__Commit_Id
from sgit_ai.schemas.commit.Schema__File_Hunks     import Schema__File_Hunks


class Schema__Hunk_List(Type_Safe):
    base_commit : Safe_Str__Commit_Id = None
    files       : list[Schema__File_Hunks]
