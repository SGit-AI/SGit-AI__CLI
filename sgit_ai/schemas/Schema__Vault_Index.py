from osbot_utils.type_safe.Type_Safe                          import Type_Safe
from sgit_ai.safe_types.Safe_Str__Vault_Id                import Safe_Str__Vault_Id
from sgit_ai.safe_types.Safe_UInt__Vault_Version          import Safe_UInt__Vault_Version
from sgit_ai.schemas.Schema__Vault_Index_Entry            import Schema__Vault_Index_Entry


class Schema__Vault_Index(Type_Safe):
    vault_id : Safe_Str__Vault_Id                      = None
    version  : Safe_UInt__Vault_Version
    entries  : list[Schema__Vault_Index_Entry]
