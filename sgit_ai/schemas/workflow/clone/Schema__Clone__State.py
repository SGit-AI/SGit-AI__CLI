"""Accumulating state schema shared by all 10 clone workflow steps."""
from osbot_utils.type_safe.Type_Safe              import Type_Safe
from sgit_ai.safe_types.Safe_Str__Vault_Key       import Safe_Str__Vault_Key
from sgit_ai.safe_types.Safe_Str__File_Path       import Safe_Str__File_Path
from sgit_ai.safe_types.Safe_Str__Vault_Id        import Safe_Str__Vault_Id
from sgit_ai.safe_types.Safe_Str__Index_Id        import Safe_Str__Index_Id
from sgit_ai.safe_types.Safe_Str__Write_Key       import Safe_Str__Write_Key
from sgit_ai.safe_types.Safe_Str__Branch_Id       import Safe_Str__Branch_Id
from sgit_ai.safe_types.Safe_Str__Ref_Id          import Safe_Str__Ref_Id
from sgit_ai.safe_types.Safe_Str__Commit_Id       import Safe_Str__Commit_Id
from sgit_ai.safe_types.Safe_Str__Object_Id       import Safe_Str__Object_Id
from sgit_ai.safe_types.Safe_Str__Key_Id          import Safe_Str__Key_Id
from sgit_ai.safe_types.Safe_UInt__File_Count     import Safe_UInt__File_Count
from sgit_ai.safe_types.Safe_UInt__Timestamp      import Safe_UInt__Timestamp


class Schema__Clone__State(Type_Safe):
    """Accumulating state passed through all 10 clone steps; non-serialisable managers live in Clone__Workspace."""

    # ── caller-supplied inputs ───────────────────────────────────────────
    vault_key             : Safe_Str__Vault_Key   = None
    directory             : Safe_Str__File_Path   = None
    sparse                : bool                  = False

    # ── step 1: derive_keys ─────────────────────────────────────────────
    vault_id              : Safe_Str__Vault_Id    = None
    branch_index_file_id  : Safe_Str__Index_Id    = None
    read_key_hex          : Safe_Str__Write_Key   = None

    # ── step 2: check_directory ─────────────────────────────────────────
    sg_dir                : Safe_Str__File_Path   = None

    # ── step 3: download_index ──────────────────────────────────────────
    named_branch_id       : Safe_Str__Branch_Id   = None
    named_ref_id          : Safe_Str__Ref_Id      = None
    index_id              : Safe_Str__Index_Id    = None

    # ── step 4: download_branch_meta ────────────────────────────────────
    named_commit_id       : Safe_Str__Commit_Id   = None

    # ── step 5: walk_commits ────────────────────────────────────────────
    n_commits             : Safe_UInt__File_Count = None
    root_tree_ids         : list[Safe_Str__Object_Id]
    t_commits_ms          : Safe_UInt__Timestamp  = None

    # ── step 6: walk_trees ──────────────────────────────────────────────
    n_trees               : Safe_UInt__File_Count = None
    t_trees_ms            : Safe_UInt__Timestamp  = None

    # ── step 7: download_blobs ──────────────────────────────────────────
    n_blobs               : Safe_UInt__File_Count = None
    t_blobs_ms            : Safe_UInt__Timestamp  = None

    # ── step 8: create_clone_branch ─────────────────────────────────────
    clone_branch_id       : Safe_Str__Branch_Id   = None
    clone_ref_id          : Safe_Str__Ref_Id      = None
    clone_public_key_id   : Safe_Str__Key_Id      = None

    # ── step 9: extract_working_copy ────────────────────────────────────
    t_checkout_ms         : Safe_UInt__Timestamp  = None

    # ── step 10: setup_local_config — no new schema fields; result built from state
