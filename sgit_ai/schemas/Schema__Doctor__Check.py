from osbot_utils.type_safe.Type_Safe                      import Type_Safe
from sgit_ai.safe_types.Enum__Doctor_Status           import Enum__Doctor_Status
from sgit_ai.safe_types.Safe_Str__Doctor_Message      import Safe_Str__Doctor_Message
from sgit_ai.safe_types.Safe_UInt__Vault_Version      import Safe_UInt__Vault_Version
from sgit_ai.safe_types.Safe_Str__Vault_Name          import Safe_Str__Vault_Name


class Schema__Doctor__Check(Type_Safe):
    name        : Safe_Str__Vault_Name        = None   # 'parse_url', 'dns_resolve', etc.
    status      : Enum__Doctor_Status         = None
    duration_ms : Safe_UInt__Vault_Version    = None
    message     : Safe_Str__Doctor_Message    = None
    hint        : Safe_Str__Doctor_Message    = None
