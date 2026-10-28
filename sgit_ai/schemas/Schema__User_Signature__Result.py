from osbot_utils.type_safe.Type_Safe                     import Type_Safe
from sgit_ai.safe_types.Enum__User_Signature_Format      import Enum__User_Signature_Format
from sgit_ai.safe_types.Enum__User_Signature_Status      import Enum__User_Signature_Status
from sgit_ai.safe_types.Safe_Str__Signature_Reason       import Safe_Str__Signature_Reason
from sgit_ai.safe_types.Safe_Str__Signer_Key_Fingerprint import Safe_Str__Signer_Key_Fingerprint
from sgit_ai.safe_types.Safe_Str__Signer_Key_Type        import Safe_Str__Signer_Key_Type
from sgit_ai.safe_types.Safe_Str__Signer_Principal       import Safe_Str__Signer_Principal


class Schema__User_Signature__Result(Type_Safe):
    """One verifier's verdict on a user signature. Computed, never stored in the vault:
    `principal` comes from this verifier's allowed-signers file or keyring."""
    status          : Enum__User_Signature_Status      = None
    format          : Enum__User_Signature_Format      = None
    principal       : Safe_Str__Signer_Principal       = None
    key_type        : Safe_Str__Signer_Key_Type        = None
    key_fingerprint : Safe_Str__Signer_Key_Fingerprint = None
    reason          : Safe_Str__Signature_Reason       = None
