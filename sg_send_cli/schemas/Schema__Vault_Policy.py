from osbot_utils.type_safe.Type_Safe                              import Type_Safe
from sg_send_cli.safe_types.Safe_Str__Schema_Version              import Safe_Str__Schema_Version
from sg_send_cli.safe_types.Enum__Provenance_Mode                 import Enum__Provenance_Mode


class Schema__Vault_Policy(Type_Safe):
    schema                    : Safe_Str__Schema_Version = None   # e.g. 'vault_policy_v1'
    minimum_provenance        : Enum__Provenance_Mode    = Enum__Provenance_Mode.MODE_1
    require_author_signature  : bool                     = False
    require_attestation       : bool                     = False
