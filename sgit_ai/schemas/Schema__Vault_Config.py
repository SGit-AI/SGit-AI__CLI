from osbot_utils.type_safe.Type_Safe                          import Type_Safe
from sgit_ai.safe_types.Safe_Str__Vault_Id                import Safe_Str__Vault_Id
from sgit_ai.safe_types.Safe_Str__Access_Token            import Safe_Str__Access_Token
from sgit_ai.safe_types.Safe_Str__Base_URL                import Safe_Str__Base_URL
from sgit_ai.safe_types.Safe_Str__File_Path               import Safe_Str__File_Path


class Schema__Vault_Config(Type_Safe):
    vault_id     : Safe_Str__Vault_Id     = None
    endpoint_url : Safe_Str__Base_URL     = None
    access_token : Safe_Str__Access_Token = None
    local_path   : Safe_Str__File_Path    = None
