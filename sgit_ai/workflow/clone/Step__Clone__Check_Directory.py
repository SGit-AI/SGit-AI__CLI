"""Step 2 — Validate target directory and create the bare vault structure."""
import os

from sgit_ai.safe_types.Safe_Str__Step_Name               import Safe_Str__Step_Name
from sgit_ai.schemas.workflow.clone.Schema__Clone__State  import Schema__Clone__State
from sgit_ai.workflow.Step                                import Step


class Step__Clone__Check_Directory(Step):
    name          = Safe_Str__Step_Name('check-directory')
    input_schema  = Schema__Clone__State
    output_schema = Schema__Clone__State

    def execute(self, input: Schema__Clone__State, workspace) -> Schema__Clone__State:
        directory = str(input.directory)
        if os.path.exists(directory):
            entries = os.listdir(directory)
            if entries:
                raise RuntimeError(f'Directory is not empty: {directory}')
        os.makedirs(directory, exist_ok=True)

        from sgit_ai.storage.Vault__Storage import Vault__Storage
        storage = Vault__Storage()
        sg_dir  = storage.create_bare_structure(directory)
        workspace.ensure_managers(sg_dir)

        data          = input.json()
        data['sg_dir'] = sg_dir
        return Schema__Clone__State.from_json(data)
