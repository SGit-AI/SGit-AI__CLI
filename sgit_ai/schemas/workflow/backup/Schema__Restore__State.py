from osbot_utils.type_safe.Type_Safe              import Type_Safe
from sgit_ai.safe_types.Safe_Str__File_Path       import Safe_Str__File_Path
from sgit_ai.safe_types.Safe_Str__Vault_Id        import Safe_Str__Vault_Id
from sgit_ai.safe_types.Safe_Str__Vault_Key       import Safe_Str__Vault_Key
from sgit_ai.safe_types.Safe_Str__Restore_Mode    import Safe_Str__Restore_Mode
from sgit_ai.safe_types.Safe_Str__SHA256          import Safe_Str__SHA256
from sgit_ai.safe_types.Safe_UInt__Timestamp      import Safe_UInt__Timestamp


class Schema__Restore__State(Type_Safe):
    zip_source    : Safe_Str__File_Path    = None
    destination   : Safe_Str__File_Path    = None
    mode          : Safe_Str__Restore_Mode = None
    vault_key     : Safe_Str__Vault_Key    = None
    zip_path      : Safe_Str__File_Path    = None
    sha256        : Safe_Str__SHA256       = None
    sg_dir        : Safe_Str__File_Path    = None
    vault_id      : Safe_Str__Vault_Id     = None
    t_checkout_ms : Safe_UInt__Timestamp   = None
