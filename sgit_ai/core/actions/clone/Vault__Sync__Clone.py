"""Vault__Sync__Clone — clone operations (Brief 22 — E5-6)."""
import json
import os
import time
from   urllib.request                            import urlopen
from   sgit_ai.crypto.PKI__Crypto            import PKI__Crypto
from   sgit_ai.crypto.Vault__Key_Manager     import Vault__Key_Manager
from   sgit_ai.storage.Vault__Commit         import Vault__Commit
from   sgit_ai.storage.Vault__Object_Store   import Vault__Object_Store
from   sgit_ai.storage.Vault__Ref_Manager    import Vault__Ref_Manager
from   sgit_ai.safe_types.Enum__Clone_Mode       import Enum__Clone_Mode
from   sgit_ai.safe_types.Enum__Local_Config_Mode import Enum__Local_Config_Mode
from   sgit_ai.schemas.Schema__Clone_Mode    import Schema__Clone_Mode
from   sgit_ai.schemas.Schema__Local_Config  import Schema__Local_Config
from   sgit_ai.storage.Vault__Branch_Manager    import Vault__Branch_Manager
from   sgit_ai.storage.Vault__Storage           import Vault__Storage
from   sgit_ai.storage.Vault__Sub_Tree          import Vault__Sub_Tree
from   sgit_ai.core.Vault__Sync__Base        import Vault__Sync__Base


