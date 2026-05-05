"""Vault__Sync__Pull — pull and reset operations."""
import os
import time
from   urllib.request                              import urlopen
from   sgit_ai.crypto.PKI__Crypto                 import PKI__Crypto
from   sgit_ai.storage.Vault__Commit              import Vault__Commit
from   sgit_ai.storage.Vault__Object_Store        import Vault__Object_Store
from   sgit_ai.storage.Vault__Ref_Manager         import Vault__Ref_Manager
from   sgit_ai.core.actions.fetch.Vault__Fetch    import Vault__Fetch
from   sgit_ai.storage.Vault__Sub_Tree            import Vault__Sub_Tree
from   sgit_ai.core.Vault__Sync__Base             import Vault__Sync__Base


class Vault__Sync__Pull(Vault__Sync__Base):

    def reset(self, directory: str, commit_id: str = None) -> dict:
        """Reset the local clone branch HEAD to commit_id and restore working copy."""
        c = self._init_components(directory)
        read_key       = c.read_key
        obj_store      = c.obj_store
        ref_manager    = c.ref_manager
        branch_manager = c.branch_manager
        storage        = c.storage
        pki            = c.pki

        local_config = self._read_local_config(directory, storage)
        branch_id    = str(local_config.my_branch_id)

        index_id = c.branch_index_file_id
        if not index_id:
            raise RuntimeError('No branch index found — is this a v2 vault?')
        branch_index = branch_manager.load_branch_index(directory, index_id, read_key)
        branch_meta  = branch_manager.get_branch_by_id(branch_index, branch_id)
        if not branch_meta:
            raise RuntimeError(f'Branch not found: {branch_id}')

        current_commit_id = ref_manager.read_ref(str(branch_meta.head_ref_id), read_key)

        if commit_id is None:
            if not current_commit_id:
                raise RuntimeError('No commits yet — nothing to reset to')
            commit_id = current_commit_id

        vault_commit = Vault__Commit(crypto=self.crypto, pki=pki,
                                     object_store=obj_store, ref_manager=ref_manager)
        try:
            target_commit = vault_commit.load_commit(commit_id, read_key)
        except FileNotFoundError:
            raise RuntimeError(f'Commit not found locally: {commit_id} '
                               f'— run sgit pull to fetch missing history first')

        sub_tree = Vault__Sub_Tree(crypto=self.crypto, obj_store=obj_store)
        target_flat = sub_tree.flatten(str(target_commit.tree_id), read_key)

        disk_map = self._scan_local_directory(directory)

        self._checkout_flat_map(directory, target_flat, obj_store, read_key)
        self._remove_deleted_flat(directory, disk_map, target_flat)

        ref_manager.write_ref(str(branch_meta.head_ref_id), commit_id, read_key)

        restored = len(target_flat)
        deleted  = len(set(disk_map.keys()) - set(target_flat.keys()))
        return dict(commit_id = commit_id,
                    branch_id = branch_id,
                    restored  = restored,
                    deleted   = deleted)

    def pull(self, directory: str, on_progress: callable = None) -> dict:
        """Fetch named branch state and merge into clone branch via Workflow__Pull."""
        self._auto_gc_drain(directory)
        c = self._init_components(directory)
        if not c.branch_index_file_id:
            raise RuntimeError('No branch index found')

        from sgit_ai.workflow.pull.Workflow__Pull  import Workflow__Pull
        from sgit_ai.workflow.pull.Pull__Workspace import Pull__Workspace
        from sgit_ai.workflow.Workflow__Runner     import Workflow__Runner
        from sgit_ai.schemas.workflow.pull.Schema__Pull__State import Schema__Pull__State
        from sgit_ai.safe_types.Safe_Str__File_Path import Safe_Str__File_Path
        from sgit_ai.storage.Vault__Storage import SG_VAULT_DIR

        wf       = Workflow__Pull()
        work_dir = os.path.join(directory, SG_VAULT_DIR, 'work')
        os.makedirs(work_dir, exist_ok=True)
        ws             = Pull__Workspace.create(wf.workflow_name(), work_dir,
                                                wf.workflow_version())
        ws.sync_client = self
        ws.on_progress = on_progress
        initial        = Schema__Pull__State(directory=Safe_Str__File_Path(directory))
        runner         = Workflow__Runner(workflow=wf, workspace=ws, keep_work=False)
        final_dict     = runner.run(input=initial)

        from sgit_ai.schemas.workflow.pull.Schema__Pull__State import Schema__Pull__State as PullState
        annotations = getattr(PullState, '__annotations__', {})
        valid       = {k: v for k, v in final_dict.items() if k in annotations}
        final_state = PullState(**valid)
        return self._pull_state_to_dict(final_state)

    def _pull_state_to_dict(self, state) -> dict:
        """Convert Schema__Pull__State to the legacy pull() return dict."""
        merge_status = str(state.merge_status) if state.merge_status else 'up_to_date'
        remote_ok    = bool(state.remote_reachable)

        if merge_status == 'up_to_date':
            result = dict(status='up_to_date', message='Already up to date')
            if not remote_ok:
                result['remote_unreachable'] = True
                result['remote_error']       = 'remote unreachable'
                result['message']            = 'Already up to date (remote unreachable)'
            return result

        if merge_status == 'conflict':
            return dict(
                status         = 'conflicts',
                conflicts      = list(state.conflict_paths or []),
                conflict_files = list(state.conflict_paths or []),
                added          = list(state.added_files    or []),
                modified       = list(state.modified_files or []),
                deleted        = list(state.deleted_files  or []),
            )

        # fast_forward or merge → 'merged'
        commit_id = str(state.merge_commit_id) if state.merge_commit_id else ''
        return dict(
            status    = 'merged',
            commit_id = commit_id,
            added     = list(state.added_files    or []),
            modified  = list(state.modified_files or []),
            deleted   = list(state.deleted_files  or []),
            conflicts = [],
        )

    def _pull_stats_line(self, fetch_stats: dict, t_checkout: float) -> str:
        t_graph    = fetch_stats.get('t_graph', 0.0)
        t_download = fetch_stats.get('t_download', 0.0)
        n_commits  = fetch_stats.get('n_commits', 0)
        n_trees    = fetch_stats.get('n_trees', 0)
        n_blobs    = fetch_stats.get('n_blobs', 0)
        total      = t_graph + t_download + t_checkout
        return (f'{n_commits} commit{"s" if n_commits != 1 else ""}, '
                f'{n_trees} tree{"s" if n_trees != 1 else ""}, '
                f'{n_blobs} blob{"s" if n_blobs != 1 else ""} '
                f'in {total:.1f}s')

    def _find_missing_blobs(self, commit_id: str, obj_store: Vault__Object_Store,
                            read_key: bytes) -> list:
        """Return list of blob_ids required by commit_id's tree that are absent locally."""
        try:
            pki          = PKI__Crypto()
            vault_commit = Vault__Commit(crypto=self.crypto, pki=pki,
                                         object_store=obj_store, ref_manager=None)
            commit_obj   = vault_commit.load_commit(commit_id, read_key)
            sub_tree     = Vault__Sub_Tree(crypto=self.crypto, obj_store=obj_store)
            flat_map     = sub_tree.flatten(str(commit_obj.tree_id), read_key)
        except Exception:
            return []

        return [entry['blob_id'] for entry in flat_map.values()
                if entry.get('blob_id') and not obj_store.exists(entry['blob_id'])]

    def _fetch_missing_objects(self, vault_id: str, commit_id: str,
                               obj_store: Vault__Object_Store, read_key: bytes,
                               sg_dir: str, _p: callable = None,
                               stop_at: str = None, include_blobs: bool = True) -> dict:
        """BFS-walk commit chain from commit_id, downloading any missing objects."""
        _p = _p or (lambda *a, **k: None)
        pki = PKI__Crypto()
        vc  = Vault__Commit(crypto=self.crypto, pki=pki,
                            object_store=obj_store, ref_manager=Vault__Ref_Manager())

        def _save(fid: str, data: bytes) -> None:
            oid        = fid.replace('bare/data/', '')
            local_path = os.path.join(sg_dir, 'bare', 'data', oid)
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            with open(local_path, 'wb') as f:
                f.write(data)

        def _batch_save(fids: list) -> None:
            if not fids:
                return
            try:
                for fid, data in self.api.batch_read(vault_id, fids).items():
                    if data:
                        _save(fid, data)
            except Exception:
                pass

        # ── Phase 1: BFS commit walk ─────────────────────────────────────────
        n_commits       = 0
        commit_infos    = []
        root_tree_ids   = []
        visited_commits = set()
        if stop_at:
            visited_commits.add(stop_at)

        _p('scan', 'Analysing commit graph', '0 commits')
        t_graph_start = time.monotonic()

        commit_wave = [commit_id]
        while commit_wave:
            unvisited = [c for c in commit_wave if c and c not in visited_commits]
            if not unvisited:
                break

            missing_cids = [c for c in unvisited if not obj_store.exists(c)]
            if missing_cids:
                _batch_save([f'bare/data/{c}' for c in missing_cids])

            next_wave = []
            for cid in unvisited:
                if cid in visited_commits:
                    continue
                visited_commits.add(cid)
                if not obj_store.exists(cid):
                    continue
                try:
                    commit  = vc.load_commit(cid, read_key)
                    tree_id = str(commit.tree_id) if commit.tree_id else None
                    if tree_id:
                        root_tree_ids.append(tree_id)
                    if cid in set(missing_cids):
                        n_commits += 1
                        commit_infos.append((
                            cid[12:],
                            int(commit.timestamp_ms) if commit.timestamp_ms else 0,
                            str(commit.message_enc) if commit.message_enc else '',
                        ))
                    for pid in (list(commit.parents) if commit.parents else []):
                        pid_str = str(pid)
                        if pid_str in visited_commits:
                            continue
                        if obj_store.exists(pid_str):
                            visited_commits.add(pid_str)
                        else:
                            next_wave.append(pid_str)
                except Exception:
                    pass

            _p('scan', 'Analysing commit graph',
               f'{n_commits} commit{"s" if n_commits != 1 else ""} · fetching trees...')
            commit_wave = next_wave

        # ── Phase 2: BFS tree walk (one batch per depth level) ───────────────
        n_trees      = 0
        seen_trees   = set()
        tree_wave    = [t for t in root_tree_ids if t]

        while tree_wave:
            missing_tids = [t for t in tree_wave
                            if t not in seen_trees and not obj_store.exists(t)]
            if missing_tids:
                n_trees += len(missing_tids)
                _batch_save([f'bare/data/{t}' for t in missing_tids])

            next_wave = []
            for tid in tree_wave:
                if tid in seen_trees:
                    continue
                seen_trees.add(tid)
                if not obj_store.exists(tid):
                    continue
                try:
                    tree = vc.load_tree(tid, read_key)
                    for entry in tree.entries:
                        sub_tid = str(entry.tree_id) if entry.tree_id else None
                        if sub_tid and sub_tid not in seen_trees:
                            next_wave.append(sub_tid)
                except Exception:
                    pass

            _p('scan', 'Analysing commit graph',
               f'{n_commits} commit{"s" if n_commits != 1 else ""} · {n_trees} trees · collecting blobs...')
            tree_wave = next_wave

        # ── Phase 3: collect missing blobs ───────────────────────────────────
        missing_blobs = []
        seen_blobs    = set()
        if include_blobs:
            for tid in seen_trees:
                if not obj_store.exists(tid):
                    continue
                try:
                    tree = vc.load_tree(tid, read_key)
                    for entry in tree.entries:
                        blob_id = str(entry.blob_id) if entry.blob_id else None
                        if blob_id and blob_id not in seen_blobs and not obj_store.exists(blob_id):
                            seen_blobs.add(blob_id)
                            missing_blobs.append((f'bare/data/{blob_id}',
                                                  getattr(entry, 'large', False)))
                except Exception:
                    pass

        t_graph = time.monotonic() - t_graph_start

        _p('scan_done', 'Commit graph analysed',
           f'{n_commits} new commit{"s" if n_commits != 1 else ""} · {n_trees} trees · {len(missing_blobs)} blobs')
        for oid_short, ts_ms, enc_msg in reversed(commit_infos):
            msg = ''
            if enc_msg:
                try:
                    msg = self.crypto.decrypt_metadata(read_key, enc_msg)
                except Exception:
                    pass
            label = f'"{msg[:60]}"' if msg else '(no message)'
            _p('commit', oid_short, label)

        if not missing_blobs:
            return {'t_graph': t_graph, 't_download': 0.0,
                    'n_commits': n_commits, 'n_trees': n_trees, 'n_blobs': 0}

        # ── Pass 2: download blobs with a progress bar ───────────────────────
        n_blobs    = len(missing_blobs)
        downloaded = 0
        t_dl_start = time.monotonic()
        _p('download', 'Downloading objects', f'0/{n_blobs}')

        for file_id, is_large in missing_blobs:
            oid = file_id.replace('bare/data/', '')
            if obj_store.exists(oid):
                downloaded += 1
                _p('download', 'Downloading objects', f'{downloaded}/{n_blobs}')
                continue
            try:
                if is_large:
                    url_info = self.api.presigned_read_url(vault_id, file_id)
                    data     = urlopen(url_info['url']).read()
                else:
                    data = self.api.read(vault_id, file_id)
                if data:
                    _save(file_id, data)
            except Exception:
                pass
            downloaded += 1
            _p('download', 'Downloading objects', f'{downloaded}/{n_blobs}')

        t_download = time.monotonic() - t_dl_start
        return {'t_graph': t_graph, 't_download': t_download,
                'n_commits': n_commits, 'n_trees': n_trees, 'n_blobs': n_blobs}
