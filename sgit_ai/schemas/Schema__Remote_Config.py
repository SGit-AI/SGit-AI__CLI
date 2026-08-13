from osbot_utils.type_safe.Type_Safe                                                  import Type_Safe
from osbot_utils.type_safe.primitives.domains.identifiers.safe_int.Timestamp_Now      import Timestamp_Now
from sgit_ai.safe_types.Enum__Doctor_Status                                       import Enum__Doctor_Status
from sgit_ai.safe_types.Safe_Str__Base_URL                                        import Safe_Str__Base_URL
from sgit_ai.safe_types.Safe_Str__Remote_Name                                     import Safe_Str__Remote_Name
from sgit_ai.safe_types.Safe_Str__Vault_Id                                        import Safe_Str__Vault_Id


class Schema__Remote_Config(Type_Safe):
    name               : Safe_Str__Remote_Name = None
    url                : Safe_Str__Base_URL    = None
    vault_id           : Safe_Str__Vault_Id    = None
    is_default         : bool                  = False
    tls_verify         : bool                  = True
    created_at         : Timestamp_Now         = None     # milliseconds since epoch
    last_health_at     : Timestamp_Now         = None     # milliseconds since epoch
    last_health_status : Enum__Doctor_Status   = None
