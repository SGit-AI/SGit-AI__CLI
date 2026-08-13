from sgit_ai.safe_types.Safe_Str__Step_Name                        import Safe_Str__Step_Name
from sgit_ai.safe_types.Safe_Str__Vault_Id                         import Safe_Str__Vault_Id
from sgit_ai.safe_types.Safe_Str__File_Path                        import Safe_Str__File_Path
from sgit_ai.schemas.workflow.backup.Schema__Restore__State        import Schema__Restore__State
from sgit_ai.workflow.Step                                         import Step


class Step__Restore__Extract_Bare(Step):
    name          = Safe_Str__Step_Name('extract-bare')
    input_schema  = Schema__Restore__State
    output_schema = Schema__Restore__State

    def execute(self, input: Schema__Restore__State, workspace) -> Schema__Restore__State:
        from sgit_ai.core.actions.backup.Vault__Restore import Vault__Restore

        sg_dir, vault_id = Vault__Restore()._extract_bare(
            str(input.zip_path), str(input.destination)
        )

        data             = input.json()
        data['sg_dir']   = sg_dir
        data['vault_id'] = vault_id
        return Schema__Restore__State.from_json(data)
