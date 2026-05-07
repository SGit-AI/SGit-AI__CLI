from sgit_ai.safe_types.Safe_Str__Step_Name                        import Safe_Str__Step_Name
from sgit_ai.safe_types.Safe_Str__File_Path                        import Safe_Str__File_Path
from sgit_ai.schemas.workflow.backup.Schema__Restore__State        import Schema__Restore__State
from sgit_ai.workflow.Step                                         import Step


class Step__Restore__Validate_Destination(Step):
    name          = Safe_Str__Step_Name('validate-destination')
    input_schema  = Schema__Restore__State
    output_schema = Schema__Restore__State

    def execute(self, input: Schema__Restore__State, workspace) -> Schema__Restore__State:
        from sgit_ai.core.actions.backup.Vault__Restore import Vault__Restore

        restore  = Vault__Restore()
        zip_path = restore._resolve_source(str(input.zip_source))
        restore._validate_destination(str(input.destination))

        data             = input.json()
        data['zip_path'] = zip_path
        return Schema__Restore__State.from_json(data)
