"""Step 4 — Download all refs and public keys for all known branches."""
from sgit_ai.safe_types.Safe_Str__Step_Name               import Safe_Str__Step_Name
from sgit_ai.schemas.workflow.clone.Schema__Clone__State  import Schema__Clone__State
from sgit_ai.workflow.Step                                import Step


class Step__Clone__Download_Branch_Meta(Step):
    name          = Safe_Str__Step_Name('download-branch-meta')
    input_schema  = Schema__Clone__State
    output_schema = Schema__Clone__State

    def execute(self, input: Schema__Clone__State, workspace) -> Schema__Clone__State:
        vault_id  = str(input.vault_id)
        index_id  = str(input.branch_index_file_id)
        sg_dir    = str(input.sg_dir)
        read_key  = bytes.fromhex(str(input.read_key_hex))
        directory = str(input.directory)

        workspace.ensure_managers(sg_dir)
        workspace.progress('step', 'Downloading branch metadata')

        branch_index   = workspace.branch_manager.load_branch_index(directory, index_id, read_key)
        structural_fids = []
        for branch in branch_index.branches:
            if branch.head_ref_id:
                structural_fids.append(f'bare/refs/{str(branch.head_ref_id)}')
            if branch.public_key_id:
                structural_fids.append(f'bare/keys/{str(branch.public_key_id)}')
        if structural_fids:
            for fid, blob in workspace.sync_client.api.batch_read(vault_id, structural_fids).items():
                if blob:
                    workspace.save_file(sg_dir, fid, blob)

        named_ref_id    = str(input.named_ref_id)
        named_commit_id = workspace.ref_manager.read_ref(named_ref_id, read_key) or ''

        data                    = input.json()
        data['named_commit_id'] = named_commit_id
        return Schema__Clone__State.from_json(data)
