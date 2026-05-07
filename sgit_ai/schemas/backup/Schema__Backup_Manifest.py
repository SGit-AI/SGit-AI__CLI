from osbot_utils.type_safe.Type_Safe               import Type_Safe
from sgit_ai.safe_types.Safe_Str__App_Version      import Safe_Str__App_Version
from sgit_ai.safe_types.Safe_Str__Backup_Label     import Safe_Str__Backup_Label
from sgit_ai.safe_types.Safe_Str__ISO_Timestamp    import Safe_Str__ISO_Timestamp
from sgit_ai.safe_types.Safe_Str__Vault_Id         import Safe_Str__Vault_Id
from sgit_ai.safe_types.Safe_UInt__Byte_Size       import Safe_UInt__Byte_Size
from sgit_ai.safe_types.Safe_UInt__File_Count      import Safe_UInt__File_Count
from sgit_ai.safe_types.Safe_UInt__Vault_Version   import Safe_UInt__Vault_Version


class Schema__Backup_Manifest(Type_Safe):
    schema_version : Safe_UInt__Vault_Version = None
    vault_id       : Safe_Str__Vault_Id       = None
    key_generation : Safe_UInt__Vault_Version = None
    created_at     : Safe_Str__ISO_Timestamp  = None
    created_by     : Safe_Str__App_Version    = None
    label          : Safe_Str__Backup_Label   = None
    includes_key   : bool                     = False
    object_count   : Safe_UInt__File_Count    = None
    byte_size      : Safe_UInt__Byte_Size     = None
