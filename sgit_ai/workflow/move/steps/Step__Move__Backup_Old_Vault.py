"""Step 7 — Create a backup zip of the old vault. Destructive boundary starts here."""
from sgit_ai.safe_types.Safe_Str__File_Path  import Safe_Str__File_Path
from sgit_ai.safe_types.Safe_Str__Step_Name  import Safe_Str__Step_Name
from sgit_ai.schemas.workflow.move.Schema__Move__State import Schema__Move__State
from sgit_ai.workflow.Step                   import Step


class Step__Move__Backup_Old_Vault(Step):
    name          = Safe_Str__Step_Name('backup-old-vault')
    input_schema  = Schema__Move__State
    output_schema = Schema__Move__State

    def execute(self, input: Schema__Move__State, workspace) -> Schema__Move__State:
        from sgit_ai.core.actions.backup.Vault__Backup import Vault__Backup

        if input.dry_run:
            state_dict = input.json()
            state_dict['backup_zip_path'] = 'dry-run-backup.zip'
            return Schema__Move__State.from_json(state_dict)

        directory = str(input.directory)
        result = Vault__Backup().backup(
            directory   = directory,
            label       = 'pre-move',
            include_key = False,
            allow_dirty = True,
        )

        state_dict = input.json()
        state_dict['backup_zip_path'] = result['zip_path']
        return Schema__Move__State.from_json(state_dict)
