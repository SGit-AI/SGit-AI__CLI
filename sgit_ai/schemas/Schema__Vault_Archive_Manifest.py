from osbot_utils.type_safe.Type_Safe                                           import Type_Safe
from osbot_utils.type_safe.primitives.domains.identifiers.safe_int.Timestamp_Now import Timestamp_Now
from sgit_ai.safe_types.Safe_Str__Schema_Version                               import Safe_Str__Schema_Version
from sgit_ai.safe_types.Safe_Str__Vault_Id                                     import Safe_Str__Vault_Id
from sgit_ai.safe_types.Safe_Str__Key_Type                                     import Safe_Str__Key_Type
from sgit_ai.safe_types.Safe_Str__Commit_Message                               import Safe_Str__Commit_Message
from sgit_ai.safe_types.Safe_UInt__File_Count                                  import Safe_UInt__File_Count
from sgit_ai.safe_types.Safe_UInt__File_Size                                   import Safe_UInt__File_Size
from sgit_ai.schemas.Schema__Archive_Provenance                                import Schema__Archive_Provenance

VAULT_ARCHIVE_SCHEMA_VERSION = 'vault_archive_v1'


class Schema__Vault_Archive_Manifest(Type_Safe):
    schema         : Safe_Str__Schema_Version  = None   # 'vault_archive_v1'
    vault_id       : Safe_Str__Vault_Id        = None
    created_at     : Timestamp_Now             = None   # milliseconds since epoch (Type_Safe convention)
    files          : Safe_UInt__File_Count
    total_bytes    : Safe_UInt__File_Size
    inner_key_type : Safe_Str__Key_Type        = None   # 'vault_key' | 'none' | 'pki' | 'password'
    inner_key_id   : Safe_Str__Vault_Id        = None
    description    : Safe_Str__Commit_Message  = None
    provenance     : Schema__Archive_Provenance = None
