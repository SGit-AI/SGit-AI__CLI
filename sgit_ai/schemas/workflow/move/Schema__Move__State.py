from osbot_utils.type_safe.Type_Safe             import Type_Safe
from sgit_ai.safe_types.Safe_Str__Base_URL       import Safe_Str__Base_URL
from sgit_ai.safe_types.Safe_Str__Commit_Message import Safe_Str__Commit_Message
from sgit_ai.safe_types.Safe_Str__File_Path      import Safe_Str__File_Path
from sgit_ai.safe_types.Safe_Str__ISO_Timestamp  import Safe_Str__ISO_Timestamp
from sgit_ai.safe_types.Safe_Str__Vault_Id       import Safe_Str__Vault_Id
from sgit_ai.safe_types.Safe_Str__Vault_Key      import Safe_Str__Vault_Key
from sgit_ai.safe_types.Safe_UInt__Vault_Version import Safe_UInt__Vault_Version


class Schema__Move__State(Type_Safe):
    directory          : Safe_Str__File_Path      = None
    new_vault_key      : Safe_Str__Vault_Key      = None
    target_api_url     : Safe_Str__Base_URL       = None
    reason             : Safe_Str__Commit_Message = None
    dry_run            : bool                     = False
    old_vault_id       : Safe_Str__Vault_Id       = None
    old_api_url        : Safe_Str__Base_URL       = None
    object_count       : Safe_UInt__Vault_Version = None
    new_vault_id       : Safe_Str__Vault_Id       = None
    key_generation     : Safe_UInt__Vault_Version = None
    temp_vault_dir     : Safe_Str__File_Path      = None
    sentinel_commit_id : Safe_Str__File_Path      = None
    push_completed     : bool                     = False
    verify_completed   : bool                     = False
    backup_zip_path    : Safe_Str__File_Path      = None
    renamed_at         : Safe_Str__ISO_Timestamp  = None
    server_deleted     : bool                     = False
