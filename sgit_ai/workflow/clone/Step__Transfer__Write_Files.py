"""Step 4 (transfer) — Write received transfer files to the local directory."""
import os

from sgit_ai.safe_types.Safe_Str__Step_Name                  import Safe_Str__Step_Name
from sgit_ai.schemas.workflow.clone.Schema__Transfer__State  import Schema__Transfer__State
from sgit_ai.workflow.Step                                   import Step

_SKIP_PREFIXES = ('__share__', '_share.', '__gallery__')


class Step__Transfer__Write_Files(Step):
    name          = Safe_Str__Step_Name('transfer-write-files')
    input_schema  = Schema__Transfer__State
    output_schema = Schema__Transfer__State

    def execute(self, input: Schema__Transfer__State, workspace) -> Schema__Transfer__State:
        directory      = str(input.directory) if input.directory else ''
        received_files = workspace.received_files or {}

        workspace.progress('step', f'Writing {len(received_files)} files')

        for path, content in received_files.items():
            top = path.split('/')[0]
            if any(top.startswith(p) for p in _SKIP_PREFIXES):
                continue
            full_path = os.path.join(directory, path)
            parent    = os.path.dirname(full_path)
            if parent and parent != directory:
                os.makedirs(parent, exist_ok=True)
            with open(full_path, 'wb') as f:
                f.write(content if isinstance(content, bytes) else content.encode('utf-8'))

        return Schema__Transfer__State.from_json(input.json())
