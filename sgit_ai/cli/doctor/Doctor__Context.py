from osbot_utils.type_safe.Type_Safe                  import Type_Safe
from sgit_ai.safe_types.Safe_Str__Access_Token    import Safe_Str__Access_Token
from sgit_ai.safe_types.Safe_Str__Base_URL        import Safe_Str__Base_URL
from sgit_ai.safe_types.Safe_Str__Remote_Name     import Safe_Str__Remote_Name
from sgit_ai.safe_types.Safe_Str__Vault_Id        import Safe_Str__Vault_Id
from sgit_ai.safe_types.Safe_Str__Write_Key       import Safe_Str__Write_Key
from sgit_ai.safe_types.Safe_UInt__Lock_Timeout   import Safe_UInt__Lock_Timeout


class Doctor__Context(Type_Safe):
    url             : Safe_Str__Base_URL      = None
    token           : Safe_Str__Access_Token  = None
    vault_id        : Safe_Str__Vault_Id      = None
    timeout_seconds : Safe_UInt__Lock_Timeout = 5        # seconds; default 5, max 86400
    tls_verify      : bool                    = True
    write_probe     : bool                    = False
    remote_name     : Safe_Str__Remote_Name   = None
    write_key       : Safe_Str__Write_Key     = None     # write probe only; from the clone's vault key

    def headers(self, extra: dict = None) -> dict:
        """The headers every check sends: the token on the names Vault__API sends it on
        (x-sgraph-access-token for the vault app, X-API-Key for the stack middleware), plus
        Bearer for servers that read that. Doctor used to send only Bearer, so a token push
        was using without trouble came back from doctor as "401 — token rejected"."""
        headers = {'Accept': 'application/json'}
        if self.token:
            token                            = str(self.token)
            headers['x-sgraph-access-token'] = token
            headers['X-API-Key']             = token
            headers['Authorization']         = f'Bearer {token}'
        if extra:
            headers.update(extra)
        return headers
