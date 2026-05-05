"""Step 3 — Fetch the named branch ref from the remote server."""
import os

from sgit_ai.safe_types.Safe_Str__Step_Name              import Safe_Str__Step_Name
from sgit_ai.safe_types.Safe_Str__Commit_Id              import Safe_Str__Commit_Id
from sgit_ai.schemas.workflow.pull.Schema__Pull__State   import Schema__Pull__State
from sgit_ai.workflow.Step                               import Step


class Step__Pull__Fetch_Remote_Ref(Step):
    name          = Safe_Str__Step_Name('fetch-remote-ref')
    input_schema  = Schema__Pull__State
    output_schema = Schema__Pull__State

    def execute(self, input: Schema__Pull__State, workspace) -> Schema__Pull__State:
        sg_dir   = str(input.sg_dir)
        read_key = bytes.fromhex(str(input.read_key_hex))
        vault_id = str(input.vault_id)
        named_ref_id = str(input.named_ref_id)

        workspace.ensure_managers(sg_dir)
        workspace.progress('step', 'Fetching remote ref')

        named_ref_file_id = f'bare/refs/{named_ref_id}'
        remote_reachable  = False
        try:
            remote_ref_data = workspace.sync_client.api.read(vault_id, named_ref_file_id)
            if remote_ref_data:
                ref_path = os.path.join(sg_dir, named_ref_file_id)
                os.makedirs(os.path.dirname(ref_path), exist_ok=True)
                with open(ref_path, 'wb') as f:
                    f.write(remote_ref_data)
                remote_reachable = True
        except Exception as exc:
            workspace.progress('warn', f'Could not fetch remote ref: {exc}')

        named_commit_id = workspace.ref_manager.read_ref(named_ref_id, read_key) or ''

        out = Schema__Pull__State(
            vault_key             = input.vault_key,
            directory             = input.directory,
            sg_dir                = input.sg_dir,
            vault_id              = input.vault_id,
            branch_index_file_id  = input.branch_index_file_id,
            read_key_hex          = input.read_key_hex,
            clone_branch_id       = input.clone_branch_id,
            clone_ref_id          = input.clone_ref_id,
            named_ref_id          = input.named_ref_id,
            clone_commit_id       = input.clone_commit_id,
            named_commit_id       = Safe_Str__Commit_Id(named_commit_id) if named_commit_id else None,
            remote_reachable      = remote_reachable,
        )
        return out
