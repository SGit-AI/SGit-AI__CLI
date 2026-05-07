from sgit_ai.safe_types.Safe_Str__Step_Name                        import Safe_Str__Step_Name
from sgit_ai.safe_types.Safe_UInt__Timestamp                       import Safe_UInt__Timestamp
from sgit_ai.schemas.workflow.backup.Schema__Restore__State        import Schema__Restore__State
from sgit_ai.workflow.Step                                         import Step


class Step__Restore__Extract_Working_Copy(Step):
    name          = Safe_Str__Step_Name('extract-working-copy')
    input_schema  = Schema__Restore__State
    output_schema = Schema__Restore__State

    def execute(self, input: Schema__Restore__State, workspace) -> Schema__Restore__State:
        mode = str(input.mode) if input.mode else 'expanded'
        if mode == 'bare':
            data                    = input.json()
            data['t_checkout_ms']   = 0
            return Schema__Restore__State.from_json(data)

        from sgit_ai.core.actions.backup.Vault__Restore import Vault__Restore

        vault_key = str(input.vault_key) if input.vault_key else None
        t_ms = Vault__Restore()._extract_working_copy(
            destination = str(input.destination),
            sg_dir      = str(input.sg_dir),
            vault_key   = vault_key,
        )

        data                  = input.json()
        data['t_checkout_ms'] = t_ms
        return Schema__Restore__State.from_json(data)
