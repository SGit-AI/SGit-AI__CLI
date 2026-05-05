"""Step 1 — Derive cryptographic keys from vault_key."""
from sgit_ai.safe_types.Safe_Str__Step_Name               import Safe_Str__Step_Name
from sgit_ai.safe_types.Safe_Str__Index_Id                import Safe_Str__Index_Id
from sgit_ai.safe_types.Safe_Str__Vault_Id                import Safe_Str__Vault_Id
from sgit_ai.safe_types.Safe_Str__Read_Key                import Safe_Str__Read_Key
from sgit_ai.safe_types.Safe_Str__Write_Key               import Safe_Str__Write_Key
from sgit_ai.schemas.workflow.clone.Schema__Clone__State  import Schema__Clone__State
from sgit_ai.workflow.Step                                import Step


class Step__Clone__Derive_Keys(Step):
    name          = Safe_Str__Step_Name('derive-keys')
    input_schema  = Schema__Clone__State
    output_schema = Schema__Clone__State

    def execute(self, input: Schema__Clone__State, workspace) -> Schema__Clone__State:
        vault_key = str(input.vault_key)
        keys      = workspace.sync_client._derive_keys_from_stored_key(vault_key)
        workspace.progress('step', 'Deriving vault keys')
        return Schema__Clone__State(
            vault_key             = input.vault_key,
            directory             = input.directory,
            sparse                = input.sparse,
            vault_id              = Safe_Str__Vault_Id(keys['vault_id']),
            branch_index_file_id  = Safe_Str__Index_Id(keys['branch_index_file_id']),
            read_key_hex          = Safe_Str__Read_Key(keys['read_key']),
        )
