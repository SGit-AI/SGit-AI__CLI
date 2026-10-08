from osbot_utils.type_safe.Type_Safe                       import Type_Safe
from osbot_utils.type_safe.primitives.core.Safe_UInt       import Safe_UInt
from sgit_ai.safe_types.Safe_Str__Tag_Name                 import Safe_Str__Tag_Name
from sgit_ai.safe_types.Safe_Str__Object_Id                import Safe_Str__Object_Id


class Schema__Tag_Ref(Type_Safe):
    """A tag's entry in the (encrypted) branch index: name -> tag object. One live
    entry per name; a deleted tag stays as a tombstone so a stale clone's copy
    cannot bring it back. Merge rule per name: the later (timestamp_ms, tag_id)."""
    name         : Safe_Str__Tag_Name  = None
    tag_id       : Safe_Str__Object_Id = None
    timestamp_ms : Safe_UInt
    deleted      : bool                = False
