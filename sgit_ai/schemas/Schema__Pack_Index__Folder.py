from osbot_utils.type_safe.Type_Safe                       import Type_Safe
from sgit_ai.safe_types.Safe_Str__Object_Id                import Safe_Str__Object_Id
from sgit_ai.safe_types.Safe_Str__Schema_Version           import Safe_Str__Schema_Version
from sgit_ai.safe_types.Safe_Str__Index_Path               import Safe_Str__Index_Path
from sgit_ai.schemas.Schema__Pack_Index__Totals            import Schema__Pack_Index__Totals


class Schema__Pack_Index__Folder(Type_Safe):
    """A `folder:<path>` member (dev pack 01 §3.2): one folder's files and sub-folders,
    and the totals of the whole subtree below it. `files` is {name: entry as flatten()
    gives it}; `dirs` is {name: tree id}. A commit index carries one for every folder on
    a changed path; a snapshot index one for every folder (built as plain dicts of this
    shape: 58,062 typed objects would cost what the 0.25.0 work removed)."""
    schema  : Safe_Str__Schema_Version = None       # 'folder_v1'
    path    : Safe_Str__Index_Path     = None
    tree_id : Safe_Str__Object_Id      = None
    files   : dict
    dirs    : dict
    totals  : Schema__Pack_Index__Totals
