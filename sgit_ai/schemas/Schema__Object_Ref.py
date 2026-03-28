from osbot_utils.type_safe.Type_Safe                          import Type_Safe
from sgit_ai.safe_types.Safe_Str__Object_Id               import Safe_Str__Object_Id
from sgit_ai.safe_types.Safe_UInt__Vault_Version          import Safe_UInt__Vault_Version


class Schema__Object_Ref(Type_Safe):
    commit_id : Safe_Str__Object_Id      = None
    version   : Safe_UInt__Vault_Version
