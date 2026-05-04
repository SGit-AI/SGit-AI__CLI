from osbot_utils.type_safe.Type_Safe                                                   import Type_Safe
from osbot_utils.type_safe.primitives.core.Safe_Str                                    import Safe_Str
from osbot_utils.type_safe.primitives.core.Safe_UInt                                   import Safe_UInt
from osbot_utils.type_safe.primitives.domains.identifiers.safe_str.Safe_Str__Id        import Safe_Str__Id


class Schema__Dump_Commit(Type_Safe):
    """Describes a single commit object decoded during tree traversal."""
    commit_id    : Safe_Str__Id = None   # obj-cas-imm-{hash}
    tree_id      : Safe_Str__Id = None   # root tree object ID
    parents      : list[Safe_Str__Id]    # parent commit IDs
    timestamp_ms : Safe_UInt             # commit timestamp
    message      : Safe_Str     = None   # decrypted commit message (None if undecryptable)
    branch_id    : Safe_Str__Id = None   # originating branch ID
    error        : Safe_Str     = None   # decode error if any
