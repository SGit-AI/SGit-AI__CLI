from osbot_utils.type_safe.Type_Safe               import Type_Safe
from osbot_utils.type_safe.primitives.core.Safe_Str  import Safe_Str
from osbot_utils.type_safe.primitives.core.Safe_UInt import Safe_UInt


class Schema__Dump_Object(Type_Safe):
    """Describes a single object found in the bare/data directory."""
    object_id  : Safe_Str          = None   # e.g. obj-cas-imm-{hash}
    size_bytes : Safe_UInt                  # raw ciphertext size
    is_dangling: bool              = False  # True if not referenced by any tree or commit
    integrity  : bool              = True   # False if stored hash does not match computed hash
