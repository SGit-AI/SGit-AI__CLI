from osbot_utils.type_safe.Type_Safe                    import Type_Safe
from sgit_ai.safe_types.Enum__Clone_Mode             import Enum__Clone_Mode
from sgit_ai.safe_types.Safe_Str__Vault_Id           import Safe_Str__Vault_Id
from sgit_ai.safe_types.Safe_Str__Write_Key          import Safe_Str__Write_Key


class Schema__Clone_Mode(Type_Safe):
    # read_key is a 64-hex-char AES-256 key stored intentionally on disk
    # (Dinis decision; AppSec F07 accepted-risk). Safe_Str__Write_Key
    # validates the 64-char hex format; the field is reused here because
    # read keys share the same byte-length as write keys.
    mode     : Enum__Clone_Mode   = None
    vault_id : Safe_Str__Vault_Id = None
    read_key : Safe_Str__Write_Key = None
