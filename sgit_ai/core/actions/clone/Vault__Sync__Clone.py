"""Vault__Sync__Clone — clone operations (Brief 22 — E5-6)."""
import time
from   urllib.request                import urlopen
from   sgit_ai.core.Vault__Sync__Base import Vault__Sync__Base


class Vault__Sync__Clone(Vault__Sync__Base):

    def clone(self, vault_key: str, directory: str, on_progress: callable = None, sparse: bool = False) -> dict:
        """Clone a vault from the remote server into a local directory."""
        return self._clone_with_keys(vault_key, directory, on_progress, sparse=sparse)

    def _warn_integrity_fallbacks(self, ws, on_progress) -> None:
        """A1: after a clone, if any object was accepted by the content-address
        FALLBACK (bytes did not hash to the id but decrypt under the key),
        surface it once. Expected only for a vault re-keyed by `sgit vault
        move`; on any other vault it signals a host serving substituted
        objects — the substitution class decision 16 exists for."""
        rescued = list(getattr(ws, 'integrity_authenticated', []) or [])
        if not rescued:
            return
        _p = on_progress or (lambda *a, **k: None)
        _p('warning', f'{len(rescued)} object(s) did not match their content address',
           'accepted because they authenticate under your key — expected ONLY for a vault '
           'that has been moved (sgit vault move). On any other vault this means the host '
           'served substituted objects; verify the source before trusting this clone.')

    def _clone_with_keys(self, vault_key: str, directory: str, on_progress: callable = None, sparse: bool = False) -> dict:
        """Internal clone implementation — delegates to Workflow__Clone (10-step pipeline)."""
        import tempfile
        from sgit_ai.safe_types.Safe_Str__File_Path                      import Safe_Str__File_Path
        from sgit_ai.safe_types.Safe_Str__Vault_Key                      import Safe_Str__Vault_Key
        from sgit_ai.schemas.workflow.clone.Schema__Clone__State         import Schema__Clone__State
        from sgit_ai.workflow.Workflow__Runner                           import Workflow__Runner
        from sgit_ai.workflow.clone.Clone__Workspace                     import Clone__Workspace
        from sgit_ai.workflow.clone.Workflow__Clone                      import Workflow__Clone

        wf  = Workflow__Clone()
        tmp = tempfile.mkdtemp(prefix='sgit-clone-')
        ws  = Clone__Workspace.create(wf.workflow_name(), tmp)
        ws.sync_client  = self
        ws.on_progress  = on_progress or (lambda *a, **k: None)

        initial_state = Schema__Clone__State(
            vault_key = Safe_Str__Vault_Key(vault_key),
            directory = Safe_Str__File_Path(directory),
            sparse    = sparse,
        )

        runner    = Workflow__Runner(workflow=wf, workspace=ws, keep_work=False)
        final_out = runner.run(input=initial_state)
        self._warn_integrity_fallbacks(ws, on_progress)

        n_commits    = final_out.get('n_commits')    or 0
        n_blobs      = final_out.get('n_blobs')      or 0
        t_commits_ms = final_out.get('t_commits_ms') or 0
        t_trees_ms   = final_out.get('t_trees_ms')   or 0
        t_blobs_ms   = final_out.get('t_blobs_ms')   or 0
        t_checkout_ms = final_out.get('t_checkout_ms') or 0
        _p = on_progress or (lambda *a, **k: None)
        if n_commits or n_blobs:
            parts = [f'commits {t_commits_ms/1000:.1f}s', f'trees {t_trees_ms/1000:.1f}s',
                     f'blobs {t_blobs_ms/1000:.1f}s', f'checkout {t_checkout_ms/1000:.1f}s']
            parts.append(f'({n_commits} commits, {n_blobs} blobs)')
            _p('stats', '  '.join(parts))

        return dict(
            directory    = directory,
            vault_key    = vault_key,
            vault_id     = final_out.get('vault_id', ''),
            branch_id    = final_out.get('clone_branch_id', ''),
            named_branch = final_out.get('named_branch_id', ''),
            commit_id    = final_out.get('named_commit_id') or '',
            sparse       = sparse,
        )

    def clone_read_only(self, vault_id: str, read_key_hex: str, directory: str,
                        on_progress: callable = None, sparse: bool = False) -> dict:
        """Clone a vault in read-only mode — delegates to Workflow__Clone__ReadOnly."""
        import tempfile
        from sgit_ai.safe_types.Safe_Str__File_Path                          import Safe_Str__File_Path
        from sgit_ai.safe_types.Safe_Str__Vault_Id                           import Safe_Str__Vault_Id
        from sgit_ai.safe_types.Safe_Str__Read_Key                           import Safe_Str__Read_Key
        from sgit_ai.schemas.workflow.clone.Schema__Clone__State             import Schema__Clone__State
        from sgit_ai.workflow.Workflow__Runner                               import Workflow__Runner
        from sgit_ai.workflow.clone.Clone__Workspace                         import Clone__Workspace
        from sgit_ai.workflow.clone.Workflow__Clone__ReadOnly                import Workflow__Clone__ReadOnly

        wf  = Workflow__Clone__ReadOnly()
        tmp = tempfile.mkdtemp(prefix='sgit-clone-ro-')
        ws  = Clone__Workspace.create(wf.workflow_name(), tmp)
        ws.sync_client = self
        ws.on_progress = on_progress or (lambda *a, **k: None)

        initial_state = Schema__Clone__State(
            vault_id     = Safe_Str__Vault_Id(vault_id),
            read_key_hex = Safe_Str__Read_Key(read_key_hex),
            directory    = Safe_Str__File_Path(directory),
            sparse       = sparse,
        )

        runner    = Workflow__Runner(workflow=wf, workspace=ws, keep_work=False)
        final_out = runner.run(input=initial_state)
        self._warn_integrity_fallbacks(ws, on_progress)

        return dict(
            vault_id   = final_out.get('vault_id',         vault_id),
            directory  = directory,
            file_count = final_out.get('n_blobs',          0),
            commit_id  = final_out.get('named_commit_id',  '') or '',
            sparse     = sparse,
            mode       = 'read-only',
        )

    def clone_branch(self, vault_key: str, directory: str,
                     on_progress: callable = None, bare: bool = False) -> dict:
        """Thin clone: download full commit history but only HEAD trees/blobs."""
        import tempfile
        from sgit_ai.safe_types.Safe_Str__File_Path                      import Safe_Str__File_Path
        from sgit_ai.safe_types.Safe_Str__Vault_Key                      import Safe_Str__Vault_Key
        from sgit_ai.schemas.workflow.clone.Schema__Clone__State         import Schema__Clone__State
        from sgit_ai.workflow.Workflow__Runner                           import Workflow__Runner
        from sgit_ai.workflow.clone.Clone__Workspace                     import Clone__Workspace
        from sgit_ai.workflow.clone.Workflow__Clone__Branch              import Workflow__Clone__Branch

        wf  = Workflow__Clone__Branch()
        tmp = tempfile.mkdtemp(prefix='sgit-clone-branch-')
        ws  = Clone__Workspace.create(wf.workflow_name(), tmp)
        ws.sync_client = self
        ws.on_progress = on_progress or (lambda *a, **k: None)

        initial_state = Schema__Clone__State(
            vault_key = Safe_Str__Vault_Key(vault_key),
            directory = Safe_Str__File_Path(directory),
            bare      = bare,
        )

        runner    = Workflow__Runner(workflow=wf, workspace=ws, keep_work=False)
        final_out = runner.run(input=initial_state)
        self._warn_integrity_fallbacks(ws, on_progress)

        return dict(
            directory    = directory,
            vault_key    = vault_key,
            vault_id     = final_out.get('vault_id', ''),
            branch_id    = final_out.get('clone_branch_id', ''),
            named_branch = final_out.get('named_branch_id', ''),
            commit_id    = final_out.get('named_commit_id') or '',
            mode         = 'clone-branch',
            bare         = bare,
        )

    def clone_headless(self, vault_key: str, directory: str,
                       on_progress: callable = None) -> dict:
        """Credentials-only clone: derive keys and write config; no data downloaded."""
        import tempfile
        from sgit_ai.safe_types.Safe_Str__File_Path                      import Safe_Str__File_Path
        from sgit_ai.safe_types.Safe_Str__Vault_Key                      import Safe_Str__Vault_Key
        from sgit_ai.schemas.workflow.clone.Schema__Clone__State         import Schema__Clone__State
        from sgit_ai.workflow.Workflow__Runner                           import Workflow__Runner
        from sgit_ai.workflow.clone.Clone__Workspace                     import Clone__Workspace
        from sgit_ai.workflow.clone.Workflow__Clone__Headless            import Workflow__Clone__Headless

        wf  = Workflow__Clone__Headless()
        tmp = tempfile.mkdtemp(prefix='sgit-clone-headless-')
        ws  = Clone__Workspace.create(wf.workflow_name(), tmp)
        ws.sync_client = self
        ws.on_progress = on_progress or (lambda *a, **k: None)

        initial_state = Schema__Clone__State(
            vault_key = Safe_Str__Vault_Key(vault_key),
            directory = Safe_Str__File_Path(directory),
        )

        runner    = Workflow__Runner(workflow=wf, workspace=ws, keep_work=False)
        final_out = runner.run(input=initial_state)
        self._warn_integrity_fallbacks(ws, on_progress)

        return dict(
            directory = directory,
            vault_key = vault_key,
            vault_id  = final_out.get('vault_id', ''),
            mode      = 'headless',
        )

    def clone_range(self, vault_key: str, directory: str, range_from: str = '',
                    range_to: str = '', on_progress: callable = None,
                    bare: bool = False) -> dict:
        """Clone commits/trees/blobs in the range range_from..range_to (range_from exclusive)."""
        import tempfile
        from sgit_ai.safe_types.Safe_Str__File_Path                      import Safe_Str__File_Path
        from sgit_ai.safe_types.Safe_Str__Vault_Key                      import Safe_Str__Vault_Key
        from sgit_ai.safe_types.Safe_Str__Commit_Id                      import Safe_Str__Commit_Id
        from sgit_ai.schemas.workflow.clone.Schema__Clone__State         import Schema__Clone__State
        from sgit_ai.workflow.Workflow__Runner                           import Workflow__Runner
        from sgit_ai.workflow.clone.Clone__Workspace                     import Clone__Workspace
        from sgit_ai.workflow.clone.Workflow__Clone__Range               import Workflow__Clone__Range

        wf  = Workflow__Clone__Range()
        tmp = tempfile.mkdtemp(prefix='sgit-clone-range-')
        ws  = Clone__Workspace.create(wf.workflow_name(), tmp)
        ws.sync_client = self
        ws.on_progress = on_progress or (lambda *a, **k: None)

        initial_state = Schema__Clone__State(
            vault_key  = Safe_Str__Vault_Key(vault_key),
            directory  = Safe_Str__File_Path(directory),
            range_from = Safe_Str__Commit_Id(range_from) if range_from else None,
            range_to   = Safe_Str__Commit_Id(range_to)   if range_to   else None,
            bare       = bare,
        )

        runner    = Workflow__Runner(workflow=wf, workspace=ws, keep_work=False)
        final_out = runner.run(input=initial_state)
        self._warn_integrity_fallbacks(ws, on_progress)

        return dict(
            directory    = directory,
            vault_key    = vault_key,
            vault_id     = final_out.get('vault_id', ''),
            branch_id    = final_out.get('clone_branch_id', ''),
            commit_id    = final_out.get('named_commit_id') or '',
            mode         = 'clone-range',
            bare         = bare,
            range_from   = range_from,
            range_to     = range_to,
        )

    def _download_blobs_by_id(self, vault_id: str, small_blob_ids: list,
                               large_blob_ids: list, save_file, _p) -> dict:
        small_blobs = [f'bare/data/{bid}' for bid in small_blob_ids]
        large_blobs = [f'bare/data/{bid}' for bid in large_blob_ids]

        total_blobs = len(small_blobs) + len(large_blobs)
        _t0 = time.monotonic()

        if not total_blobs:
            return {'n_blobs': 0, 't_blobs': 0.0}

        _p('download', 'Downloading blobs', f'0/{total_blobs}')
        done = 0

        # Count-based chunking (avoids needing decrypted sizes)
        BLOBS_PER_CHUNK = 50
        chunks = [small_blobs[i:i + BLOBS_PER_CHUNK]
                  for i in range(0, len(small_blobs), BLOBS_PER_CHUNK)]

        def fetch_small_chunk(chunk):
            nonlocal done
            for fid, data in self.api.batch_read(vault_id, chunk).items():
                if data:
                    save_file(fid, data)
            done += len(chunk)
            _p('download', 'Downloading blobs', f'{done}/{total_blobs}')

        if len(chunks) > 1:
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=min(len(chunks), 8)) as executor:
                for fut in [executor.submit(fetch_small_chunk, c) for c in chunks]:
                    fut.result()
        elif chunks:
            fetch_small_chunk(chunks[0])

        if large_blobs:
            debug_log = getattr(self.api, 'debug_log', None)

            def download_large_blob(fid):
                nonlocal done
                url_info = self.api.presigned_read_url(vault_id, fid)
                s3_url   = url_info.get('url') or url_info.get('presigned_url', '')
                entry    = debug_log.log_request('GET', s3_url) if debug_log else None
                with urlopen(s3_url) as resp:
                    data = resp.read()
                    if entry:
                        debug_log.log_response(entry, resp.status, len(data))
                save_file(fid, data)
                done += 1
                _p('download', 'Downloading blobs', f'{done}/{total_blobs}')

            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=min(len(large_blobs), 4)) as executor:
                for fut in [executor.submit(download_large_blob, fid) for fid in large_blobs]:
                    fut.result()

        return {'n_blobs': total_blobs, 't_blobs': time.monotonic() - _t0}

    def _clone_download_blobs(self, vault_id: str, vc, sub_tree,
                              named_commit_id: str, read_key: bytes,
                              save_file, _p) -> dict:
        """Download blobs for HEAD only (legacy path — only used by clone-branch thin mode).

        Returns {'n_blobs': int, 't_blobs': float}.
        """
        commit_obj   = vc.load_commit(named_commit_id, read_key)
        flat_entries = sub_tree.flatten(str(commit_obj.tree_id), read_key)

        CLONE_LAMBDA_SAFE_BYTES = 2 * 1024 * 1024
        small_blobs = []
        large_blobs = []
        for entry_data in flat_entries.values():
            blob_id = entry_data.get('blob_id', '')
            if not blob_id:
                continue
            fid  = f'bare/data/{blob_id}'
            size = entry_data.get('size', 0)
            if entry_data.get('large') or size > CLONE_LAMBDA_SAFE_BYTES:
                large_blobs.append(fid)
            else:
                small_blobs.append((fid, size))

        total_blobs = len(small_blobs) + len(large_blobs)
        _t0 = time.monotonic()

        if not total_blobs:
            return {'n_blobs': 0, 't_blobs': 0.0}

        _p('download', 'Downloading blobs', f'0/{total_blobs}')
        done = 0

        MAX_RESPONSE_BYTES = 3 * 1024 * 1024
        chunks       = []
        cur_chunk    = []
        cur_chunk_sz = 0
        for fid, size in small_blobs:
            est_b64 = (size * 4 // 3) + 64
            if cur_chunk and cur_chunk_sz + est_b64 > MAX_RESPONSE_BYTES:
                chunks.append(cur_chunk)
                cur_chunk    = []
                cur_chunk_sz = 0
            cur_chunk.append(fid)
            cur_chunk_sz += est_b64
        if cur_chunk:
            chunks.append(cur_chunk)

        def fetch_small_chunk(chunk):
            nonlocal done
            for fid, data in self.api.batch_read(vault_id, chunk).items():
                if data:
                    save_file(fid, data)
            done += len(chunk)
            _p('download', 'Downloading blobs', f'{done}/{total_blobs}')

        if len(chunks) > 1:
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=len(chunks)) as executor:
                for fut in [executor.submit(fetch_small_chunk, c) for c in chunks]:
                    fut.result()
        elif chunks:
            fetch_small_chunk(chunks[0])

        if large_blobs:
            debug_log = getattr(self.api, 'debug_log', None)

            def download_large_blob(fid):
                nonlocal done
                url_info = self.api.presigned_read_url(vault_id, fid)
                s3_url   = url_info.get('url') or url_info.get('presigned_url', '')
                entry    = debug_log.log_request('GET', s3_url) if debug_log else None
                with urlopen(s3_url) as resp:
                    data = resp.read()
                    if entry:
                        debug_log.log_response(entry, resp.status, len(data))
                save_file(fid, data)
                done += 1
                _p('download', 'Downloading blobs', f'{done}/{total_blobs}')

            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=min(len(large_blobs), 4)) as executor:
                for fut in [executor.submit(download_large_blob, fid) for fid in large_blobs]:
                    fut.result()

        return {'n_blobs': total_blobs, 't_blobs': time.monotonic() - _t0}
