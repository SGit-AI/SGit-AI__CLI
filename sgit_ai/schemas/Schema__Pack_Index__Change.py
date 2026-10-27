from osbot_utils.type_safe.Type_Safe                       import Type_Safe
from osbot_utils.type_safe.primitives.core.Safe_UInt        import Safe_UInt
from sgit_ai.safe_types.Safe_Str__Object_Id                import Safe_Str__Object_Id
from sgit_ai.safe_types.Safe_Str__Index_Path               import Safe_Str__Index_Path
from sgit_ai.safe_types.Safe_Str__Content_Hash             import Safe_Str__Content_Hash
from sgit_ai.safe_types.Safe_Str__Content_Type             import Safe_Str__Content_Type
from sgit_ai.safe_types.Safe_Str__Change_Op                import Safe_Str__Change_Op


class Schema__Pack_Index__Change(Type_Safe):
    """One changed path of a commit against its first parent: op A (added), M (modified)
    or D (deleted); `old_blob` for M and D, the new entry's fields for A and M."""
    path         : Safe_Str__Index_Path     = None
    op           : Safe_Str__Change_Op      = None
    old_blob     : Safe_Str__Object_Id      = None
    new_blob     : Safe_Str__Object_Id      = None
    size         : Safe_UInt
    content_hash : Safe_Str__Content_Hash   = None
    content_type : Safe_Str__Content_Type   = None
    large        : bool                     = False
