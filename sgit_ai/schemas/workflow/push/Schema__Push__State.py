"""Accumulating state schema shared by all push workflow steps."""
from osbot_utils.type_safe.Type_Safe              import Type_Safe
from sgit_ai.safe_types.Safe_Str__Vault_Key       import Safe_Str__Vault_Key
from sgit_ai.safe_types.Safe_Str__File_Path       import Safe_Str__File_Path
from sgit_ai.safe_types.Safe_Str__Vault_Id        import Safe_Str__Vault_Id
from sgit_ai.safe_types.Safe_Str__Index_Id        import Safe_Str__Index_Id
from sgit_ai.safe_types.Safe_Str__Write_Key       import Safe_Str__Write_Key
from sgit_ai.safe_types.Safe_Str__Branch_Id       import Safe_Str__Branch_Id
from sgit_ai.safe_types.Safe_Str__Ref_Id          import Safe_Str__Ref_Id
from sgit_ai.safe_types.Safe_Str__Commit_Id       import Safe_Str__Commit_Id
from sgit_ai.safe_types.Safe_UInt__File_Count     import Safe_UInt__File_Count


class Schema__Push__State(Type_Safe):
    """Accumulating state passed through all push workflow steps."""

    # ── caller-supplied inputs ───────────────────────────────────────────
    vault_key             : Safe_Str__Vault_Key   = None
    directory             : Safe_Str__File_Path   = None
    force                 : bool                  = False

    # ── step 1: derive_keys ─────────────────────────────────────────────
    vault_id              : Safe_Str__Vault_Id    = None
    read_key_hex          : Safe_Str__Write_Key   = None
    write_key_hex         : Safe_Str__Write_Key   = None
    branch_index_file_id  : Safe_Str__Index_Id    = None

    # ── step 2: check_clean ──────────────────────────────────────────────
    sg_dir                : Safe_Str__File_Path   = None
    working_copy_clean    : bool                  = False

    # ── step 3: local_inventory ──────────────────────────────────────────
    clone_branch_id       : Safe_Str__Branch_Id   = None
    clone_ref_id          : Safe_Str__Ref_Id      = None
    named_ref_id          : Safe_Str__Ref_Id      = None
    clone_commit_id       : Safe_Str__Commit_Id   = None
    named_commit_id       : Safe_Str__Commit_Id   = None
    n_local_only_objects  : Safe_UInt__File_Count = None

    # ── step 4: fast_forward_check ───────────────────────────────────────
    remote_commit_id      : Safe_Str__Commit_Id   = None
    can_fast_forward      : bool                  = False

    # ── step 5: upload (B08-dependent — stub) ────────────────────────────
    n_objects_uploaded    : Safe_UInt__File_Count = None

    # ── step 6: update_remote_ref ────────────────────────────────────────
    remote_ref_updated    : bool                  = False
