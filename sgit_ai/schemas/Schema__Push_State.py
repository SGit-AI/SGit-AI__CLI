from osbot_utils.type_safe.Type_Safe                    import Type_Safe
from sgit_ai.safe_types.Safe_Str__Vault_Id           import Safe_Str__Vault_Id
from sgit_ai.safe_types.Safe_Str__Object_Id          import Safe_Str__Object_Id


class Schema__Push_State(Type_Safe):
    vault_id        : Safe_Str__Vault_Id  = None
    clone_commit_id : Safe_Str__Object_Id = None
    blobs_uploaded  : list[Safe_Str__Object_Id]
