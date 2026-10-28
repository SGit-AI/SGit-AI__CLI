from osbot_utils.type_safe.Type_Safe                  import Type_Safe
from sgit_ai.safe_types.Enum__GPG_Trust               import Enum__GPG_Trust
from sgit_ai.safe_types.Enum__User_Signature_Format   import Enum__User_Signature_Format
from sgit_ai.safe_types.Safe_Str__Config_Value        import Safe_Str__Config_Value
from sgit_ai.safe_types.Safe_Str__Signing_Key_Spec    import Safe_Str__Signing_Key_Spec


class Schema__Signing_Config(Type_Safe):
    """How and whether to sign and verify user signatures, resolved from the command's
    flags and the user's Git config (never from the vault: design__02 §5.6)."""
    sign                 : bool = False
    format               : Enum__User_Signature_Format = None
    signing_key          : Safe_Str__Signing_Key_Spec  = None
    gpg_program          : Safe_Str__Config_Value      = None
    ssh_program          : Safe_Str__Config_Value      = None
    allowed_signers_file : Safe_Str__Config_Value      = None
    revocation_file      : Safe_Str__Config_Value      = None
    default_key_command  : Safe_Str__Config_Value      = None
    min_trust_level      : Enum__GPG_Trust             = None
    source               : Safe_Str__Config_Value      = None     # where the switch came from, for doctor and messages
