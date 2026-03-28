from osbot_utils.type_safe.Type_Safe                          import Type_Safe
from sgit_ai.safe_types.Safe_Str__Vault_Id                import Safe_Str__Vault_Id
from sgit_ai.safe_types.Safe_Str__Vault_Name              import Safe_Str__Vault_Name
from sgit_ai.safe_types.Safe_Str__Vault_Key               import Safe_Str__Vault_Key
from sgit_ai.safe_types.Safe_UInt__Vault_Version          import Safe_UInt__Vault_Version


class Schema__Vault_Meta(Type_Safe):
    vault_id : Safe_Str__Vault_Id       = None
    name     : Safe_Str__Vault_Name     = None
    version  : Safe_UInt__Vault_Version
    vault_key: Safe_Str__Vault_Key      = None
