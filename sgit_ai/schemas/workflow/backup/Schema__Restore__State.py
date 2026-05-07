"""Accumulating state schema shared by all restore workflow steps."""
from osbot_utils.type_safe.Type_Safe              import Type_Safe
from sgit_ai.safe_types.Safe_Str__File_Path       import Safe_Str__File_Path
from sgit_ai.safe_types.Safe_Str__Vault_Id        import Safe_Str__Vault_Id
from sgit_ai.safe_types.Safe_Str__Vault_Key       import Safe_Str__Vault_Key
from sgit_ai.safe_types.Safe_Str__Restore_Mode    import Safe_Str__Restore_Mode
from sgit_ai.safe_types.Safe_Str__SHA256          import Safe_Str__SHA256
from sgit_ai.safe_types.Safe_UInt__Timestamp      import Safe_UInt__Timestamp


class Schema__Restore__State(Type_Safe):
    """Accumulating state passed through all restore workflow steps."""

    # ── caller-supplied inputs ───────────────────────────────────────────
    zip_source   : Safe_Str__File_Path    = None   # path or vault-dir:backup-id
    destination  : Safe_Str__File_Path    = None
    mode         : Safe_Str__Restore_Mode = None   # 'bare' or 'expanded'
    vault_key    : Safe_Str__Vault_Key    = None   # optional, for expanded mode

    # ── step 1: validate_destination ────────────────────────────────────
    zip_path     : Safe_Str__File_Path    = None   # resolved absolute zip path

    # ── step 2: verify_zip_integrity ────────────────────────────────────
    sha256       : Safe_Str__SHA256       = None

    # ── step 3: extract_bare ────────────────────────────────────────────
    sg_dir       : Safe_Str__File_Path    = None
    vault_id     : Safe_Str__Vault_Id     = None

    # ── step 4: resolve_vault_key ────────────────────────────────────────
    # vault_key updated in-place (already in inputs above)

    # ── step 5: extract_working_copy ────────────────────────────────────
    t_checkout_ms : Safe_UInt__Timestamp  = None
