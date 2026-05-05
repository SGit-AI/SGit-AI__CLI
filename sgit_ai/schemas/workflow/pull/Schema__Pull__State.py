"""Accumulating state schema shared by all pull workflow steps."""
from osbot_utils.type_safe.Type_Safe              import Type_Safe
from osbot_utils.type_safe.primitives.core.Safe_Str import Safe_Str
from sgit_ai.safe_types.Safe_Str__Vault_Key       import Safe_Str__Vault_Key
from sgit_ai.safe_types.Safe_Str__File_Path       import Safe_Str__File_Path
from sgit_ai.safe_types.Safe_Str__Vault_Id        import Safe_Str__Vault_Id
from sgit_ai.safe_types.Safe_Str__Index_Id        import Safe_Str__Index_Id
from sgit_ai.safe_types.Safe_Str__Read_Key        import Safe_Str__Read_Key
from sgit_ai.safe_types.Safe_Str__Write_Key       import Safe_Str__Write_Key
from sgit_ai.safe_types.Safe_Str__Branch_Id       import Safe_Str__Branch_Id
from sgit_ai.safe_types.Safe_Str__Ref_Id          import Safe_Str__Ref_Id
from sgit_ai.safe_types.Safe_Str__Commit_Id       import Safe_Str__Commit_Id
from sgit_ai.safe_types.Safe_UInt__File_Count     import Safe_UInt__File_Count


class Schema__Pull__State(Type_Safe):
    """Accumulating state passed through all pull workflow steps."""

    # ── caller-supplied inputs ───────────────────────────────────────────
    vault_key             : Safe_Str__Vault_Key   = None
    directory             : Safe_Str__File_Path   = None

    # ── step 1: derive_keys ─────────────────────────────────────────────
    vault_id              : Safe_Str__Vault_Id    = None
    read_key_hex          : Safe_Str__Read_Key    = None
    branch_index_file_id  : Safe_Str__Index_Id    = None

    # ── step 2: load_branch_info ─────────────────────────────────────────
    sg_dir                : Safe_Str__File_Path   = None
    clone_branch_id       : Safe_Str__Branch_Id   = None
    clone_ref_id          : Safe_Str__Ref_Id      = None
    named_ref_id          : Safe_Str__Ref_Id      = None
    clone_commit_id       : Safe_Str__Commit_Id   = None
    clone_public_key_id   : Safe_Str              = None   # for signing merge commits
    clone_branch_name     : Safe_Str              = None   # for merge commit message
    named_branch_name     : Safe_Str              = None   # for merge commit message

    # ── step 3: fetch_remote_ref ─────────────────────────────────────────
    named_commit_id       : Safe_Str__Commit_Id   = None
    remote_reachable      : bool                  = True

    # ── step 4: fetch_missing ────────────────────────────────────────────
    n_objects_fetched     : Safe_UInt__File_Count = None

    # ── step 5: merge ────────────────────────────────────────────────────
    merge_status          : Safe_Str              = None  # 'up_to_date' | 'fast_forward' | 'merge' | 'conflict'
    n_conflicts           : Safe_UInt__File_Count = None
    merge_commit_id       : Safe_Str__Commit_Id   = None
    added_files           : list                  = None  # paths added by merge
    modified_files        : list                  = None  # paths modified by merge
    deleted_files         : list                  = None  # paths deleted by merge
    conflict_paths        : list                  = None  # paths with merge conflicts

    # ── step 6: update_working_copy — no new schema fields; working copy restored from merged tree
