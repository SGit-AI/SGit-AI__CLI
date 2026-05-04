"""Step 3 — Download the branch index file."""
from sgit_ai.safe_types.Safe_Str__Step_Name               import Safe_Str__Step_Name
from sgit_ai.schemas.workflow.clone.Schema__Clone__State  import Schema__Clone__State
from sgit_ai.workflow.Step                                import Step


class Step__Clone__Download_Index(Step):
    name          = Safe_Str__Step_Name('download-index')
    input_schema  = Schema__Clone__State
    output_schema = Schema__Clone__State

    def execute(self, input: Schema__Clone__State, workspace) -> Schema__Clone__State:
        vault_id  = str(input.vault_id)
        index_id  = str(input.branch_index_file_id)
        sg_dir    = str(input.sg_dir)
        read_key  = bytes.fromhex(str(input.read_key_hex))
        directory = str(input.directory)

        workspace.ensure_managers(sg_dir)
        workspace.progress('step', 'Downloading vault index')

        index_fid = f'bare/indexes/{index_id}'
        idx_data  = workspace.sync_client.api.batch_read(vault_id, [index_fid])
        if not idx_data.get(index_fid):
            raise RuntimeError('No branch index found on remote — is this a valid vault?')
        workspace.save_file(sg_dir, index_fid, idx_data[index_fid])

        branch_index = workspace.branch_manager.load_branch_index(directory, index_id, read_key)
        named_meta   = workspace.branch_manager.get_branch_by_name(branch_index, 'current')
        if not named_meta:
            raise RuntimeError('Named branch "current" not found on remote')

        data                   = input.json()
        data['named_branch_id'] = str(named_meta.branch_id)
        data['named_ref_id']    = str(named_meta.head_ref_id)
        data['index_id']        = index_id
        return Schema__Clone__State.from_json(data)
