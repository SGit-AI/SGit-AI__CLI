from osbot_utils.type_safe.Type_Safe              import Type_Safe
from sgit_ai.safe_types.Safe_Str__File_Path       import Safe_Str__File_Path
from sgit_ai.safe_types.Safe_Str__Vault_Id        import Safe_Str__Vault_Id
from sgit_ai.safe_types.Safe_Str__Backup_Label    import Safe_Str__Backup_Label
from sgit_ai.safe_types.Safe_Str__SHA256          import Safe_Str__SHA256
from sgit_ai.safe_types.Safe_UInt__Byte_Size      import Safe_UInt__Byte_Size
from sgit_ai.safe_types.Safe_UInt__File_Count     import Safe_UInt__File_Count


class Schema__Backup__State(Type_Safe):
    directory    : Safe_Str__File_Path    = None
    output_dir   : Safe_Str__File_Path    = None
    label        : Safe_Str__Backup_Label = None
    includes_key : bool                   = False
    vault_id     : Safe_Str__Vault_Id     = None
    zip_path     : Safe_Str__File_Path    = None
    sha256       : Safe_Str__SHA256       = None
    byte_size    : Safe_UInt__Byte_Size   = None
    object_count : Safe_UInt__File_Count  = None
