from osbot_utils.type_safe.Type_Safe               import Type_Safe
from sgit_ai.crypto.PKI__Crypto                import PKI__Crypto
from sgit_ai.crypto.Vault__Key_Manager         import Vault__Key_Manager
from sgit_ai.objects.Vault__Object_Store       import Vault__Object_Store
from sgit_ai.objects.Vault__Ref_Manager        import Vault__Ref_Manager
from sgit_ai.safe_types.Safe_Str__Vault_Key    import Safe_Str__Vault_Key
from sgit_ai.safe_types.Safe_Str__Vault_Id     import Safe_Str__Vault_Id
from sgit_ai.safe_types.Safe_Str__Write_Key    import Safe_Str__Write_Key
from sgit_ai.sync.Vault__Branch_Manager        import Vault__Branch_Manager
from sgit_ai.sync.Vault__Storage               import Vault__Storage


class Vault__Components(Type_Safe):
    vault_key              : Safe_Str__Vault_Key    = None
    vault_id               : Safe_Str__Vault_Id     = None
    read_key               : bytes                  = b''     # crypto material — no Safe_Bytes primitive
    write_key              : Safe_Str__Write_Key    = None
    ref_file_id            : str                    = ''      # ref-pid-muw-{hmac} — used in os.path.join via ref_manager
    branch_index_file_id   : str                    = ''      # idx-pid-muw-{hmac} — used in os.path.join via storage
    sg_dir                 : str                    = ''      # filesystem path — used in os.path.join throughout
    storage                : Vault__Storage
    pki                    : PKI__Crypto
    obj_store              : Vault__Object_Store
    ref_manager            : Vault__Ref_Manager
    key_manager            : Vault__Key_Manager
    branch_manager         : Vault__Branch_Manager
