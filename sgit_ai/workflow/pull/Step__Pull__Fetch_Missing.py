"""Step 4 — Download missing commits, trees, and blobs from the remote server."""
from sgit_ai.safe_types.Enum__Fetch_Failure_Class        import Enum__Fetch_Failure_Class
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
        failures  = {}
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
                failures        = failures,
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
                        raise RuntimeError(self._build_missing_message(missing, failures))
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

    def _build_missing_message(self, missing: list, failures: dict) -> str:
        """Produce the honest user-facing message for a pull that didn't land all objects.

        Classification (per object) comes from ``failures`` — populated by
        ``Vault__Sync__Pull._fetch_missing_objects`` while attempting downloads.
        Any object that's still missing on disk but absent from ``failures`` is
        treated as transient (we have no positive signal it's truly absent on
        the server).

        Four cases:
          - all ABSENT      → "were not found on the server (... storage corruption or incomplete propagation)."
          - all FORBIDDEN   → "were refused by the server (HTTP 403 ... report to the vault operator)."
          - all TRANSIENT   → "failed to download (server may be under load — retry with: sgit pull)."
          - mixed           → per-category counts + per-category id lists + guidance.
        """
        absent_ids    = []
        forbidden_ids = []
        transient_ids = []
        for oid in missing:
            failure = failures.get(oid) or failures.get(f'bare/data/{oid}')
            cls     = failure.classification if failure is not None else None
            if cls == Enum__Fetch_Failure_Class.ABSENT:
                absent_ids.append(oid)
            elif cls == Enum__Fetch_Failure_Class.FORBIDDEN:
                forbidden_ids.append(oid)
            else:
                transient_ids.append(oid)

        n_absent    = len(absent_ids)
        n_forbidden = len(forbidden_ids)
        n_transient = len(transient_ids)
        n_total     = n_absent + n_forbidden + n_transient

        def _examples(ids):
            shown = sorted(ids)[:3]
            suffix = '...' if len(ids) > 3 else ''
            return ', '.join(shown) + suffix

        # Single-category messages (exact wording the diagnostics rely on)
        if n_absent and not n_forbidden and not n_transient:
            return (f'Pull incomplete: {n_absent} object(s) were not found on the server '
                    f'(the server reports them as absent — this may indicate server-side '
                    f'storage corruption or incomplete propagation).\n'
                    f'  Missing: {_examples(absent_ids)}')

        if n_forbidden and not n_absent and not n_transient:
            return (f'Pull incomplete: {n_forbidden} object(s) were refused by the server '
                    f'(HTTP 403 Forbidden — the server is denying access to these objects, '
                    f'usually because they are missing from backing storage or there is a '
                    f'server-side cache/permission issue. Retrying will not help — report to '
                    f'the vault operator).\n'
                    f'  Forbidden: {_examples(forbidden_ids)}')

        if n_transient and not n_absent and not n_forbidden:
            return (f'Pull incomplete: {n_transient} object(s) failed to download from the server '
                    f'(server may be under load — retry with: sgit pull).\n'
                    f'  Missing: {_examples(transient_ids)}')

        # Mixed — report each present category, with both per-category lists and guidance.
        parts  = []
        detail = []
        if n_absent:
            parts.append(f'{n_absent} absent on server')
            detail.append(f'  Absent:    {_examples(absent_ids)}')
        if n_forbidden:
            parts.append(f'{n_forbidden} forbidden (HTTP 403)')
            detail.append(f'  Forbidden: {_examples(forbidden_ids)}')
        if n_transient:
            parts.append(f'{n_transient} transient error')
            detail.append(f'  Transient: {_examples(transient_ids)}')
        summary = ', '.join(parts)
        return (f'Pull incomplete: {n_total} object(s) failed to download ({summary} — '
                f'retry may clear transient errors; absent/forbidden objects indicate a '
                f'server-side problem, report to the vault operator).\n' + '\n'.join(detail))
