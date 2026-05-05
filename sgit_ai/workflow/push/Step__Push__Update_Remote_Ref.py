"""Step 6 — Upload the local named-branch ref to the remote server."""
import os

from sgit_ai.safe_types.Safe_Str__Step_Name              import Safe_Str__Step_Name
from sgit_ai.schemas.workflow.push.Schema__Push__State   import Schema__Push__State
from sgit_ai.workflow.Step                               import Step


class Step__Push__Update_Remote_Ref(Step):
    name          = Safe_Str__Step_Name('update-remote-ref')
    input_schema  = Schema__Push__State
    output_schema = Schema__Push__State

    def execute(self, input: Schema__Push__State, workspace) -> Schema__Push__State:
        sg_dir           = str(input.sg_dir)
        vault_id         = str(input.vault_id)
        read_key         = bytes.fromhex(str(input.read_key_hex))
        named_ref_id     = str(input.named_ref_id)
        clone_commit_id  = str(input.clone_commit_id) if input.clone_commit_id else ''
        remote_commit_id = str(input.remote_commit_id) if input.remote_commit_id else ''

        workspace.ensure_managers(sg_dir)
        workspace.progress('step', 'Updating remote branch ref')

        remote_ref_updated = False
        if clone_commit_id and clone_commit_id != remote_commit_id:
            try:
                ref_data = workspace.ref_manager.encrypt_ref_value(clone_commit_id, read_key)
                workspace.sync_client.api.write(vault_id, f'bare/refs/{named_ref_id}', ref_data)
                remote_ref_updated = True
                workspace.progress('done', f'Pushed to {named_ref_id}')
            except Exception as exc:
                raise RuntimeError(f'Failed to update remote ref: {exc}') from exc
        else:
            workspace.progress('done', 'Remote ref already up to date')

        out = Schema__Push__State(
            vault_key             = input.vault_key,
            directory             = input.directory,
            force                 = input.force,
            sg_dir                = input.sg_dir,
            vault_id              = input.vault_id,
            branch_index_file_id  = input.branch_index_file_id,
            read_key_hex          = input.read_key_hex,
            write_key_hex         = input.write_key_hex,
            working_copy_clean    = input.working_copy_clean,
            clone_branch_id       = input.clone_branch_id,
            clone_ref_id          = input.clone_ref_id,
            named_ref_id          = input.named_ref_id,
            clone_commit_id       = input.clone_commit_id,
            named_commit_id       = input.named_commit_id,
            n_local_only_objects  = input.n_local_only_objects,
            remote_commit_id      = input.remote_commit_id,
            can_fast_forward      = input.can_fast_forward,
            n_objects_uploaded    = input.n_objects_uploaded,
            remote_ref_updated    = remote_ref_updated,
        )
        return out
