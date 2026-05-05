"""Step 9 (read-only) — Write clone_mode.json in READ_ONLY mode (no vault_key file)."""
import json

from sgit_ai.safe_types.Safe_Str__Step_Name               import Safe_Str__Step_Name
from sgit_ai.schemas.workflow.clone.Schema__Clone__State  import Schema__Clone__State
from sgit_ai.workflow.Step                                import Step


class Step__Clone__ReadOnly__Setup_Config(Step):
    name          = Safe_Str__Step_Name('readonly-setup-config')
    input_schema  = Schema__Clone__State
    output_schema = Schema__Clone__State

    def execute(self, input: Schema__Clone__State, workspace) -> Schema__Clone__State:
        from sgit_ai.safe_types.Enum__Clone_Mode    import Enum__Clone_Mode
        from sgit_ai.schemas.Schema__Clone_Mode     import Schema__Clone_Mode

        directory    = str(input.directory)
        vault_id     = str(input.vault_id)     if input.vault_id     else ''
        read_key_hex = str(input.read_key_hex) if input.read_key_hex else ''

        workspace.progress('step', 'Setting up read-only local config')

        clone_mode      = Schema__Clone_Mode(mode     = Enum__Clone_Mode.READ_ONLY,
                                             vault_id = vault_id,
                                             read_key = read_key_hex)
        clone_mode_path = workspace.storage.clone_mode_path(directory)
        with open(clone_mode_path, 'w') as f:
            json.dump(clone_mode.json(), f, indent=2)
        workspace.storage.chmod_local_file(clone_mode_path)

        return Schema__Clone__State.from_json(input.json())
