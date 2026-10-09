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

    def _enforce_signature_policy(self, workspace, input, read_key: bytes, named_commit_id: str, clone_commit_id: str) -> None:
        """With feature 'signatures-required' on the vault, every incoming commit (the
        remote head down to what this clone already has) must verify; the first one
        that does not stops the pull by name, before anything is merged."""
        if not named_commit_id or named_commit_id == clone_commit_id:
            return
        from sgit_ai.storage.Vault__Format                    import Vault__Format, FEATURE_SIG_REQUIRED
        from sgit_ai.core.actions.verify.Vault__Signatures    import Vault__Signatures
        from sgit_ai.core.Vault__Errors                       import Vault__Signature_Error
        from sgit_ai.storage.Vault__Scope                     import Vault__Scope
        from sgit_ai.core.actions.status.Vault__Sync__Status  import Vault__Sync__Status
        sync      = workspace.sync_client
        directory = str(input.directory)
        import os
        index_id = str(input.branch_index_file_id) if input.branch_index_file_id else ''
        if not index_id or not os.path.isfile(workspace.storage.index_path(directory, index_id)):
            return                                                         # no index (single-branch vault): no policy
        index = workspace.branch_manager.load_branch_index(directory, index_id, read_key)   # present but unreadable: fail
        if not Vault__Format().has_feature(index, FEATURE_SIG_REQUIRED):   # closed, never skip the policy (TM-R25)
            try:                                                           # policy off: forget its start, so switching
                os.remove(os.path.join(str(input.sg_dir), 'local', 'signature_policy.json'))   # it on again starts afresh
            except OSError:
                pass
            return
        c      = sync._init_components(directory)
        stop   = self._local_history(c, read_key, clone_commit_id)          # what this clone already holds is not incoming
        if named_commit_id in stop:
            return                                                         # the remote is behind or equal: nothing incoming
        stop  |= self._policy_start(c, index)                               # commits from before the policy was switched on
        bounds = set()
        try:
            bounds = set(Vault__Scope().from_local_config(sync._read_local_config(directory, c.storage)).boundary_ids())
        except Exception:
            pass
        Vault__Sync__Status(crypto=sync.crypto, api=sync.api)._fetch_commit_chain(      # the incoming commits, if absent
            c, workspace.obj_store, read_key, named_commit_id, limit=10000, known=stop | bounds, boundaries=bounds)
        from sgit_ai.core.actions.verify.Vault__Key_Fetch     import Vault__Key_Fetch
        key_fetch = Vault__Key_Fetch(crypto=sync.crypto, api=sync.api)        # a teammate's key this clone has not seen yet
        report = Vault__Signatures(crypto=sync.crypto, key_fetch=key_fetch).verify_chain(
            c, read_key, named_commit_id, stop_at=stop, index=index, boundaries=bounds)
        if report['first_failure']:
            cid, status = report['first_failure']
            raise Vault__Signature_Error(
                f'this vault requires signed commits and incoming commit {cid} is {status}; '
                f'the pull was refused before anything was merged. Ask the vault owner; if the owner '
                f'relaxes the policy (`sgit vault format --remove-feature signatures-required`), '
                f'pull again.')

    def _local_history(self, c, read_key: bytes, clone_commit_id: str) -> set:
        """Every commit reachable from this clone's head that is in its store (all
        parents). Only those are 'already held'; stopping at the head alone made a
        remote head that is an ancestor, or a divergent merge base, count as incoming
        and dragged pre-policy history into the check."""
        from sgit_ai.crypto.PKI__Crypto    import PKI__Crypto
        from sgit_ai.storage.Vault__Commit import Vault__Commit
        vc    = Vault__Commit(crypto=c.obj_store.crypto, pki=PKI__Crypto(), object_store=c.obj_store, ref_manager=c.ref_manager)
        seen  = set()
        queue = [clone_commit_id] if clone_commit_id else []
        while queue:
            cid = queue.pop()
            if not cid or cid in seen or not c.obj_store.exists(cid):
                continue
            seen.add(cid)
            try:
                queue.extend(str(p) for p in (vc.load_commit(cid, read_key).parents or []) if str(p))
            except Exception:
                continue
        return seen

    def _policy_start(self, c, index) -> set:
        """The commit recorded when `signatures-required` was switched on (and so
        everything before it), if this clone holds it."""
        import os
        from sgit_ai.storage.Vault__Format import Vault__Format
        anchor = self._pinned_anchor(c, Vault__Format().sig_anchor_of(index))
        if not anchor:
            return set()
        try:
            return {n for n in os.listdir(os.path.join(str(c.sg_dir), 'bare', 'data')) if n.startswith('obj-cas-imm-' + anchor)}
        except OSError:
            return set()

    def _pinned_anchor(self, c, anchor: str) -> str:
        """The first policy start this clone saw stays: a later index that moves it
        forward (exempting commits) is ignored. Called only while the policy is on;
        _enforce_signature_policy clears the pin when the policy is switched off."""
        import json, os
        path = os.path.join(str(c.sg_dir), 'local', 'signature_policy.json')
        try:
            with open(path) as f:
                pinned = json.load(f).get('signed_since', '')
        except Exception:
            pinned = ''
        if pinned:
            return pinned
        if anchor:
            try:
                with open(path, 'w') as f:
                    json.dump({'signed_since': anchor}, f)
            except OSError:
                pass
        return anchor

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
        from sgit_ai.core.scope.Vault__Scope import Vault__Scope
        scope = Vault__Scope()
        try:
            local_config = workspace.sync_client._read_local_config(directory, storage)
            is_sparse = bool(getattr(local_config, 'sparse', False)) if local_config else False
            scope     = Vault__Scope().from_local_config(local_config)
        except Exception:
            is_sparse = False

        n_fetched = 0
        failures  = {}
        self._enforce_signature_policy(workspace, input, read_key, named_commit_id, clone_commit_id)
        if named_commit_id and input.remote_reachable and input.named_ref_id and input.clone_ref_id:   # writable pull: the head
            try:                                                                                   # passed every check: accept it
                workspace.sync_client._write_remote_baseline(directory, workspace.storage, str(input.named_ref_id), named_commit_id)
            except Exception:
                pass
        if named_commit_id and named_commit_id != clone_commit_id:
            workspace.progress('step', 'Fetching missing objects from server')
            fetch_kwargs = dict(
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
            if scope.is_partial():
                fetch_kwargs['scope'] = scope                # a full clone's call is unchanged
            fetch_stats = workspace.sync_client._fetch_missing_objects(**fetch_kwargs)
            if isinstance(fetch_stats, dict):
                n_fetched = (fetch_stats.get('n_commits', 0) +
                             fetch_stats.get('n_trees',   0) +
                             fetch_stats.get('n_blobs',   0))

            if not is_sparse:
                find_missing = getattr(workspace.sync_client, '_find_missing_blobs', None)
                if find_missing:
                    missing = (find_missing(named_commit_id, workspace.obj_store, read_key, scope=scope)
                               if scope.is_scoped() else
                               find_missing(named_commit_id, workspace.obj_store, read_key))
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
