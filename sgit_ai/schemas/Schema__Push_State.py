from osbot_utils.type_safe.Type_Safe                    import Type_Safe
from sgit_ai.safe_types.Safe_Str__Base_URL           import Safe_Str__Base_URL
from sgit_ai.safe_types.Safe_Str__Vault_Id           import Safe_Str__Vault_Id
from sgit_ai.safe_types.Safe_Str__Object_Id          import Safe_Str__Object_Id


class Schema__Push_State(Type_Safe):
    vault_id        : Safe_Str__Vault_Id  = None
    clone_commit_id : Safe_Str__Object_Id = None
    # API base URL of the remote this checkpoint was built for. Without this
    # field, a non-first push of the same clone_commit_id to two different
    # remotes would consult the same blobs_uploaded set and could skip blobs
    # the second remote does not have. (Reuses Safe_Str__Base_URL — already
    # the canonical URL type for Vault__API.base_url / Schema__Remote_Config.)
    remote_url      : Safe_Str__Base_URL  = None
    blobs_uploaded  : list[Safe_Str__Object_Id]
