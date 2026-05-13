from osbot_utils.type_safe.Type_Safe          import Type_Safe
from sgit_ai.safe_types.Safe_Str__Base_URL import Safe_Str__Base_URL
from sgit_ai.safe_types.Safe_Str__Vault_Id import Safe_Str__Vault_Id


class Doctor__Context(Type_Safe):
    url             : Safe_Str__Base_URL = None
    token           : str                = ''
    vault_id        : Safe_Str__Vault_Id = None
    timeout_seconds : int                = 5
    tls_verify      : bool               = True
    write_probe     : bool               = False
    remote_name     : str                = 'origin'
