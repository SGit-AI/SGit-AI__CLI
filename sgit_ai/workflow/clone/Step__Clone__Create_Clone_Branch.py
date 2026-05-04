"""Step 8 — Create the local clone branch and update the branch index."""
import json
import os
import time

from sgit_ai.safe_types.Safe_Str__Step_Name               import Safe_Str__Step_Name
from sgit_ai.schemas.workflow.clone.Schema__Clone__State  import Schema__Clone__State
from sgit_ai.workflow.Step                                import Step


class Step__Clone__Create_Clone_Branch(Step):
    name          = Safe_Str__Step_Name('create-clone-branch')
    input_schema  = Schema__Clone__State
    output_schema = Schema__Clone__State

    def execute(self, input: Schema__Clone__State, workspace) -> Schema__Clone__State:
        sg_dir          = str(input.sg_dir)
        directory       = str(input.directory)
        index_id        = str(input.index_id)
        named_commit_id = str(input.named_commit_id) if input.named_commit_id else ''
        named_branch_id = str(input.named_branch_id)
        read_key        = bytes.fromhex(str(input.read_key_hex))

        workspace.ensure_managers(sg_dir)
        workspace.progress('step', 'Creating clone branch')

        timestamp_ms = int(time.time() * 1000)
        clone_branch = workspace.branch_manager.create_clone_branch(
            directory, 'local', read_key,
            creator_branch_id=named_branch_id,
            timestamp_ms=timestamp_ms,
        )

        if named_commit_id:
            workspace.ref_manager.write_ref(
                str(clone_branch.head_ref_id), named_commit_id, read_key)

        branch_index = workspace.branch_manager.load_branch_index(directory, index_id, read_key)
        branch_index.branches.append(clone_branch)
        workspace.branch_manager.save_branch_index(
            directory, branch_index, read_key, index_file_id=index_id)

        # Save pending registration data
        pending_path = os.path.join(workspace.storage.local_dir(directory),
                                    'pending_registration.json')
        pending_data = dict(
            index_id      = index_id,
            head_ref_id   = str(clone_branch.head_ref_id),
            public_key_id = str(clone_branch.public_key_id),
            commit_id     = named_commit_id or '',
        )
        with open(pending_path, 'w') as f:
            json.dump(pending_data, f, indent=2)
        workspace.storage.chmod_local_file(pending_path)
        workspace.progress('step', 'Clone branch will be registered on first push')

        data                      = input.json()
        data['clone_branch_id']   = str(clone_branch.branch_id)
        data['clone_ref_id']      = str(clone_branch.head_ref_id)
        data['clone_public_key_id'] = str(clone_branch.public_key_id)
        return Schema__Clone__State.from_json(data)
