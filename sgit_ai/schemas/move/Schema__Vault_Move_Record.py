from osbot_utils.type_safe.Type_Safe                                                  import Type_Safe
from osbot_utils.type_safe.primitives.domains.identifiers.safe_int.Timestamp_Now      import Timestamp_Now
from sgit_ai.safe_types.Safe_Str__Base_URL                                        import Safe_Str__Base_URL
from sgit_ai.safe_types.Safe_Str__Commit_Message                                  import Safe_Str__Commit_Message
from sgit_ai.safe_types.Safe_Str__Vault_Id                                        import Safe_Str__Vault_Id
from sgit_ai.safe_types.Safe_UInt__Vault_Version                                  import Safe_UInt__Vault_Version


class Schema__Vault_Move_Record(Type_Safe):
    from_vault_id  : Safe_Str__Vault_Id       = None
    to_vault_id    : Safe_Str__Vault_Id       = None
    from_api       : Safe_Str__Base_URL       = None
    to_api         : Safe_Str__Base_URL       = None
    key_generation : Safe_UInt__Vault_Version = None
    rotated_at     : Timestamp_Now            = None     # milliseconds since epoch
    reason         : Safe_Str__Commit_Message = None
