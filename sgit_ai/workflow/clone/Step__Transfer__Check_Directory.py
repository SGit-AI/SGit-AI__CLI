"""Step 2 (transfer) — Validate the target directory is empty or creatable."""
import os

from sgit_ai.safe_types.Safe_Str__Step_Name                  import Safe_Str__Step_Name
from sgit_ai.schemas.workflow.clone.Schema__Transfer__State  import Schema__Transfer__State
from sgit_ai.workflow.Step                                   import Step


class Step__Transfer__Check_Directory(Step):
    name          = Safe_Str__Step_Name('transfer-check-directory')
    input_schema  = Schema__Transfer__State
    output_schema = Schema__Transfer__State

    def execute(self, input: Schema__Transfer__State, workspace) -> Schema__Transfer__State:
        directory = str(input.directory) if input.directory else ''
        if not directory:
            raise RuntimeError('directory is required for transfer clone')

        if os.path.exists(directory):
            entries = os.listdir(directory)
            if entries:
                raise RuntimeError(f'Directory is not empty: {directory}')
        os.makedirs(directory, exist_ok=True)

        workspace.progress('step', 'Validated target directory')
        return Schema__Transfer__State.from_json(input.json())
