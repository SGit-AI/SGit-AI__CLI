"""Step 7 — Download blob files (skipped in sparse mode)."""
from sgit_ai.safe_types.Safe_Str__Step_Name               import Safe_Str__Step_Name
from sgit_ai.schemas.workflow.clone.Schema__Clone__State  import Schema__Clone__State
from sgit_ai.workflow.Step                                import Step


class Step__Clone__Download_Blobs(Step):
    name          = Safe_Str__Step_Name('download-blobs')
    input_schema  = Schema__Clone__State
    output_schema = Schema__Clone__State

    def execute(self, input: Schema__Clone__State, workspace) -> Schema__Clone__State:
        sg_dir          = str(input.sg_dir)
        named_commit_id = str(input.named_commit_id) if input.named_commit_id else ''

        workspace.ensure_managers(sg_dir)

        n_blobs    = 0
        t_blobs_ms = 0

        if named_commit_id and not input.sparse:
            vault_id = str(input.vault_id)
            read_key = bytes.fromhex(str(input.read_key_hex))
            blob_stats = workspace.sync_client._clone_download_blobs(
                vault_id, workspace.vc, workspace.sub_tree, named_commit_id,
                read_key, lambda fid, data: workspace.save_file(sg_dir, fid, data),
                workspace.progress,
            )
            n_blobs    = blob_stats.get('n_blobs', 0)
            t_blobs_ms = int(blob_stats.get('t_blobs', 0.0) * 1000)

        data               = input.json()
        data['n_blobs']    = n_blobs
        data['t_blobs_ms'] = t_blobs_ms
        return Schema__Clone__State.from_json(data)
