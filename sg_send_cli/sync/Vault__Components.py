from osbot_utils.type_safe.Type_Safe               import Type_Safe
from sg_send_cli.crypto.PKI__Crypto                import PKI__Crypto
from sg_send_cli.crypto.Vault__Key_Manager         import Vault__Key_Manager
from sg_send_cli.objects.Vault__Object_Store       import Vault__Object_Store
from sg_send_cli.objects.Vault__Ref_Manager        import Vault__Ref_Manager
from sg_send_cli.sync.Vault__Branch_Manager        import Vault__Branch_Manager
from sg_send_cli.sync.Vault__Storage               import Vault__Storage


class Vault__Components(Type_Safe):
    vault_key              : str                    = ''
    vault_id               : str                    = ''
    read_key               : bytes                  = b''
    write_key              : str                    = ''
    ref_file_id            : str                    = ''      # ref-pid-muw-{hmac} (deterministic)
    branch_index_file_id   : str                    = ''      # idx-pid-muw-{hmac} (deterministic)
    sg_dir                 : str                    = ''
    storage                : Vault__Storage
    pki                    : PKI__Crypto
    obj_store              : Vault__Object_Store
    ref_manager            : Vault__Ref_Manager
    key_manager            : Vault__Key_Manager
    branch_manager         : Vault__Branch_Manager
