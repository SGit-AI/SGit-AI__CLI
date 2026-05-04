"""Vault__Sync__Pull — pull and reset operations (Brief 22 — E5)."""
import json
import os
import time
from   urllib.request                              import urlopen
from   sgit_ai.crypto.PKI__Crypto                 import PKI__Crypto
from   sgit_ai.storage.Vault__Commit              import Vault__Commit
from   sgit_ai.storage.Vault__Object_Store        import Vault__Object_Store
from   sgit_ai.storage.Vault__Ref_Manager         import Vault__Ref_Manager
from   sgit_ai.sync.Vault__Fetch                  import Vault__Fetch
from   sgit_ai.sync.Vault__Merge                  import Vault__Merge
from   sgit_ai.storage.Vault__Sub_Tree               import Vault__Sub_Tree
from   sgit_ai.core.Vault__Sync__Base             import Vault__Sync__Base


def _pull_stats_line(fetch_stats: dict, t_checkout: float) -> str:
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


class Vault__Sync__Pull(Vault__Sync__Base):

    def reset(self, directory: str, commit_id: str = None) -> dict:
        """Reset the local clone branch HEAD to commit_id and restore working copy.

        If commit_id is None, resets to the current HEAD (discards working copy
        changes without moving the branch pointer — equivalent to git restore .).
        Equivalent to git reset --hard <commit>.  Does not touch the server.
        Use sgit push --force afterwards to rewrite the remote ref.
        """
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
        """Fetch named branch state and merge into clone branch.

        Workflow:
        0. Drain any pending change packs (GC)
        1. Read local config to find clone branch
        2. Find named branch in branch index
        3. Read named branch ref (remote state) and clone branch ref (local state)
        4. Find LCA of both heads
        5. Three-way merge: base=LCA tree, ours=clone tree, theirs=named tree
        6. If no conflicts, create merge commit on clone branch
        7. If conflicts, write .conflict files and return conflict info
        8. Update working directory with merged files
        """
        _p = on_progress or (lambda *a, **k: None)
        self._auto_gc_drain(directory)

        c = self._init_components(directory)
        read_key       = c.read_key
        storage        = c.storage
        pki            = c.pki
        obj_store      = c.obj_store
        ref_manager    = c.ref_manager
        key_manager    = c.key_manager
        branch_manager = c.branch_manager

        local_config    = self._read_local_config(directory, storage)
        clone_branch_id = str(local_config.my_branch_id)

        index_id = c.branch_index_file_id
        if not index_id:
            raise RuntimeError('No branch index found')
        branch_index = branch_manager.load_branch_index(directory, index_id, read_key)

        clone_meta = branch_manager.get_branch_by_id(branch_index, clone_branch_id)
        if not clone_meta:
            raise RuntimeError(f'Clone branch not found: {clone_branch_id}')

        named_meta = branch_manager.get_branch_by_name(branch_index, 'current')
        if not named_meta:
            raise RuntimeError('Named branch "current" not found')

        clone_commit_id = ref_manager.read_ref(str(clone_meta.head_ref_id), read_key)

        _p('step', 'Fetching remote ref')
        vault_id  = c.vault_id
        named_ref_file_id = f'bare/refs/{named_meta.head_ref_id}'
        remote_fetch_ok   = False
        remote_fetch_error = None
        try:
            remote_ref_data = self.api.read(vault_id, named_ref_file_id)
            if remote_ref_data:
                ref_path = os.path.join(c.sg_dir, named_ref_file_id)
                os.makedirs(os.path.dirname(ref_path), exist_ok=True)
                with open(ref_path, 'wb') as f:
                    f.write(remote_ref_data)
                remote_fetch_ok = True
        except Exception as e:
            remote_fetch_error = e
            _p('warn', f'Could not fetch remote ref: {e}')

        named_commit_id = ref_manager.read_ref(str(named_meta.head_ref_id), read_key)

        clone_short = clone_commit_id or '(none)'
        named_short = named_commit_id or '(none)'
        _p('step', f'Local HEAD: {clone_short}, Remote HEAD: {named_short}')

        if not named_commit_id:
            result = dict(status='up_to_date', message='Named branch has no commits')
            if not remote_fetch_ok:
                result['remote_unreachable'] = True
                result['remote_error']       = str(remote_fetch_error) if remote_fetch_error else 'empty response'
            return result

        if clone_commit_id == named_commit_id:
            if not remote_fetch_ok:
                _p('warn', 'Could not reach remote — comparison based on local data only')
                return dict(status='up_to_date',
                            message='Already up to date (remote unreachable)',
                            remote_unreachable=True,
                            remote_error=str(remote_fetch_error) if remote_fetch_error else 'empty response')
            return dict(status='up_to_date', message='Already up to date')

        _config_path = storage.local_config_path(directory)
        _sparse = False
        if os.path.isfile(_config_path):
            _sparse = self._read_local_config(directory, storage).sparse

        fetch_stats = self._fetch_missing_objects(vault_id, named_commit_id, obj_store, read_key, c.sg_dir, _p,
                                                  stop_at=clone_commit_id, include_blobs=not _sparse)

        if not _sparse:
            missing_blobs = self._find_missing_blobs(named_commit_id, obj_store, read_key)
            if missing_blobs:
                n = len(missing_blobs)
                examples = ', '.join(sorted(missing_blobs)[:3])
                raise RuntimeError(
                    f'Pull incomplete: {n} object(s) failed to download from the server '
                    f'(server may be under load — retry with: sgit pull).\n'
                    f'  Missing: {examples}{"..." if n > 3 else ""}')

        vault_commit = Vault__Commit(crypto=self.crypto, pki=pki,
                                     object_store=obj_store, ref_manager=ref_manager)
        fetcher      = Vault__Fetch(crypto=self.crypto, api=self.api, storage=storage)
        merger       = Vault__Merge(crypto=self.crypto)

        lca_id = fetcher.find_lca(obj_store, read_key, clone_commit_id, named_commit_id)

        if lca_id == named_commit_id:
            result = dict(status='up_to_date', message='Already up to date')
            if not remote_fetch_ok:
                result['remote_unreachable'] = True
                result['remote_error']       = str(remote_fetch_error) if remote_fetch_error else 'empty response'
                result['message']            = 'Already up to date (remote unreachable)'
            return result

        sub_tree = Vault__Sub_Tree(crypto=self.crypto, obj_store=obj_store)

        if lca_id == clone_commit_id:
            named_commit_ff = vault_commit.load_commit(named_commit_id, read_key)
            theirs_map_ff   = sub_tree.flatten(str(named_commit_ff.tree_id), read_key)
            ours_map_ff     = {}
            if clone_commit_id:
                ours_commit_ff = vault_commit.load_commit(clone_commit_id, read_key)
                ours_map_ff    = sub_tree.flatten(str(ours_commit_ff.tree_id), read_key)

            _p('step', 'Updating working copy')
            t_co = time.monotonic()
            self._checkout_flat_map(directory, theirs_map_ff, obj_store, read_key)
            self._remove_deleted_flat(directory, ours_map_ff, theirs_map_ff)
            ref_manager.write_ref(str(clone_meta.head_ref_id), named_commit_id, read_key)
            t_checkout = time.monotonic() - t_co
            _p('stats', _pull_stats_line(fetch_stats, t_checkout))

            added    = [p for p in theirs_map_ff if p not in ours_map_ff]
            deleted  = [p for p in ours_map_ff   if p not in theirs_map_ff]
            modified = [p for p in theirs_map_ff
                        if p in ours_map_ff and
                        theirs_map_ff[p].get('blob_id') != ours_map_ff[p].get('blob_id')]

            return dict(status    = 'merged',
                        commit_id = named_commit_id,
                        added     = added,
                        modified  = modified,
                        deleted   = deleted,
                        conflicts = [])

        base_map = {}
        if lca_id:
            lca_commit = vault_commit.load_commit(lca_id, read_key)
            base_map   = sub_tree.flatten(str(lca_commit.tree_id), read_key)

        ours_map = {}
        if clone_commit_id:
            ours_commit = vault_commit.load_commit(clone_commit_id, read_key)
            ours_map    = sub_tree.flatten(str(ours_commit.tree_id), read_key)

        named_commit = vault_commit.load_commit(named_commit_id, read_key)
        theirs_map   = sub_tree.flatten(str(named_commit.tree_id), read_key)

        _p('step', 'Merging trees')
        merge_result = merger.three_way_merge(base_map, ours_map, theirs_map)
        merged_map   = merge_result['merged_map']
        conflicts    = merge_result['conflicts']

        _p('step', 'Updating working copy')
        t_co = time.monotonic()
        self._checkout_flat_map(directory, merged_map, obj_store, read_key)
        self._remove_deleted_flat(directory, ours_map, merged_map)
        t_checkout = time.monotonic() - t_co

        if conflicts:
            conflict_files = merger.write_conflict_files(directory, conflicts,
                                                         theirs_map,
                                                         obj_store, read_key)
            merge_state = dict(clone_commit_id = clone_commit_id,
                               named_commit_id = named_commit_id,
                               lca_id          = lca_id,
                               conflicts       = conflicts)
            merge_state_path = os.path.join(storage.local_dir(directory), 'merge_state.json')
            with open(merge_state_path, 'w') as f:
                json.dump(merge_state, f, indent=2)
            storage.chmod_local_file(merge_state_path)

            return dict(status         = 'conflicts',
                        conflicts      = conflicts,
                        conflict_files = conflict_files,
                        added          = merge_result['added'],
                        modified       = merge_result['modified'],
                        deleted        = merge_result['deleted'])

        signing_key = None
        try:
            signing_key = key_manager.load_private_key_locally(
                str(clone_meta.public_key_id), storage.local_dir(directory))
        except (FileNotFoundError, Exception):
            pass

        parent_ids = [p for p in [clone_commit_id, named_commit_id] if p]
        merged_tree_id = sub_tree.build_from_flat(merged_map, read_key)

        merge_commit_id = vault_commit.create_commit(
            read_key    = read_key,
            tree_id     = merged_tree_id,
            parent_ids  = parent_ids,
            message     = f'Merge {str(named_meta.name)} into {str(clone_meta.name)}',
            branch_id   = clone_branch_id,
            signing_key = signing_key)

        ref_manager.write_ref(str(clone_meta.head_ref_id), merge_commit_id, read_key)
        _p('stats', _pull_stats_line(fetch_stats, t_checkout))

        return dict(status    = 'merged',
                    commit_id = merge_commit_id,
                    added     = merge_result['added'],
                    modified  = merge_result['modified'],
                    deleted   = merge_result['deleted'],
                    conflicts = [])

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
        """Walk the commit chain from commit_id, downloading any missing objects.

        Stops walking a branch as soon as it hits a commit that already exists
        locally — that commit's full ancestry is already present (it was fetched
        by a previous clone or pull), so there is nothing further to download in
        that direction.  The explicit stop_at commit (if given) is treated the
        same way.

        BFS with batch_read: commits are downloaded in BFS waves; trees are
        downloaded in per-depth-level waves (typically ~5-6 batches instead of
        one HTTP request per object).  Blobs are collected and downloaded in
        Pass 2.  Returns timing stats dict.
        """
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
