from osbot_utils.type_safe.Type_Safe                                                  import Type_Safe
from osbot_utils.type_safe.primitives.domains.identifiers.safe_int.Timestamp_Now      import Timestamp_Now
from sgit_ai.safe_types.Safe_Str__Key_Fingerprint                                 import Safe_Str__Key_Fingerprint
from sgit_ai.safe_types.Safe_Str__Vault_Name                                      import Safe_Str__Vault_Name
from sgit_ai.safe_types.Safe_UInt__Key_Size                                       import Safe_UInt__Key_Size


class Schema__PKI_Key_Pair(Type_Safe):
    label                 : Safe_Str__Vault_Name      = None
    algorithm             : Safe_Str__Vault_Name      = None
    key_size              : Safe_UInt__Key_Size
    encryption_fingerprint: Safe_Str__Key_Fingerprint = None
    signing_fingerprint   : Safe_Str__Key_Fingerprint = None
    created_at            : Timestamp_Now             = None    # milliseconds since epoch