class Vault__Sync__Clone(Vault__Sync__Base):

    def clone(self, vault_key: str, directory: str, on_progress: callable = None, sparse: bool = False) -> dict:
        """Clone a vault from the remote server into a local directory."""
        from sgit_ai.transfer.Simple_Token import Simple_Token
        if Simple_Token.is_simple_token(vault_key) or vault_key.startswith('vault://'):
            token_str = vault_key.removeprefix('vault://')
            return self._clone_resolve_simple_token(token_str, directory, on_progress, sparse=sparse)

        return self._clone_with_keys(vault_key, directory, on_progress, sparse=sparse)

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
        """Clone a vault in read-only mode using only the read key."""
        import json as _json
        if os.path.exists(directory):
            entries = os.listdir(directory)
            if entries:
                raise RuntimeError(f'Directory is not empty: {directory}')
        os.makedirs(directory, exist_ok=True)

        _p = on_progress or (lambda *a, **k: None)

        keys     = self.crypto.import_read_key(read_key_hex, vault_id)
        read_key = keys['read_key_bytes']

        _p('step', 'Deriving vault keys')

        storage = Vault__Storage()
        sg_dir  = storage.create_bare_structure(directory)

        def save_file(file_id, data):
            local_path = os.path.join(sg_dir, file_id)
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            with open(local_path, 'wb') as f:
                f.write(data)

        pki            = PKI__Crypto()
        key_manager    = Vault__Key_Manager(vault_path=sg_dir, crypto=self.crypto, pki=pki)
        ref_manager    = Vault__Ref_Manager(vault_path=sg_dir, crypto=self.crypto)
        obj_store      = Vault__Object_Store(vault_path=sg_dir, crypto=self.crypto)
        branch_manager = Vault__Branch_Manager(vault_path  = sg_dir,
                                               crypto      = self.crypto,
                                               key_manager = key_manager,
                                               ref_manager = ref_manager,
                                               storage     = storage)

        # Phase 1: Download branch index
        _p('step', 'Downloading vault index')
        index_id  = keys['branch_index_file_id']
        index_fid = f'bare/indexes/{index_id}'
        idx_data  = self.api.batch_read(vault_id, [index_fid])
        if not idx_data.get(index_fid):
            raise RuntimeError('No branch index found on remote — is this a valid vault?')
        save_file(index_fid, idx_data[index_fid])

        branch_index = branch_manager.load_branch_index(directory, index_id, read_key)
        named_meta   = branch_manager.get_branch_by_name(branch_index, 'current')
        if not named_meta:
            raise RuntimeError('Named branch "current" not found on remote')

        # Phase 2: Download refs + public keys
        _p('step', 'Downloading branch metadata')
        structural_fids = []
        for branch in branch_index.branches:
            if branch.head_ref_id:
                structural_fids.append(f'bare/refs/{branch.head_ref_id}')
            if branch.public_key_id:
                structural_fids.append(f'bare/keys/{branch.public_key_id}')
        if structural_fids:
            for fid, data in self.api.batch_read(vault_id, structural_fids).items():
                if data:
                    save_file(fid, data)

        named_ref_id    = str(named_meta.head_ref_id)
        named_commit_id = ref_manager.read_ref(named_ref_id, read_key) if named_ref_id else None
        if not named_commit_id:
            clone_mode      = Schema__Clone_Mode(mode=Enum__Clone_Mode.READ_ONLY,
                                                 vault_id=vault_id, read_key=read_key_hex)
            clone_mode_path = storage.clone_mode_path(directory)
            with open(clone_mode_path, 'w') as f:
                _json.dump(clone_mode.json(), f, indent=2)
            storage.chmod_local_file(clone_mode_path)
            return dict(vault_id=vault_id, directory=directory, file_count=0, mode='read-only')

        # Phase 3: Walk commit chain + download tree objects
        _p('step', 'Downloading commits and trees')
        vc          = Vault__Commit(crypto=self.crypto, pki=pki,
                                    object_store=obj_store, ref_manager=ref_manager)
        commit_ids  = []
        queue       = [named_commit_id]
        visited     = set()
        while queue:
            cid = queue.pop(0)
            if cid in visited:
                continue
            visited.add(cid)
            commit_ids.append(cid)
            obj_data = self.api.batch_read(vault_id, [f'bare/data/{cid}'])
            if obj_data.get(f'bare/data/{cid}'):
                save_file(f'bare/data/{cid}', obj_data[f'bare/data/{cid}'])
            try:
                commit_obj = vc.load_commit(cid, read_key)
                for pid in commit_obj.parents:
                    if str(pid) not in visited:
                        queue.append(str(pid))
            except Exception:
                pass

        root_tree_ids  = []
        visited_commit = set()
        for cid in commit_ids:
            try:
                commit_obj = vc.load_commit(cid, read_key)
                tid        = str(commit_obj.tree_id)
                if tid and tid not in visited_commit:
                    root_tree_ids.append(tid)
                    visited_commit.add(tid)
            except Exception:
                pass

        visited_trees = set()
        tree_queue    = list(root_tree_ids)
        while tree_queue:
            to_dl = [f'bare/data/{tid}' for tid in tree_queue if tid not in visited_trees]
            if to_dl:
                for fid, data in self.api.batch_read(vault_id, to_dl).items():
                    if data:
                        save_file(fid, data)
            next_trees = []
            for tid in tree_queue:
                if tid in visited_trees:
                    continue
                visited_trees.add(tid)
                try:
                    tree = vc.load_tree(tid, read_key)
                    for entry in tree.entries:
                        sub_tid = str(entry.tree_id) if entry.tree_id else None
                        if sub_tid and sub_tid not in visited_trees:
                            next_trees.append(sub_tid)
                except Exception:
                    pass
            tree_queue = next_trees

        # Phase 4: Collect blobs and write working copy (unless sparse)
        sub_tree = Vault__Sub_Tree(crypto=self.crypto, obj_store=obj_store)
        try:
            named_commit = vc.load_commit(named_commit_id, read_key)
            flat         = sub_tree.flatten(str(named_commit.tree_id), read_key)
        except Exception:
            flat = {}

        file_count = len(flat)

        if not sparse and flat:
            _p('download', 'Fetching blobs', f'0/{file_count}')
            blob_ids = [e['blob_id'] for e in flat.values() if e.get('blob_id')]
            fids     = [f'bare/data/{b}' for b in blob_ids]
            done     = 0
            chunk    = 50
            for i in range(0, len(fids), chunk):
                batch = fids[i:i + chunk]
                for fid, data in self.api.batch_read(vault_id, batch).items():
                    if data:
                        save_file(fid, data)
                    done += 1
                    _p('download', 'Fetching blobs', f'{done}/{file_count}')

            for rel_path, entry_data in flat.items():
                blob_id = entry_data.get('blob_id', '')
                if not blob_id or not obj_store.exists(blob_id):
                    continue
                try:
                    ciphertext = obj_store.load(blob_id)
                    plaintext  = self.crypto.decrypt(read_key, ciphertext)
                    dest       = os.path.join(directory, rel_path)
                    os.makedirs(os.path.dirname(dest), exist_ok=True)
                    with open(dest, 'wb') as f:
                        f.write(plaintext)
                except Exception:
                    pass

        # Save clone_mode.json (no clone branch, no vault_key file)
        clone_mode      = Schema__Clone_Mode(mode=Enum__Clone_Mode.READ_ONLY,
                                             vault_id=vault_id, read_key=read_key_hex)
        clone_mode_path = storage.clone_mode_path(directory)
        with open(clone_mode_path, 'w') as f:
            _json.dump(clone_mode.json(), f, indent=2)
        storage.chmod_local_file(clone_mode_path)

        return dict(vault_id   = vault_id,
                    directory  = directory,
                    file_count = file_count,
                    commit_id  = named_commit_id or '',
                    sparse     = sparse,
                    mode       = 'read-only')

    def clone_from_transfer(self, token_str: str, directory: str,
                            debug_log=None) -> dict:
        """Download and import a SG/Send transfer, creating a new local vault."""
        from sgit_ai.api.API__Transfer            import API__Transfer
        from sgit_ai.transfer.Vault__Transfer     import Vault__Transfer
        from sgit_ai.transfer.Simple_Token__Wordlist import Simple_Token__Wordlist

        api      = API__Transfer(debug_log=debug_log)
        api.setup()
        transfer = Vault__Transfer(api=api, crypto=self.crypto)

        receive_result = transfer.receive(token_str)
        files          = receive_result['files']

        new_token = str(Simple_Token__Wordlist().setup().generate())

        from sgit_ai.sync.Vault__Sync import Vault__Sync as _VS
        _VS(crypto=self.crypto, api=self.api).init(directory, token=new_token, allow_nonempty=True)

        for path, content in files.items():
            top = path.split('/')[0]
            if top.startswith('__share__') or top.startswith('_share.') or top.startswith('__gallery__'):
                continue
            full_path = os.path.join(directory, path)
            parent    = os.path.dirname(full_path)
            if parent and parent != directory:
                os.makedirs(parent, exist_ok=True)
            with open(full_path, 'wb') as f:
                f.write(content if isinstance(content, bytes) else content.encode('utf-8'))

        from sgit_ai.core.actions.commit.Vault__Sync__Commit import Vault__Sync__Commit
        Vault__Sync__Commit(crypto=self.crypto, api=self.api).commit(
            directory, message=f'Imported from vault://{token_str}')

        storage     = Vault__Storage()
        config_path = storage.local_config_path(directory)
        with open(config_path, 'r') as f:
            config_data = json.load(f)
        config_data['share_token'] = token_str
        with open(config_path, 'w') as f:
            json.dump(config_data, f, indent=2)
        storage.chmod_local_file(config_path)

        from sgit_ai.safe_types.Safe_Str__Simple_Token import Safe_Str__Simple_Token as _SST
        from sgit_ai.transfer.Simple_Token            import Simple_Token as _ST2
        new_vault_id = _ST2(token=_SST(new_token)).transfer_id()
        branch_id    = config_data.get('my_branch_id', '')
        return dict(vault_id    = new_vault_id,
                    branch_id   = branch_id,
                    share_token = token_str,
                    file_count  = len(files),
                    directory   = directory)

    def _clone_resolve_simple_token(self, token_str: str, directory: str,
                                    on_progress: callable = None, sparse: bool = False) -> dict:
        """Resolve a simple token clone: check SGit-AI vault first, then SG/Send transfer."""
        from sgit_ai.transfer.Simple_Token import Simple_Token as _ST
        from sgit_ai.safe_types.Safe_Str__Simple_Token import Safe_Str__Simple_Token as _SST

        _p        = on_progress or (lambda *a, **k: None)
        debug_log = getattr(self.api, 'debug_log', None)

        st      = _ST(token=_SST(token_str))
        xfer_id = st.transfer_id()

        # Step 1: try SGit-AI vault lookup
        _p('step', f'Checking SGit-AI for vault: {token_str}')
        try:
            keys      = self.crypto.derive_keys_from_simple_token(token_str)
            vault_id  = keys['vault_id']
            index_id  = keys['branch_index_file_id']
            index_fid = f'bare/indexes/{index_id}'
            idx_data  = self.api.batch_read(vault_id, [index_fid])
            if idx_data.get(index_fid):
                _p('step', 'Vault found on SGit-AI — cloning with simple token keys')
                return self._clone_with_keys(token_str, directory, on_progress, sparse=sparse)
        except Exception:
            pass

        # Step 2: try SG/Send transfer lookup
        _p('step', f'Vault not found — checking SG/Send for transfer: {token_str}')
        _p('step', f'  Derived transfer ID: {xfer_id}  (SHA-256("{token_str}")[:12])')

        from sgit_ai.api.API__Transfer import API__Transfer as _AT
        _probe = _AT(debug_log=debug_log)
        _probe.setup()
        try:
            _probe.info(xfer_id)
        except Exception:
            raise RuntimeError(f"No vault or transfer found for '{token_str}' "
                               f"(transfer_id={xfer_id})")

        _p('step', f'  Transfer found on SG/Send — downloading and importing...')
        return self.clone_from_transfer(token_str, directory, debug_log=debug_log)

    def _clone_download_blobs(self, vault_id: str, vc, sub_tree,
                              named_commit_id: str, read_key: bytes,
                              save_file, _p) -> dict:
        """Phases 5-7 of clone: flatten HEAD tree and download all blobs.

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
