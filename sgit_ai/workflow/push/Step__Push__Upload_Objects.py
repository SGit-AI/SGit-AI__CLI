"""Step 5 — Upload local-only objects to the server via batch API."""
from sgit_ai.safe_types.Safe_Str__Step_Name              import Safe_Str__Step_Name
from sgit_ai.safe_types.Safe_UInt__File_Count            import Safe_UInt__File_Count
from sgit_ai.schemas.workflow.push.Schema__Push__State   import Schema__Push__State
from sgit_ai.workflow.Step                               import Step


class Step__Push__Upload_Objects(Step):
    name          = Safe_Str__Step_Name('upload-objects')
    input_schema  = Schema__Push__State
    output_schema = Schema__Push__State

    def execute(self, input: Schema__Push__State, workspace) -> Schema__Push__State:
        sg_dir           = str(input.sg_dir)
        vault_id         = str(input.vault_id)
        read_key         = bytes.fromhex(str(input.read_key_hex))
        clone_commit_id  = str(input.clone_commit_id) if input.clone_commit_id else ''
        remote_commit_id = str(input.remote_commit_id) if input.remote_commit_id else ''
        write_key_hex    = str(input.write_key_hex) if input.write_key_hex else ''

        workspace.ensure_managers(sg_dir)
        workspace.progress('step', 'Uploading objects to server')

        n_uploaded = 0
        if clone_commit_id and clone_commit_id != remote_commit_id:
            from sgit_ai.core.actions.push.Vault__Batch import Vault__Batch
            batch = Vault__Batch(crypto=workspace.sync_client.crypto,
                                 api=workspace.sync_client.api)
            try:
                named_commit_id = str(input.named_commit_id) if input.named_commit_id else ''
                ops, _ = batch.build_push_operations(
                    obj_store        = workspace.obj_store,
                    read_key         = read_key,
                    clone_branch_id  = str(input.clone_branch_id),
                    clone_commit_id  = clone_commit_id,
                    named_commit_id  = named_commit_id,
                )
                if ops:
                    result     = batch.execute_batch(vault_id, write_key_hex, ops)
                    n_uploaded = result.get('n_uploaded', len(ops))
            except Exception as exc:
                raise RuntimeError(f'Upload failed: {exc}') from exc

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
            n_objects_uploaded    = Safe_UInt__File_Count(n_uploaded),
        )
        return out
