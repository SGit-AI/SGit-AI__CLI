from osbot_utils.type_safe.Type_Safe                       import Type_Safe
from osbot_utils.type_safe.primitives.core.Safe_UInt        import Safe_UInt
from sgit_ai.safe_types.Safe_Str__Object_Id                import Safe_Str__Object_Id
from sgit_ai.safe_types.Safe_Str__Schema_Version           import Safe_Str__Schema_Version
from sgit_ai.safe_types.Safe_UInt__Timestamp               import Safe_UInt__Timestamp
from sgit_ai.schemas.Schema__Pack_Index__Change            import Schema__Pack_Index__Change


class Schema__Pack_Index__Changes(Type_Safe):
    """The `changes` member of a commit index (dev pack 01 §3.3): what the commit changed
    against its first parent, with the header's commit fields repeated so the member
    stands alone."""
    schema       : Safe_Str__Schema_Version = None       # 'changes_v1'
    commit_id    : Safe_Str__Object_Id      = None
    parents      : list[Safe_Str__Object_Id]
    generation   : Safe_UInt
    timestamp_ms : Safe_UInt__Timestamp
    tree_id      : Safe_Str__Object_Id      = None
    changes      : list[Schema__Pack_Index__Change]
