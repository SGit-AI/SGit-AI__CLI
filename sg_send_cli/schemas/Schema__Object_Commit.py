from osbot_utils.type_safe.Type_Safe                          import Type_Safe
from sg_send_cli.safe_types.Safe_Str__Object_Id               import Safe_Str__Object_Id
from sg_send_cli.safe_types.Safe_Str__Branch_Id               import Safe_Str__Branch_Id
from sg_send_cli.safe_types.Safe_Str__Signature               import Safe_Str__Signature
from sg_send_cli.safe_types.Safe_Str__Author_Key_Id           import Safe_Str__Author_Key_Id
from sg_send_cli.safe_types.Safe_Str__Schema_Version          import Safe_Str__Schema_Version
from sg_send_cli.safe_types.Safe_Str__Encrypted_Value         import Safe_Str__Encrypted_Value
from sg_send_cli.safe_types.Safe_UInt__Timestamp              import Safe_UInt__Timestamp


class Schema__Object_Commit(Type_Safe):
    schema             : Safe_Str__Schema_Version = None   # 'commit_v1'
    tree_id            : Safe_Str__Object_Id      = None   # root tree obj-cas-imm-{hash}
    parents            : list[Safe_Str__Object_Id]          # parent commit IDs
    timestamp_ms       : Safe_UInt__Timestamp               # uint milliseconds since epoch
    message_enc        : Safe_Str__Encrypted_Value = None   # AES-GCM encrypted message (base64)
    branch_id          : Safe_Str__Branch_Id      = None   # branch that created this commit
    signature          : Safe_Str__Signature      = None   # ECDSA signature
    author_key_id      : Safe_Str__Author_Key_Id  = None   # reserved
    author_signature   : Safe_Str__Signature      = None   # reserved
    attestations       : list[Safe_Str__Signature]           # reserved
