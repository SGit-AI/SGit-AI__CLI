from osbot_utils.type_safe.Type_Safe                          import Type_Safe
from sg_send_cli.safe_types.Safe_Str__Vault_Id                import Safe_Str__Vault_Id
from sg_send_cli.safe_types.Safe_Str__Vault_Name              import Safe_Str__Vault_Name
from sg_send_cli.safe_types.Safe_Str__Vault_Key               import Safe_Str__Vault_Key
from sg_send_cli.safe_types.Safe_UInt__Vault_Version          import Safe_UInt__Vault_Version


class Schema__Vault_Meta(Type_Safe):
    vault_id : Safe_Str__Vault_Id       = None
    name     : Safe_Str__Vault_Name     = None
    version  : Safe_UInt__Vault_Version
    vault_key: Safe_Str__Vault_Key      = None
