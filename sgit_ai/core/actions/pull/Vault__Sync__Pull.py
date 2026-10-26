"""Vault__Sync__Pull — pull and reset operations."""
import os
import threading
import time
from   concurrent.futures                         import ThreadPoolExecutor
from   sgit_ai.crypto.PKI__Crypto                 import PKI__Crypto
from   sgit_ai.storage.Vault__Commit              import Vault__Commit
from   sgit_ai.schemas.Schema__Tree_Entries__Light import Schema__Tree_Entries__Light
from   sgit_ai.storage.Vault__Object_Store        import Vault__Object_Store
from   sgit_ai.storage.Vault__Ref_Manager         import Vault__Ref_Manager
from   sgit_ai.core.actions.fetch.Vault__Fetch    import Vault__Fetch
from   sgit_ai.storage.Vault__Sub_Tree            import Vault__Sub_Tree
from   sgit_ai.storage.graph.Vault__Graph_Walk     import Vault__Graph_Walk
from   sgit_ai.core.Vault__Sync__Base             import Vault__Sync__Base
from   sgit_ai.network.api.Vault__API             import MAX_BATCH_OPS, BATCH_READ_WORKERS

SWEEP_AFTER_WAVES = 25        # sequential commit fetches a pull makes before it lists the store and fetches in bulk
COMMIT_CLOCK_SKEW_MS = 24 * 3600 * 1000          # a pull's commit list is exact for a clock up to a day behind
PLAN_COMMITS_MAX     = 5000                              # base..head longer than this: the walk, not the index plan


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
        else:                                                        # HEAD~2, @{1}, a tag, a short id … (Vault__Revision)
            from sgit_ai.core.actions.history.Vault__Revision import Vault__Revision
            commit_id = Vault__Revision(crypto=self.crypto, api=self.api).resolve_soft(directory, commit_id)

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

    def pull(self, directory: str, on_progress: callable = None, accept_rewind: bool = False,
             merge_from: str = None, checkout: bool = True) -> dict:
        """Fetch the tracked named branch and merge it into this clone; with merge_from,
        fetch and merge THAT named branch instead (`sgit branch merge <name>`). With
        checkout=False (`sgit pull --no-checkout`, a selective working copy only) the
        merge moves the clone's head and records what changed, but writes no file:
        `sgit checkout --since-pull` writes those."""
        from sgit_ai.core.actions.merge.Vault__Merge__State import Vault__Merge__State
        Vault__Merge__State().check_not_in_progress(directory, 'pull')
        self._auto_gc_drain(directory)
        c = self._init_components(directory)
        if not c.branch_index_file_id:
            raise RuntimeError('No branch index found')
        if not checkout and not self._read_local_config(directory, c.storage).sparse:
            raise RuntimeError('--no-checkout needs a selective working copy (a clone made with '
                               '--no-checkout or --sparse): on a full clone a pull writes what changed')

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
        ws.sync_client   = self
        ws.on_progress   = on_progress
        ws.accept_rewind = bool(accept_rewind)
        ws.no_checkout   = not checkout
        if merge_from:
            ws.merge_from = merge_from
        initial        = Schema__Pull__State(directory=Safe_Str__File_Path(directory))
        runner         = Workflow__Runner(workflow=wf, workspace=ws, keep_work=False)
        final_dict     = runner.run(input=initial)

        from sgit_ai.schemas.workflow.pull.Schema__Pull__State import Schema__Pull__State as PullState
        annotations = getattr(PullState, '__annotations__', {})
        valid       = {k: v for k, v in final_dict.items() if k in annotations}
        final_state = PullState(**valid)
        return self._pull_state_to_dict(final_state)

    def pull_read_only(self, directory: str, on_progress: callable = None, accept_rewind: bool = False) -> dict:
        """Read-only pull (architect contract §5.3): re-fetch the named-branch HEAD,
        download missing objects, re-checkout the working copy — NO merge, NO commit
        creation, NO clone-branch ref write. Every server call is an api.read(...) only.
        """
        self._auto_gc_drain(directory)
        c = self._init_components(directory)
        if not c.branch_index_file_id:
            raise RuntimeError('No branch index found')

        from sgit_ai.workflow.pull.Workflow__Pull__ReadOnly import Workflow__Pull__ReadOnly
        from sgit_ai.workflow.pull.Pull__Workspace          import Pull__Workspace
        from sgit_ai.workflow.Workflow__Runner               import Workflow__Runner
        from sgit_ai.schemas.workflow.pull.Schema__Pull__State import Schema__Pull__State
        from sgit_ai.safe_types.Safe_Str__File_Path           import Safe_Str__File_Path
        from sgit_ai.storage.Vault__Storage                   import SG_VAULT_DIR

        wf       = Workflow__Pull__ReadOnly()
        work_dir = os.path.join(directory, SG_VAULT_DIR, 'work')
        os.makedirs(work_dir, exist_ok=True)
        ws             = Pull__Workspace.create(wf.workflow_name(), work_dir,
                                                wf.workflow_version())
        ws.sync_client   = self
        ws.on_progress   = on_progress
        ws.accept_rewind = bool(accept_rewind)
        initial        = Schema__Pull__State(directory=Safe_Str__File_Path(directory))
        runner         = Workflow__Runner(workflow=wf, workspace=ws, keep_work=False)
        final_dict     = runner.run(input=initial)

        annotations = getattr(Schema__Pull__State, '__annotations__', {})
        valid       = {k: v for k, v in final_dict.items() if k in annotations}
        final_state = Schema__Pull__State(**valid)
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
                kept_dirty     = list(state.kept_dirty_files or []),
                added          = list(state.added_files    or []),
                modified       = list(state.modified_files or []),
                deleted        = list(state.deleted_files  or []),
            )

        # fast_forward, merge or an accepted rewind → 'merged'
        commit_id = str(state.merge_commit_id) if state.merge_commit_id else ''
        result = dict(
            status     = 'merged',
            commit_id  = commit_id,
            not_written = list(state.not_written_files or []),
            added      = list(state.added_files      or []),
            modified   = list(state.modified_files   or []),
            deleted    = list(state.deleted_files    or []),
            kept_dirty = list(state.kept_dirty_files or []),
            conflicts  = [],
        )
        if merge_status == 'rewound':
            result['rewound']   = True
            result['reapplied'] = bool(commit_id) and commit_id != str(state.named_commit_id or '')
        return result

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

    def _pack_index_reader(self, directory: str, read_key: bytes, packs=None):
        """The index reader for this pull, or None: a pack vault whose branch index carries
        the advisory 'pack-indexes' feature, with the reader on. Never raises."""
        try:
            from sgit_ai.core.actions.pack.Vault__Pack_Index__Reader import Vault__Pack_Index__Reader
            if not (self.pack_vault or (packs is not None and packs.is_pack_vault(directory))):
                return None
            reader = Vault__Pack_Index__Reader(crypto=self.crypto, api=self.api)
            if not reader.usable_in(directory):
                return None
            return reader.setup_for(directory, read_key)
        except Exception:
            return None

    def _seed_flat_from_indexes(self, reader, directory: str, commit_id: str, obj_store, read_key: bytes, _p) -> bool:
        """The new head's flat map from the indexes (the last cached head's map plus the
        folder members of each commit on the first-parent chain, or a snapshot index's
        `flat`), anchored to the root tree and remembered by the flat cache. A map that
        cannot be assembled is nothing: the next flatten walks, as before."""
        try:
            sub_tree = Vault__Sub_Tree(crypto=self.crypto, obj_store=obj_store)
            commit   = Vault__Commit(crypto=self.crypto, pki=PKI__Crypto(), object_store=obj_store, ref_manager=None).load_commit(commit_id, read_key)
            tree_id  = str(commit.tree_id or '')
            if not tree_id or sub_tree._flat_cached(tree_id, read_key) is not None:
                return False
            if reader.seed_head_flat(directory, commit_id, read_key, sub_tree, _p) is None:
                return False
            _p('step', 'Flat map of the new head from the pack indexes', f'from the {reader.last_seed}; no tree walk')
            return True
        except Exception:
            return False

    def _find_missing_blobs(self, commit_id: str, obj_store: Vault__Object_Store,
                            read_key: bytes, scope=None) -> list:
        """Return list of blob_ids required by commit_id's tree that are absent locally
        (only the held folders' blobs on a scoped clone)."""
        try:
            pki          = PKI__Crypto()
            vault_commit = Vault__Commit(crypto=self.crypto, pki=pki,
                                         object_store=obj_store, ref_manager=None)
            commit_obj   = vault_commit.load_commit(commit_id, read_key)
            if scope is not None and scope.is_scoped():
                from sgit_ai.storage.Vault__Scoped_Tree import Vault__Scoped_Tree
                flat_map, _ = Vault__Scoped_Tree(crypto=self.crypto, obj_store=obj_store).flatten(
                    str(commit_obj.tree_id), read_key, scope)
            else:
                sub_tree     = Vault__Sub_Tree(crypto=self.crypto, obj_store=obj_store)
                flat_map     = sub_tree.flatten(str(commit_obj.tree_id), read_key)
        except Exception:
            return []

        return [entry['blob_id'] for entry in flat_map.values()
                if entry.get('blob_id') and not obj_store.exists(entry['blob_id'])]

    def _classify_chunk_exception(self, file_id: str, error: Exception):
        """Classify an exception raised while fetching ``file_id``.

        Mirrors Vault__API._classify_exception but lives on the Pull side so
        the sync layer doesn't need a direct API instance — it's invoked from
        the inner _batch_save/single-blob loops in _fetch_missing_objects.
        """
        from urllib.error                                  import HTTPError
        from sgit_ai.schemas.Schema__Fetch_Failure         import Schema__Fetch_Failure
        from sgit_ai.safe_types.Enum__Fetch_Failure_Class  import Enum__Fetch_Failure_Class
        from sgit_ai.safe_types.Safe_Str__Error_Message    import Safe_Str__Error_Message
        from sgit_ai.safe_types.Safe_Str__Object_Id        import Safe_Str__Object_Id

        oid          = file_id.replace('bare/data/', '')
        error_str    = str(error)
        code         = getattr(error, 'code', None) if isinstance(error, HTTPError) else None
        is_absent    = code == 404 or 'HTTP 404' in error_str or 'Not found' in error_str
        is_forbidden = code == 403 or 'HTTP 403' in error_str or 'Forbidden' in error_str
        if is_absent:
            cls = Enum__Fetch_Failure_Class.ABSENT
        elif is_forbidden:
            cls = Enum__Fetch_Failure_Class.FORBIDDEN
        else:
            cls = Enum__Fetch_Failure_Class.TRANSIENT
        try:
            oid_safe = Safe_Str__Object_Id(oid)
        except Exception:
            oid_safe = None
        return Schema__Fetch_Failure(
            file_id        = oid_safe,
            classification = cls,
            error_message  = Safe_Str__Error_Message(error_str),
        )

    def _commit_tree_local(self, vc, commit_id: str, read_key: bytes, obj_store) -> bool:
        try:
            tree_id = str(vc.load_commit(commit_id, read_key).tree_id or '')
        except Exception:
            return False
        return bool(tree_id) and obj_store.exists(tree_id)

    def _sweep_store(self, vault_id: str, obj_store, read_key: bytes, sg_dir: str, _p) -> set:
        """List the vault store once and fetch every object not yet local, batched and in
        parallel (Step__Clone__Bulk_Fetch, the clone's accelerator). Verify-before-write
        per object; a listing the transport cannot give leaves the walk to carry on as
        before. Returns the ids the sweep fetched (empty when it could not run), so the
        walk still counts them as new."""
        from sgit_ai.storage.Vault__Verified_Write          import Vault__Verified_Write
        from sgit_ai.workflow.clone.Step__Clone__Bulk_Fetch import Step__Clone__Bulk_Fetch
        writer = Vault__Verified_Write(crypto=self.crypto)
        sync   = self

        class _WS:                                             # the step's workspace surface
            sync_client = sync
            def progress(self_, *a, **k): _p(*a, **k)
            def save_file(self_, sg_dir_, fid, data, read_key_=None):
                return writer.save(sg_dir_, fid, data, read_key=read_key_) == writer.VERIFIED
        _WS.obj_store = obj_store

        step = Step__Clone__Bulk_Fetch()
        _p('scan', 'Analysing commit graph', 'far behind: listing the vault store for one parallel fetch...')
        ids = step.list_object_ids(_WS(), vault_id)
        if ids is None:
            return set()
        wanted = [oid for oid in ids if not obj_store.exists(oid)]
        step.fetch_all(_WS(), vault_id, sg_dir, read_key, wanted)
        return set(wanted)

    def _commits_between(self, vc, read_key: bytes, head: str, base: str, obj_store,
                         cap: int = 500, skew_ms: int = COMMIT_CLOCK_SKEW_MS, full_ids: bool = False) -> list:
        """base..head over the local store: the commits reachable from head and not
        from base, as (short id, timestamp, encrypted message) newest first (the full
        id with `full_ids`).

        A two-sided walk, newest first, as git does without generation numbers, with
        one addition: before a head-side commit is listed, every base-side commit
        dated within `skew_ms` after it is expanded first, so a clock running up to
        that far behind (a merge whose base is dated before its own parent, the QA
        review's finding 3) still gives the exact answer; the base side is expanded no
        deeper than that window below the oldest new commit, so the cost follows the
        new commits, not the history (the first exact version collected the base's
        whole ancestry: 0.4 ms per commit, 1.9 s on a 5,000-commit chain — QA round 2).
        `cap` bounds what is listed; a clock further off than `skew_ms` can list a
        base-side commit as new (display only)."""
        import heapq
        if not head or not obj_store.exists(head):
            return []
        sides, heap = {}, []

        def add(cid, tags):
            cid = str(cid or '')
            if not cid or not obj_store.exists(cid):
                return
            if cid not in sides:
                try:
                    commit = vc.load_commit(cid, read_key)
                except Exception:
                    return
                sides[cid] = (set(), commit)
                heapq.heappush(heap, (-(int(commit.timestamp_ms) if commit.timestamp_ms else 0), cid))
            sides[cid][0].update(tags)

        def expand(cid):
            tags, commit = sides[cid]
            for p in (commit.parents or []):
                add(p, tags)                                            # a base commit's parents are base's;
                                                                        # a head commit's are head's; both: both
        add(head, {'h'}); add(base, {'b'})
        new = []
        while heap and len(new) < cap:
            if not any('b' not in sides[c][0] for _, c in heap):
                break                                                   # only base-side history is left
            neg_ts, cid = heapq.heappop(heap)
            if 'b' in sides[cid][0]:
                expand(cid)
                continue
            # head-only so far: expand every base-side commit dated within the skew
            # window after it (a child dated before its parent), then look again
            ts = -neg_ts
            while True:
                within = [(n, c) for n, c in heap if 'b' in sides[c][0] and -n >= ts - skew_ms]
                if not within:
                    break
                for item in within:
                    heap.remove(item)
                heapq.heapify(heap)
                for _, c in within:
                    expand(c)
            if 'b' in sides[cid][0]:
                expand(cid)
                continue
            commit = sides[cid][1]
            new.append((cid if full_ids else cid[12:], int(commit.timestamp_ms) if commit.timestamp_ms else 0,
                        str(commit.message_enc) if commit.message_enc else ''))
            expand(cid)
        return new

    def _fetch_missing_objects(self, vault_id: str, commit_id: str,
                               obj_store: Vault__Object_Store, read_key: bytes,
                               sg_dir: str, _p: callable = None,
                               stop_at: str = None, include_blobs: bool = True,
                               failures: dict = None, scope=None, complete_trees: set = None) -> dict:
        """BFS-walk commit chain from commit_id, downloading any missing objects.

        `complete_trees`: tree ids known to be local with everything under them (the
        folders of the head this clone last accepted, whose record is written only once
        every object of that head was local). The walk does not descend into them, so a
        pull's cost follows the folders the new head changed, not the vault: a 301-file
        pull on the 77,227-tree synthetic vault walked every tree through the schema
        parser, 6 of its 9 minutes (newsroom field report, 26 Oct, item 2).

        If ``failures`` is supplied, per-object download failures are recorded
        into it as ``failures[file_id] = Schema__Fetch_Failure(...)`` — letting
        the caller distinguish "absent on server" (404 / 'not_found') from
        "transient" (5xx / network) so honest user messages can be produced.
        """
        _p = _p or (lambda *a, **k: None)
        from sgit_ai.core.actions.pack.Vault__Packs import Vault__Packs
        packs     = Vault__Packs(crypto=self.crypto, api=self.api)
        directory = os.path.dirname(os.path.abspath(sg_dir))
        packed_ids = set()                                      # ids this pull's packs wrote: new to this clone
        if not obj_store.exists(commit_id) and (self.pack_vault or packs.is_pack_vault(directory)):
            packed_ids = set(packs.sync_down(directory, vault_id, read_key, _p, head=commit_id)['objects'])
                                                                # pack vault: the host holds packs; a head that is
                                                                # local came whole with its pack
        pki = PKI__Crypto()
        vc  = Vault__Commit(crypto=self.crypto, pki=pki,
                            object_store=obj_store, ref_manager=Vault__Ref_Manager())

        def _save(fid: str, data: bytes) -> bool:
            # SP-1 / I7: verify before write, per object; a refused object is
            # reported as a fetch failure, never written, and never aborts the run.
            from sgit_ai.storage.Vault__Verified_Write import Vault__Verified_Write
            oid     = fid.replace('bare/data/', '')
            verdict = Vault__Verified_Write(crypto=self.crypto).save(
                sg_dir, f'bare/data/{oid}', data, read_key=read_key)
            if verdict == Vault__Verified_Write.REFUSED:
                _p('warning', 'Object failed integrity check — skipped',
                   f'{fid}: bytes do not hash to the id; not written')
                if failures is not None:
                    failures[fid] = self.api._classify_exception(
                        fid, RuntimeError('integrity check failed: bytes do not hash to the id'))
                return False
            return True

        def _batch_save(fids: list) -> None:
            if not fids:
                return
            try:
                results = self.api.batch_read(vault_id, fids, failures=failures)
            except Exception as e:
                # Whole-chunk failure (the batch endpoint itself errored before
                # per-file status came back). Classify every requested fid via
                # the chunk classifier (404 → ABSENT, 403 → FORBIDDEN, else
                # TRANSIENT) so the caller can report it honestly — never silent.
                if failures is not None:
                    for fid in fids:
                        if fid in failures:
                            continue
                        failures[fid] = self._classify_chunk_exception(fid, e)
                return
            for fid, data in results.items():
                if data:
                    if _save(fid, data) and failures is not None:
                        failures.pop(fid, None)

        # ── Phase 1: BFS commit walk ─────────────────────────────────────────
        n_commits       = 0
        commit_infos    = []
        root_tree_ids   = []
        new_commit_ids  = []                                    # the commits counted as new, in walk order
        visited_commits = set()
        if stop_at:
            visited_commits.add(stop_at)

        _p('scan', 'Analysing commit graph', '0 commits')
        t_graph_start = time.monotonic()

        # A linear history is one request per commit on this walk (each wave is the
        # previous wave's parents), and a whole-vault clone that is far behind pays
        # that N times before a single tree arrives. Past SWEEP_AFTER_WAVES missing
        # waves, list the store once and fetch everything not yet local in parallel
        # (the clone's own sweep); the walk then finds its objects on disk. Partial
        # clones never sweep: they must not hold what they do not track.
        waves      = 0
        swept      = bool(packed_ids)                           # a pack vault never sweeps bare/data/: the host has none
        swept_ids  = set(packed_ids)                            # fetched by the sweep or a pack: new to this clone, counted as such
        may_sweep  = include_blobs and (scope is None or not scope.is_partial())
        commit_wave = [commit_id]
        while commit_wave:
            unvisited = [c for c in commit_wave if c and c not in visited_commits]
            if not unvisited:
                break

            missing_cids = [c for c in unvisited if not obj_store.exists(c)]
            if missing_cids and may_sweep and not swept and waves >= SWEEP_AFTER_WAVES:
                swept     = True
                swept_ids = self._sweep_store(vault_id, obj_store, read_key, sg_dir, _p)
            if missing_cids:
                waves += 1
                _batch_save([f'bare/data/{c}' for c in missing_cids if not obj_store.exists(c)])
            new_cids = set(missing_cids) | {c for c in unvisited if c in swept_ids}

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
                    # New to this clone: downloaded, swept or unpacked by this pull, OR held as a bare
                    # commit object only (`sgit status` and the rewind guard fetch commit objects to
                    # count and classify; the pull is what brings their trees). The second case used
                    # to count as "0 new commits" and print no commit lines (reported 24 Oct).
                    if cid in new_cids or not (tree_id and obj_store.exists(tree_id)):
                        n_commits += 1
                        new_commit_ids.append(cid)
                        commit_infos.append((
                            cid[12:],
                            int(commit.timestamp_ms) if commit.timestamp_ms else 0,
                            str(commit.message_enc) if commit.message_enc else '',
                        ))
                    if scope is not None and scope.is_boundary(cid):
                        continue                               # shallow clone: history stops here by design
                    for pid in (list(commit.parents) if commit.parents else []):
                        pid_str = str(pid)
                        if pid_str in visited_commits:
                            continue
                        # A local commit whose root tree is local is complete below
                        # (every download path fetches commits with their trees). A
                        # commit object alone is not: `sgit status` and the rewind
                        # check fetch commit objects to count and classify, and the
                        # trees behind them must still be fetched here.
                        if (obj_store.exists(pid_str) and pid_str not in swept_ids         # swept: new, walk and list it
                                and self._commit_tree_local(vc, pid_str, read_key, obj_store)):
                            visited_commits.add(pid_str)
                        else:
                            next_wave.append(pid_str)
                except Exception:
                    pass

            _p('scan', 'Analysing commit graph',
               f'{n_commits} commit{"s" if n_commits != 1 else ""} · fetching trees...')
            commit_wave = next_wave

        # ── Phase 1b: the pack indexes' plan (dev pack 03 §5) ────────────────
        # On a pack vault with the advisory 'pack-indexes' feature, the new commits'
        # commit indexes name every object they introduce (A/M blobs, changed folders).
        # When every one of those is local (the packs just brought them), there is
        # nothing for the tree walk to find: Phases 2 and 3 walk nothing. Any doubt (a
        # commit without a usable index, an object the plan names that is not here)
        # means the walk, exactly as before. The new head's flat map comes from the
        # same indexes (no tree read but the root anchor), so the merge, the status
        # and the next commit find it cached.
        # What is new is base..head (every commit the branch gained since this clone's
        # head), not what this walk downloaded: status, the rewind guard and a pack
        # vault's sync_down bring commit objects (and, on a pack vault, their packs)
        # before this walk runs, and those commits used to show as "0 new commits" with
        # no lines (reported 24 Oct). Without a base (a first pull), what the walk found.
        between = (self._commits_between(vc, read_key, commit_id, stop_at, obj_store, cap=PLAN_COMMITS_MAX, full_ids=True)
                   if stop_at else [])
        plan_commits  = [b[0] for b in between] if between else list(new_commit_ids)
        planned_blobs = 0
        reader        = None
        plan          = None
        if plan_commits and len(plan_commits) < PLAN_COMMITS_MAX and include_blobs and (scope is None or not scope.is_partial()):
            reader = self._pack_index_reader(directory, read_key, packs)
        if reader is not None:
            plan = reader.fetch_plan(directory, plan_commits, read_key, _p)
            if plan is not None:
                absent = [o for o in sorted(plan['blobs'] | plan['trees']) if not obj_store.exists(o)]
                if absent:
                    _p('step', 'Index plan names objects this clone lacks (walking the trees instead)', f'{len(absent)} object(s)')
                    plan = None
            if plan is not None:
                planned_blobs = sum(1 for b in plan['blobs'] if b in swept_ids)
                _p('step', 'Fetch plan from the pack indexes',
                   f'{len(plan_commits)} commit(s): {len(plan["trees"])} tree(s), {len(plan["blobs"])} blob(s), all local; no tree walk')
                root_tree_ids = []                              # nothing to walk: every object the plan names is here

        # ── Phase 2: BFS tree walk (one batch per depth level) ───────────────
        n_trees    = 0
        graph_walk = Vault__Graph_Walk()

        def _on_batch_missing(ids):
            nonlocal n_trees
            n_trees += sum(1 for t in ids if not obj_store.exists(t) or t in swept_ids)
            missing  = [t for t in ids if not obj_store.exists(t)]
            if missing:
                _batch_save([f'bare/data/{t}' for t in missing])
            _p('scan', 'Analysing commit graph',
               f'{n_commits} commit{"s" if n_commits != 1 else ""} · {n_trees} trees · collecting blobs...')

        complete_trees = complete_trees or set()
        light          = Vault__Sub_Tree(crypto=self.crypto, obj_store=obj_store)

        def _load_tree(tid):
            if not obj_store.exists(tid):
                raise RuntimeError(f'tree {tid} not in obj_store')
            if tid in complete_trees:
                return Schema__Tree_Entries__Light(tree_id=tid, entries=[])      # complete below: no descent
            return Schema__Tree_Entries__Light(tree_id=tid, entries=light._load_tree_entries(tid, read_key))

        missing_blobs = []
        seen_blobs    = set()
        if scope is not None and scope.is_scoped():
            # Scoped clone: descend only into the held folders (and the spine
            # above them); blobs come from the same walk
            from sgit_ai.storage.Vault__Scoped_Tree import Vault__Scoped_Tree
            scoped  = Vault__Scoped_Tree(crypto=self.crypto, obj_store=obj_store)
            walked  = scoped.walk_fetch(root_tree_ids, read_key, scope, on_batch_missing=_on_batch_missing)
            seen_trees = walked['trees']
            if include_blobs:
                for bid in sorted(walked['small_blobs']):
                    if not obj_store.exists(bid):
                        seen_blobs.add(bid); missing_blobs.append((f'bare/data/{bid}', False))
                for bid in sorted(walked['large_blobs']):
                    if not obj_store.exists(bid):
                        seen_blobs.add(bid); missing_blobs.append((f'bare/data/{bid}', True))
            include_blobs = False                           # collected above
        else:
            seen_trees = graph_walk.walk_trees(root_tree_ids, _load_tree, _on_batch_missing)

        # ── Phase 3: collect missing blobs ───────────────────────────────────
        if include_blobs:
            for tid in seen_trees:
                if not obj_store.exists(tid) or tid in complete_trees:
                    continue
                try:
                    for entry in light._load_tree_entries(tid, read_key):        # the JSON, not the schema parser
                        blob_id = str(entry.get('blob_id') or '') or None
                        if blob_id and blob_id not in seen_blobs and (not obj_store.exists(blob_id) or blob_id in swept_ids):
                            seen_blobs.add(blob_id)
                            missing_blobs.append((f'bare/data/{blob_id}', bool(entry.get('large', False))))
                except Exception:
                    pass

        if plan is not None:
            n_trees = sum(1 for t in plan['trees'] if t in swept_ids)
        if reader is not None:
            self._seed_flat_from_indexes(reader, directory, commit_id, obj_store, read_key, _p)

        t_graph = time.monotonic() - t_graph_start

        if between:                                             # base..head is what is listed (see above)
            n_commits    = len(between)
            commit_infos = [(cid[12:], ts, msg) for cid, ts, msg in between[:500]]

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
                    'n_commits': n_commits, 'n_trees': n_trees, 'n_blobs': planned_blobs}

        # ── Pass 2: download blobs, batched and in parallel ──────────────────
        # One request per blob made a pull that is 12k files behind a 12k-request
        # affair (the agents' report on the comms vault). Small blobs now go through
        # batch_read, MAX_BATCH_OPS per request and BATCH_READ_WORKERS requests in
        # flight; blobs flagged large go through the presigned route, four at a time.
        # Each object is still verified before it is written, and each failure is
        # still classified per file.
        n_blobs    = len(missing_blobs)
        downloaded = [0]
        lock       = threading.Lock()
        t_dl_start = time.monotonic()
        _p('download', 'Downloading objects', f'0/{n_blobs}')

        def _advance(n: int) -> None:
            with lock:
                downloaded[0] += n
                _p('download', 'Downloading objects', f'{downloaded[0]}/{n_blobs}')

        def _small_chunk(fids: list) -> None:
            try:
                _batch_save([fid for fid in fids if not obj_store.exists(fid.replace('bare/data/', ''))])
            except Exception as e:                                 # a disk or decrypt error inside a chunk: recorded, never fatal
                if failures is not None:
                    for fid in fids:
                        failures.setdefault(fid, self._classify_chunk_exception(fid, e))
            _advance(len(fids))

        def _one_large(fid: str) -> None:
            try:
                if not obj_store.exists(fid.replace('bare/data/', '')):
                    data = self.api.read_large(vault_id, fid)              # presigned S3, or the read route on a server without S3
                    if data and _save(fid, data) and failures is not None:
                        failures.pop(fid, None)
            except Exception as e:
                if failures is not None:
                    failures[fid] = self._classify_chunk_exception(fid, e)
            _advance(1)

        small  = [fid for fid, is_large in missing_blobs if not is_large]
        large  = [fid for fid, is_large in missing_blobs if is_large]
        chunks = [small[i:i + MAX_BATCH_OPS] for i in range(0, len(small), MAX_BATCH_OPS)]
        if chunks:
            with ThreadPoolExecutor(max_workers=min(BATCH_READ_WORKERS, len(chunks))) as executor:
                for future in [executor.submit(_small_chunk, chunk) for chunk in chunks]:
                    future.result()
        if large:
            with ThreadPoolExecutor(max_workers=min(4, len(large))) as executor:
                for future in [executor.submit(_one_large, fid) for fid in large]:
                    future.result()

        t_download = time.monotonic() - t_dl_start
        return {'t_graph': t_graph, 't_download': t_download,
                'n_commits': n_commits, 'n_trees': n_trees, 'n_blobs': n_blobs}
