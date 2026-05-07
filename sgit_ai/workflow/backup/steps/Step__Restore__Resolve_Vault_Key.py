from sgit_ai.safe_types.Safe_Str__Step_Name                        import Safe_Str__Step_Name
from sgit_ai.schemas.workflow.backup.Schema__Restore__State        import Schema__Restore__State
from sgit_ai.workflow.Step                                         import Step


class Step__Restore__Resolve_Vault_Key(Step):
    name          = Safe_Str__Step_Name('resolve-vault-key')
    input_schema  = Schema__Restore__State
    output_schema = Schema__Restore__State

    def execute(self, input: Schema__Restore__State, workspace) -> Schema__Restore__State:
        mode = str(input.mode) if input.mode else 'expanded'
        if mode == 'bare':
            return input

        from sgit_ai.core.actions.backup.Vault__Restore import Vault__Restore

        vault_key = str(input.vault_key) if input.vault_key else None

        try:
            resolved = Vault__Restore()._resolve_vault_key(str(input.zip_path), vault_key)
        except RuntimeError:
            if workspace.vault_key_prompt_fn:
                resolved = workspace.vault_key_prompt_fn()
                if not resolved:
                    raise
            else:
                raise

        data              = input.json()
        data['vault_key'] = resolved
        return Schema__Restore__State.from_json(data)
