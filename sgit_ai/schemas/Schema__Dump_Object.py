from osbot_utils.type_safe.Type_Safe                                                   import Type_Safe
from osbot_utils.type_safe.primitives.core.Safe_UInt                                   import Safe_UInt
from osbot_utils.type_safe.primitives.domains.identifiers.safe_str.Safe_Str__Id        import Safe_Str__Id


class Schema__Dump_Object(Type_Safe):
    """Describes a single object found in the bare/data directory."""
    object_id  : Safe_Str__Id      = None   # e.g. obj-cas-imm-{hash}
    size_bytes : Safe_UInt                  # raw ciphertext size
    is_dangling: bool              = False  # True if not referenced by any tree or commit
    integrity  : bool              = True   # False if stored hash does not match computed hash
