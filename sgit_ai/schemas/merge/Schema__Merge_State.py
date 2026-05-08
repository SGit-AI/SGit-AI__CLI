from osbot_utils.type_safe.Type_Safe          import Type_Safe
from sgit_ai.safe_types.Safe_UInt__Vault_Version import Safe_UInt__Vault_Version
from sgit_ai.safe_types.Safe_Str__Commit_Id      import Safe_Str__Commit_Id
from sgit_ai.safe_types.Safe_Str__ISO_Timestamp  import Safe_Str__ISO_Timestamp
from sgit_ai.safe_types.Safe_Str__File_Path      import Safe_Str__File_Path


class Schema__Merge_State(Type_Safe):
    schema_version   : Safe_UInt__Vault_Version = None
    ours_commit_id   : Safe_Str__Commit_Id      = None
    theirs_commit_id : Safe_Str__Commit_Id      = None
    lca_id           : Safe_Str__Commit_Id      = None
    started_at       : Safe_Str__ISO_Timestamp  = None
    conflict_paths   : list[Safe_Str__File_Path]
    resolved_paths   : list[Safe_Str__File_Path]
