"""Step 1 — Build backup zip and write sha256 sidecar."""
from sgit_ai.safe_types.Safe_Str__Step_Name                        import Safe_Str__Step_Name
from sgit_ai.safe_types.Safe_Str__File_Path                        import Safe_Str__File_Path
from sgit_ai.safe_types.Safe_Str__Vault_Id                         import Safe_Str__Vault_Id
from sgit_ai.safe_types.Safe_Str__SHA256                           import Safe_Str__SHA256
from sgit_ai.safe_types.Safe_UInt__Byte_Size                       import Safe_UInt__Byte_Size
from sgit_ai.safe_types.Safe_UInt__File_Count                      import Safe_UInt__File_Count
from sgit_ai.schemas.workflow.backup.Schema__Backup__State         import Schema__Backup__State
from sgit_ai.workflow.Step                                         import Step


class Step__Backup__Build_Zip(Step):
    name          = Safe_Str__Step_Name('build-zip')
    input_schema  = Schema__Backup__State
    output_schema = Schema__Backup__State

    def execute(self, input: Schema__Backup__State, workspace) -> Schema__Backup__State:
        from sgit_ai.core.actions.backup.Vault__Backup import Vault__Backup

        directory    = str(input.directory)
        output_dir   = str(input.output_dir) if input.output_dir else None
        label        = str(input.label) if input.label else 'manual'
        includes_key = input.includes_key

        result = Vault__Backup().backup(
            directory   = directory,
            output_dir  = output_dir,
            label       = label,
            include_key = includes_key,
        )

        return Schema__Backup__State(
            directory    = input.directory,
            output_dir   = input.output_dir,
            label        = input.label,
            includes_key = includes_key,
            vault_id     = Safe_Str__Vault_Id(result['vault_id']),
            zip_path     = Safe_Str__File_Path(result['zip_path']),
            sha256       = Safe_Str__SHA256(result['sha256']),
            byte_size    = Safe_UInt__Byte_Size(result['byte_size']),
            object_count = Safe_UInt__File_Count(result['object_count']),
        )
