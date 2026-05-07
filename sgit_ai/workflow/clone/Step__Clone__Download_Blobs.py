"""Step 7 — Download all blob files collected during the tree walk (skipped in sparse mode)."""
from sgit_ai.safe_types.Safe_Str__Step_Name               import Safe_Str__Step_Name
from sgit_ai.schemas.workflow.clone.Schema__Clone__State  import Schema__Clone__State
from sgit_ai.workflow.Step                                import Step


class Step__Clone__Download_Blobs(Step):
    name          = Safe_Str__Step_Name('download-blobs')
    input_schema  = Schema__Clone__State
    output_schema = Schema__Clone__State

    def execute(self, input: Schema__Clone__State, workspace) -> Schema__Clone__State:
        sg_dir         = str(input.sg_dir)
        all_blob_ids   = [str(b) for b in (input.all_blob_ids   or [])]
        large_blob_ids = [str(b) for b in (input.large_blob_ids or [])]

        workspace.ensure_managers(sg_dir)

        n_blobs    = 0
        t_blobs_ms = 0

        if (all_blob_ids or large_blob_ids) and not input.sparse:
            vault_id = str(input.vault_id)
            read_key = bytes.fromhex(str(input.read_key_hex))
            blob_stats = workspace.sync_client._download_blobs_by_id(
                vault_id, all_blob_ids, large_blob_ids,
                lambda fid, data: workspace.save_file(sg_dir, fid, data),
                workspace.progress,
            )
            n_blobs    = blob_stats.get('n_blobs', 0)
            t_blobs_ms = int(blob_stats.get('t_blobs', 0.0) * 1000)

        data               = input.json()
        data['n_blobs']    = n_blobs
        data['t_blobs_ms'] = t_blobs_ms
        return Schema__Clone__State.from_json(data)
