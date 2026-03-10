from osbot_utils.type_safe.Type_Safe                          import Type_Safe
from sg_send_cli.safe_types.Safe_Str__Object_Id               import Safe_Str__Object_Id
from sg_send_cli.safe_types.Safe_UInt__Vault_Version          import Safe_UInt__Vault_Version


class Schema__Object_Ref(Type_Safe):
    commit_id : Safe_Str__Object_Id      = None
    version   : Safe_UInt__Vault_Version
