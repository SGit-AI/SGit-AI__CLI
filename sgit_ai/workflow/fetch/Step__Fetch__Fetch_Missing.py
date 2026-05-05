"""Step 4 — Download missing commits, trees, and blobs from the remote server."""
from sgit_ai.safe_types.Safe_Str__Step_Name               import Safe_Str__Step_Name
from sgit_ai.safe_types.Safe_UInt__File_Count             import Safe_UInt__File_Count
from sgit_ai.schemas.workflow.fetch.Schema__Fetch__State  import Schema__Fetch__State
from sgit_ai.workflow.Step                                import Step


class Step__Fetch__Fetch_Missing(Step):
    name          = Safe_Str__Step_Name('fetch-missing')
    input_schema  = Schema__Fetch__State
    output_schema = Schema__Fetch__State

    def execute(self, input: Schema__Fetch__State, workspace) -> Schema__Fetch__State:
        sg_dir          = str(input.sg_dir)
        read_key        = bytes.fromhex(str(input.read_key_hex))
        vault_id        = str(input.vault_id)
        named_commit_id = str(input.named_commit_id) if input.named_commit_id else ''
        clone_commit_id = str(input.clone_commit_id) if input.clone_commit_id else ''

        workspace.ensure_managers(sg_dir)

        n_fetched = 0
        if named_commit_id and named_commit_id != clone_commit_id:
            workspace.progress('step', 'Fetching missing objects from server')
            fetch_stats = workspace.sync_client._fetch_missing_objects(
                vault_id      = vault_id,
                commit_id     = named_commit_id,
                obj_store     = workspace.obj_store,
                read_key      = read_key,
                sg_dir        = sg_dir,
                _p            = workspace.on_progress or (lambda *a, **k: None),
                stop_at       = clone_commit_id or None,
                include_blobs = True,
            )
            n_fetched = fetch_stats.get('n_fetched', 0) if isinstance(fetch_stats, dict) else 0
        else:
            workspace.progress('step', 'Already up to date')

        return Schema__Fetch__State(
            vault_key             = input.vault_key,
            directory             = input.directory,
            sg_dir                = input.sg_dir,
            vault_id              = input.vault_id,
            branch_index_file_id  = input.branch_index_file_id,
            read_key_hex          = input.read_key_hex,
            clone_commit_id       = input.clone_commit_id,
            named_ref_id          = input.named_ref_id,
            named_commit_id       = input.named_commit_id,
            remote_reachable      = input.remote_reachable,
            n_objects_fetched     = Safe_UInt__File_Count(n_fetched),
        )
