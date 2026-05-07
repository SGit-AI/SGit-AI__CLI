"""Accumulating state schema shared by all vault-move workflow steps."""
from osbot_utils.type_safe.Type_Safe             import Type_Safe
from sgit_ai.safe_types.Safe_Str__Base_URL       import Safe_Str__Base_URL
from sgit_ai.safe_types.Safe_Str__Commit_Message import Safe_Str__Commit_Message
from sgit_ai.safe_types.Safe_Str__File_Path      import Safe_Str__File_Path
from sgit_ai.safe_types.Safe_Str__ISO_Timestamp  import Safe_Str__ISO_Timestamp
from sgit_ai.safe_types.Safe_Str__Vault_Id       import Safe_Str__Vault_Id
from sgit_ai.safe_types.Safe_Str__Vault_Key      import Safe_Str__Vault_Key
from sgit_ai.safe_types.Safe_UInt__Vault_Version import Safe_UInt__Vault_Version


class Schema__Move__State(Type_Safe):
    # ── caller-supplied inputs ────────────────────────────────────────────
    directory      : Safe_Str__File_Path      = None   # vault directory
    new_vault_key  : Safe_Str__Vault_Key      = None   # auto-generated if None
    target_api_url : Safe_Str__Base_URL       = None   # same server if None
    reason         : Safe_Str__Commit_Message = None
    dry_run        : bool                     = False

    # ── step 1: validate_local ───────────────────────────────────────────
    old_vault_id   : Safe_Str__Vault_Id       = None
    old_api_url    : Safe_Str__Base_URL       = None
    object_count   : Safe_UInt__Vault_Version = None   # reusing for generic uint

    # ── step 2: derive_new_keys ──────────────────────────────────────────
    new_vault_id   : Safe_Str__Vault_Id       = None
    key_generation : Safe_UInt__Vault_Version = None

    # ── step 3: build_temp_vault ─────────────────────────────────────────
    temp_vault_dir : Safe_Str__File_Path      = None   # .sg_vault_new/

    # ── step 4: write_sentinel_commits ──────────────────────────────────
    sentinel_commit_id : Safe_Str__File_Path  = None   # first sentinel commit id

    # ── step 5: push_to_target ──────────────────────────────────────────
    push_completed : bool                     = False

    # ── step 6: verify_target ───────────────────────────────────────────
    verify_completed : bool                   = False

    # ── step 7: backup_old_vault ─────────────────────────────────────────
    backup_zip_path : Safe_Str__File_Path     = None

    # ── step 8: delete_source ────────────────────────────────────────────
    renamed_at      : Safe_Str__ISO_Timestamp = None
    server_deleted  : bool                    = False
