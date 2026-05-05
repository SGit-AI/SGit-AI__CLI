"""Step 4 — Download missing commits, trees, and blobs from the remote server."""
from sgit_ai.safe_types.Safe_Str__Step_Name              import Safe_Str__Step_Name
from sgit_ai.safe_types.Safe_UInt__File_Count            import Safe_UInt__File_Count
from sgit_ai.schemas.workflow.pull.Schema__Pull__State   import Schema__Pull__State
from sgit_ai.workflow.Step                               import Step


class Step__Pull__Fetch_Missing(Step):
    name          = Safe_Str__Step_Name('fetch-missing')
    input_schema  = Schema__Pull__State
    output_schema = Schema__Pull__State

    def execute(self, input: Schema__Pull__State, workspace) -> Schema__Pull__State:
        sg_dir          = str(input.sg_dir)
        read_key        = bytes.fromhex(str(input.read_key_hex))
        vault_id        = str(input.vault_id)
        named_commit_id = str(input.named_commit_id) if input.named_commit_id else ''
        clone_commit_id = str(input.clone_commit_id) if input.clone_commit_id else ''

        workspace.ensure_managers(sg_dir)

        from sgit_ai.storage.Vault__Storage import Vault__Storage
        storage = Vault__Storage()
        directory = str(input.directory)
        try:
            local_config = workspace.sync_client._read_local_config(directory, storage)
            is_sparse = bool(getattr(local_config, 'sparse', False)) if local_config else False
        except Exception:
            is_sparse = False

        n_fetched = 0
        if named_commit_id and named_commit_id != clone_commit_id:
            workspace.progress('step', 'Fetching missing objects from server')
            fetch_stats = workspace.sync_client._fetch_missing_objects(
                vault_id        = vault_id,
                commit_id       = named_commit_id,
                obj_store       = workspace.obj_store,
                read_key        = read_key,
                sg_dir          = sg_dir,
                _p              = workspace.on_progress or (lambda *a, **k: None),
                stop_at         = clone_commit_id or None,
                include_blobs   = not is_sparse,
            )
            if isinstance(fetch_stats, dict):
                n_fetched = (fetch_stats.get('n_commits', 0) +
                             fetch_stats.get('n_trees',   0) +
                             fetch_stats.get('n_blobs',   0))

            if not is_sparse:
                find_missing = getattr(workspace.sync_client, '_find_missing_blobs', None)
                if find_missing:
                    missing = find_missing(named_commit_id, workspace.obj_store, read_key)
                    if missing:
                        n        = len(missing)
                        examples = ', '.join(sorted(missing)[:3])
                        raise RuntimeError(
                            f'Pull incomplete: {n} object(s) failed to download from the server '
                            f'(server may be under load — retry with: sgit pull).\n'
                            f'  Missing: {examples}{"..." if n > 3 else ""}')
        else:
            workspace.progress('step', 'No missing objects to fetch')

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
            clone_public_key_id   = input.clone_public_key_id,
            clone_branch_name     = input.clone_branch_name,
            named_branch_name     = input.named_branch_name,
            named_commit_id       = input.named_commit_id,
            remote_reachable      = input.remote_reachable,
            n_objects_fetched     = Safe_UInt__File_Count(n_fetched),
        )
        return out
