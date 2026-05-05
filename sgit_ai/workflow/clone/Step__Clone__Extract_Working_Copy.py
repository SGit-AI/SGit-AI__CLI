"""Step 9 — Check out files from the HEAD commit into the working directory."""
import time

from sgit_ai.safe_types.Safe_Str__Step_Name               import Safe_Str__Step_Name
from sgit_ai.schemas.workflow.clone.Schema__Clone__State  import Schema__Clone__State
from sgit_ai.workflow.Step                                import Step


class Step__Clone__Extract_Working_Copy(Step):
    name          = Safe_Str__Step_Name('extract-working-copy')
    input_schema  = Schema__Clone__State
    output_schema = Schema__Clone__State

    def execute(self, input: Schema__Clone__State, workspace) -> Schema__Clone__State:
        sg_dir          = str(input.sg_dir)
        directory       = str(input.directory)
        named_commit_id = str(input.named_commit_id) if input.named_commit_id else ''
        read_key        = bytes.fromhex(str(input.read_key_hex))

        workspace.ensure_managers(sg_dir)

        t_checkout_ms = 0

        if named_commit_id and not input.sparse and not input.bare:
            workspace.progress('step', 'Extracting working copy')
            _t0        = time.monotonic()
            commit_obj = workspace.vc.load_commit(named_commit_id, read_key)
            workspace.sub_tree.checkout(directory, str(commit_obj.tree_id), read_key)
            t_checkout_ms = int((time.monotonic() - _t0) * 1000)

        data                  = input.json()
        data['t_checkout_ms'] = t_checkout_ms
        return Schema__Clone__State.from_json(data)
