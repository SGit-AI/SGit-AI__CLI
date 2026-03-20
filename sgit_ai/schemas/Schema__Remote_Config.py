from osbot_utils.type_safe.Type_Safe                              import Type_Safe
from sgit_ai.safe_types.Safe_Str__Base_URL                    import Safe_Str__Base_URL
from sgit_ai.safe_types.Safe_Str__Vault_Id                    import Safe_Str__Vault_Id
from sgit_ai.safe_types.Safe_Str__Vault_Name                  import Safe_Str__Vault_Name


class Schema__Remote_Config(Type_Safe):
    name     : Safe_Str__Vault_Name = None                 # remote name (e.g. 'origin')
    url      : Safe_Str__Base_URL   = None                 # API endpoint URL
    vault_id : Safe_Str__Vault_Id   = None                 # remote vault ID
