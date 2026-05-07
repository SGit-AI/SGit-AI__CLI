from sgit_ai.safe_types.Safe_Str__Step_Name                        import Safe_Str__Step_Name
from sgit_ai.safe_types.Safe_Str__SHA256                           import Safe_Str__SHA256
from sgit_ai.schemas.workflow.backup.Schema__Restore__State        import Schema__Restore__State
from sgit_ai.workflow.Step                                         import Step


class Step__Restore__Verify_Zip_Integrity(Step):
    name          = Safe_Str__Step_Name('verify-zip-integrity')
    input_schema  = Schema__Restore__State
    output_schema = Schema__Restore__State

    def execute(self, input: Schema__Restore__State, workspace) -> Schema__Restore__State:
        from sgit_ai.core.actions.backup.Vault__Restore import Vault__Restore

        sha256_hex = Vault__Restore()._verify_integrity(str(input.zip_path))

        data           = input.json()
        data['sha256'] = sha256_hex
        return Schema__Restore__State.from_json(data)
