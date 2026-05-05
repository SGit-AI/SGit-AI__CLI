"""Step 1 (read-only) — Validate vault_id + read_key_hex and derive branch_index_file_id."""
from sgit_ai.safe_types.Safe_Str__Index_Id                import Safe_Str__Index_Id
from sgit_ai.safe_types.Safe_Str__Step_Name               import Safe_Str__Step_Name
from sgit_ai.schemas.workflow.clone.Schema__Clone__State  import Schema__Clone__State
from sgit_ai.workflow.Step                                import Step


class Step__Clone__ReadOnly__Set_Keys(Step):
    name          = Safe_Str__Step_Name('readonly-set-keys')
    input_schema  = Schema__Clone__State
    output_schema = Schema__Clone__State

    def execute(self, input: Schema__Clone__State, workspace) -> Schema__Clone__State:
        vault_id     = str(input.vault_id)     if input.vault_id     else ''
        read_key_hex = str(input.read_key_hex) if input.read_key_hex else ''

        if not vault_id:
            raise RuntimeError('vault_id is required for read-only clone')
        if not read_key_hex:
            raise RuntimeError('read_key_hex is required for read-only clone')

        workspace.progress('step', 'Setting up read-only keys')

        crypto = workspace.sync_client.crypto
        keys   = crypto.import_read_key(read_key_hex, vault_id)

        data                        = input.json()
        data['branch_index_file_id'] = keys['branch_index_file_id']
        return Schema__Clone__State.from_json(data)
