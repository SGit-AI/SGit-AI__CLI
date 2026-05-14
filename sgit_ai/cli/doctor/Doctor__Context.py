from osbot_utils.type_safe.Type_Safe                  import Type_Safe
from sgit_ai.safe_types.Safe_Str__Access_Token    import Safe_Str__Access_Token
from sgit_ai.safe_types.Safe_Str__Base_URL        import Safe_Str__Base_URL
from sgit_ai.safe_types.Safe_Str__Remote_Name     import Safe_Str__Remote_Name
from sgit_ai.safe_types.Safe_Str__Vault_Id        import Safe_Str__Vault_Id
from sgit_ai.safe_types.Safe_UInt__Lock_Timeout   import Safe_UInt__Lock_Timeout


class Doctor__Context(Type_Safe):
    url             : Safe_Str__Base_URL      = None
    token           : Safe_Str__Access_Token  = None
    vault_id        : Safe_Str__Vault_Id      = None
    timeout_seconds : Safe_UInt__Lock_Timeout = 5        # seconds; default 5, max 86400
    tls_verify      : bool                    = True
    write_probe     : bool                    = False
    remote_name     : Safe_Str__Remote_Name   = None
