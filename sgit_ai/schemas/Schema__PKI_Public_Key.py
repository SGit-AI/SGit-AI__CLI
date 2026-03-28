from osbot_utils.type_safe.Type_Safe                           import Type_Safe
from sgit_ai.safe_types.Safe_Str__Key_Fingerprint          import Safe_Str__Key_Fingerprint
from sgit_ai.safe_types.Safe_Str__PEM_Key                  import Safe_Str__PEM_Key
from sgit_ai.safe_types.Safe_Str__Vault_Name               import Safe_Str__Vault_Name


class Schema__PKI_Public_Key(Type_Safe):
    label               : Safe_Str__Vault_Name      = None
    fingerprint         : Safe_Str__Key_Fingerprint = None
    signing_fingerprint : Safe_Str__Key_Fingerprint = None
    public_key_pem      : Safe_Str__PEM_Key
    signing_key_pem     : Safe_Str__PEM_Key
