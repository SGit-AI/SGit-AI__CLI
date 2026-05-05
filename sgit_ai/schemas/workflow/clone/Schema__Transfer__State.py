"""Accumulating state schema for the Workflow__Clone__Transfer pipeline."""
from osbot_utils.type_safe.Type_Safe                    import Type_Safe
from sgit_ai.safe_types.Safe_Str__File_Path             import Safe_Str__File_Path
from sgit_ai.safe_types.Safe_Str__Simple_Token          import Safe_Str__Simple_Token
from sgit_ai.safe_types.Safe_Str__Vault_Id              import Safe_Str__Vault_Id
from sgit_ai.safe_types.Safe_Str__Branch_Id             import Safe_Str__Branch_Id
from sgit_ai.safe_types.Safe_UInt__File_Count           import Safe_UInt__File_Count


class Schema__Transfer__State(Type_Safe):
    """Accumulating state for the transfer clone workflow.

    Received files (dict[str, bytes]) live in Transfer__Workspace.received_files,
    not in the schema, because dict[str, bytes] is not Type_Safe serialisable.
    """

    # ── caller-supplied inputs ───────────────────────────────────────────
    token_str   : Safe_Str__Simple_Token = None
    directory   : Safe_Str__File_Path    = None

    # ── step 1: receive ─────────────────────────────────────────────────
    file_count  : Safe_UInt__File_Count  = None

    # ── step 3: init_vault ───────────────────────────────────────────────
    new_token   : Safe_Str__Simple_Token = None
    vault_id    : Safe_Str__Vault_Id     = None

    # ── step 4: write_files (no new fields) ─────────────────────────────

    # ── step 5: commit_and_configure ────────────────────────────────────
    branch_id   : Safe_Str__Branch_Id    = None
    share_token : Safe_Str__Simple_Token = None
