from osbot_utils.type_safe.Type_Safe                          import Type_Safe
from sg_send_cli.safe_types.Safe_Str__Object_Id               import Safe_Str__Object_Id
from sg_send_cli.safe_types.Safe_Str__ISO_Timestamp           import Safe_Str__ISO_Timestamp
from sg_send_cli.safe_types.Safe_Str__Commit_Message          import Safe_Str__Commit_Message
from sg_send_cli.safe_types.Safe_Str__Branch_Id               import Safe_Str__Branch_Id
from sg_send_cli.safe_types.Safe_Str__Signature               import Safe_Str__Signature
from sg_send_cli.safe_types.Safe_Str__Author_Key_Id           import Safe_Str__Author_Key_Id
from sg_send_cli.safe_types.Safe_Str__Schema_Version          import Safe_Str__Schema_Version
from sg_send_cli.safe_types.Safe_UInt__Timestamp              import Safe_UInt__Timestamp
from sg_send_cli.safe_types.Safe_UInt__Vault_Version          import Safe_UInt__Vault_Version


class Schema__Object_Commit(Type_Safe):
    parent             : Safe_Str__Object_Id      = None          # legacy single-parent (kept for backward compat)
    parents            : list[Safe_Str__Object_Id]                # v2: ordered list of parent commit IDs
    tree_id            : Safe_Str__Object_Id      = None
    timestamp          : Safe_Str__ISO_Timestamp  = None          # legacy ISO timestamp
    timestamp_ms       : Safe_UInt__Timestamp                     # v2: uint milliseconds since epoch
    message            : Safe_Str__Commit_Message = None
    version            : Safe_UInt__Vault_Version                 # legacy version counter
    schema             : Safe_Str__Schema_Version = None          # v2: e.g. 'commit_v1'
    branch_id          : Safe_Str__Branch_Id      = None          # v2: branch that created this commit
    signature          : Safe_Str__Signature      = None          # v2: branch key ECDSA signature
    author_key_id      : Safe_Str__Author_Key_Id  = None          # v2: Mode 3 author key ID
    author_signature   : Safe_Str__Signature      = None          # v2: Mode 3 author ECDSA signature
    attestations       : list[str]                                # v2: reserved for future attestation data
