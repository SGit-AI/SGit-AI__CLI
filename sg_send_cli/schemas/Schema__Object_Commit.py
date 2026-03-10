from osbot_utils.type_safe.Type_Safe                          import Type_Safe
from sg_send_cli.safe_types.Safe_Str__Object_Id               import Safe_Str__Object_Id
from sg_send_cli.safe_types.Safe_Str__ISO_Timestamp           import Safe_Str__ISO_Timestamp
from sg_send_cli.safe_types.Safe_Str__Commit_Message          import Safe_Str__Commit_Message
from sg_send_cli.safe_types.Safe_UInt__Vault_Version          import Safe_UInt__Vault_Version


class Schema__Object_Commit(Type_Safe):
    parent    : Safe_Str__Object_Id      = None
    tree_id   : Safe_Str__Object_Id      = None
    timestamp : Safe_Str__ISO_Timestamp  = None
    message   : Safe_Str__Commit_Message = None
    version   : Safe_UInt__Vault_Version
