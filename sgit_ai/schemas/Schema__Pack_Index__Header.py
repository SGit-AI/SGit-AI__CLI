from osbot_utils.type_safe.Type_Safe                       import Type_Safe
from osbot_utils.type_safe.primitives.core.Safe_UInt        import Safe_UInt
from sgit_ai.safe_types.Safe_Str__Object_Id                import Safe_Str__Object_Id
from sgit_ai.safe_types.Safe_Str__Author_Key_Id            import Safe_Str__Author_Key_Id
from sgit_ai.safe_types.Safe_Str__Schema_Version           import Safe_Str__Schema_Version
from sgit_ai.safe_types.Safe_Str__Index_Kind               import Safe_Str__Index_Kind
from sgit_ai.safe_types.Safe_Str__Signature                import Safe_Str__Signature
from sgit_ai.safe_types.Safe_Str__Pack_Name                import Safe_Str__Pack_Name
from sgit_ai.safe_types.Safe_UInt__Timestamp               import Safe_UInt__Timestamp
from sgit_ai.schemas.Schema__Pack_Index__Member            import Schema__Pack_Index__Member


class Schema__Pack_Index__Header(Type_Safe):
    """The first member of an index pack (dev pack 01 §2.1): what the pack describes and
    where every other member is. Signed by the pusher's clone key over its canonical
    JSON without `signature`, as a commit is, so an index has the standing of the
    commit it is named by. `kind` is 'commit' (a delta) or 'snapshot' (the whole head)."""
    schema        : Safe_Str__Schema_Version  = None     # 'pack_index_v1'
    kind          : Safe_Str__Index_Kind      = None     # 'commit' | 'snapshot'
    commit_id     : Safe_Str__Object_Id       = None
    parents       : list[Safe_Str__Object_Id]
    generation    : Safe_UInt
    tree_id       : Safe_Str__Object_Id       = None     # MUST equal the commit object's tree id
    timestamp_ms  : Safe_UInt__Timestamp
    data_packs    : list[Safe_Str__Pack_Name]            # packs an `at` may point into, by index (Phase 2)
    members       : list[Schema__Pack_Index__Member]
    author_key_id : Safe_Str__Author_Key_Id   = None
    signature     : Safe_Str__Signature       = None
