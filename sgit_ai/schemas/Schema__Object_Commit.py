from osbot_utils.type_safe.Type_Safe                          import Type_Safe
from sgit_ai.safe_types.Safe_Str__Object_Id               import Safe_Str__Object_Id
from sgit_ai.safe_types.Safe_Str__Branch_Id               import Safe_Str__Branch_Id
from sgit_ai.safe_types.Safe_Str__Signature               import Safe_Str__Signature
from sgit_ai.safe_types.Safe_Str__Author_Key_Id           import Safe_Str__Author_Key_Id
from sgit_ai.safe_types.Safe_Str__Schema_Version          import Safe_Str__Schema_Version
from sgit_ai.safe_types.Safe_Str__Encrypted_Message       import Safe_Str__Encrypted_Message
from sgit_ai.safe_types.Safe_UInt__Timestamp              import Safe_UInt__Timestamp
from sgit_ai.schemas.Schema__User_Signature              import Schema__User_Signature


class Schema__Object_Commit(Type_Safe):
    schema             : Safe_Str__Schema_Version = None   # 'commit_v1'
    tree_id            : Safe_Str__Object_Id      = None   # root tree obj-cas-imm-{hash}
    parents            : list[Safe_Str__Object_Id]          # parent commit IDs
    timestamp_ms       : Safe_UInt__Timestamp               # uint milliseconds since epoch
    message_enc        : Safe_Str__Encrypted_Message = None # AES-GCM encrypted message (base64); up to 1 MiB on read
    branch_id          : Safe_Str__Branch_Id      = None   # branch that created this commit
    signature          : Safe_Str__Signature      = None   # ECDSA signature
    author_key_id      : Safe_Str__Author_Key_Id  = None   # the signing key (bare/keys/<id>); set since 0.19.0, marks the canonical signing form
    author_signature   : Safe_Str__Signature      = None   # reserved: a second (author) signature distinct from the committer's
    attestations       : list[Safe_Str__Signature]           # reserved: e.g. reviewer approvals
    user_signature     : Schema__User_Signature   = None   # the signer's own SSH/OpenPGP key (Git's gpgsig); outside both signatures' bytes; never stored when None
