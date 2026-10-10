"""Vault__Sync__Status — status command (Brief 22 — E5)."""
import os
from   sgit_ai.storage.Vault__Commit              import Vault__Commit
from   sgit_ai.core.Vault__Remote_Manager         import Vault__Remote_Manager
from   sgit_ai.storage.Vault__Storage                import Vault__Storage
from   sgit_ai.storage.Vault__Sub_Tree               import Vault__Sub_Tree
from   sgit_ai.core.Vault__Sync__Base             import Vault__Sync__Base
from   sgit_ai.core.scope.Vault__Scope            import Vault__Scope
from   sgit_ai.storage.Vault__Scoped_Tree         import Vault__Scoped_Tree
from   osbot_utils.type_safe.primitives.core.Safe_UInt import Safe_UInt


class Vault__Sync__Status(Vault__Sync__Base):
    commit_fetch_limit : Safe_UInt = 50     # new remote commits `status` will fetch to count behind exactly

    def status(self, directory: str) -> dict:
        c = self._init_components(directory)
        read_key       = c.read_key
        storage        = c.storage
        pki            = c.pki
        obj_store      = c.obj_store
        ref_manager    = c.ref_manager
        branch_manager = c.branch_manager

        local_config = self._read_local_config(directory, storage)

        from sgit_ai.safe_types.Enum__Local_Config_Mode import Enum__Local_Config_Mode
        if local_config.mode == Enum__Local_Config_Mode.READ_ONLY:
            return self._status_read_only(directory, c, local_config)

        branch_id    = str(local_config.my_branch_id)

        index_id = c.branch_index_file_id
        _token_path        = os.path.join(directory, '.sg_vault', 'local', 'token')
        _base_url_path     = os.path.join(directory, '.sg_vault', 'local', 'base_url')
        _has_remotes       = bool(Vault__Remote_Manager(storage=Vault__Storage()).list_remotes(directory))
        _remote_configured = os.path.isfile(_token_path) or os.path.isfile(_base_url_path) or _has_remotes
        if not index_id:
            return dict(added=[], modified=[], deleted=[], clean=True,
                        clone_branch_id='', named_branch_id='',
                        clone_head=None, named_head=None,
                        ahead=0, behind=0, push_status='unknown',
                        remote_configured=_remote_configured,
                        never_pushed=not _remote_configured)
        branch_index = branch_manager.load_branch_index(directory, index_id, read_key)
        branch_meta  = branch_manager.get_branch_by_id(branch_index, branch_id)
        if not branch_meta:
            return dict(added=[], modified=[], deleted=[], clean=True,
                        clone_branch_id='', named_branch_id='',
                        clone_head=None, named_head=None,
                        ahead=0, behind=0, push_status='unknown',
                        remote_configured=_remote_configured,
                        never_pushed=not _remote_configured)

        ref_id    = str(branch_meta.head_ref_id)
        parent_id = ref_manager.read_ref(ref_id, read_key)
        scope     = Vault__Scope().from_local_config(local_config)

        old_entries = {}
        if parent_id:
            vault_commit_reader = Vault__Commit(crypto=self.crypto, pki=pki,
                                                object_store=obj_store, ref_manager=ref_manager)
            old_commit  = vault_commit_reader.load_commit(parent_id, read_key)
            if scope.is_scoped():                     # only the held folders are on disk
                old_entries, _ = Vault__Scoped_Tree(crypto=self.crypto, obj_store=obj_store).flatten(
                    str(old_commit.tree_id), read_key, scope)
            else:
                sub_tree    = Vault__Sub_Tree(crypto=self.crypto, obj_store=obj_store)
                old_entries = sub_tree.flatten(str(old_commit.tree_id), read_key)

        linked       = []
        unreadable   = []                                      # kept as committed, never "deleted" (review eed8084 B2)
        new_file_map = self._scan_local_directory(directory, linked_out=linked, unreadable_out=unreadable)

        old_paths = set(old_entries.keys())
        new_paths = set(new_file_map.keys())

        added   = sorted(new_paths - old_paths)
        deleted = sorted(old_paths - new_paths)

        _sparse          = False
        _files_total     = 0
        _files_fetched   = 0
        _config_path = storage.local_config_path(directory)
        if os.path.isfile(_config_path):
            if self._read_local_config(directory, storage).sparse:
                _sparse        = True
                _files_total   = len(old_entries)
                _files_fetched = sum(1 for e in old_entries.values()
                                     if obj_store.exists(e.get('blob_id', '')))
                deleted = [p for p in deleted
                           if obj_store.exists(old_entries[p].get('blob_id', ''))]

        modified = []
        for path in sorted(old_paths & new_paths):
            old_entry  = old_entries[path]
            old_hash   = old_entry.get('content_hash', '')
            file_hash  = new_file_map[path].get('content_hash', '')            # the scan's hash; never re-read (a link is never followed)
            if old_hash and old_hash != file_hash:
                modified.append(path)
            elif not old_hash and new_file_map[path].get('size') != old_entry.get('size', -1):
                modified.append(path)

        clone_branch_id  = branch_id
        named_branch_id  = ''
        clone_head       = parent_id
        named_head       = None
        ahead            = 0
        behind           = 0
        behind_lower_bound = False
        push_status      = 'unknown'
        rewound_from     = ''
        baseline_error   = ''

        named_meta = branch_manager.tracked_named_branch(branch_index, str(branch_meta.branch_id))

        if named_meta:
            named_branch_id   = str(named_meta.branch_id)
            named_ref_file_id = f'bare/refs/{named_meta.head_ref_id}'
            try:                                               # the record pull refuses on, checked every time
                self._read_remote_baseline(directory, storage, str(named_meta.head_ref_id))
            except Exception as error:
                baseline_error = str(error)
            # What this clone last accepted from the remote (its last push or pull):
            # every local commit not reachable from it is unpushed, whatever the
            # remote has done since — so "ahead" never depends on the network.
            last_known_named_head = ref_manager.read_ref(str(named_meta.head_ref_id), read_key)
            named_head            = last_known_named_head
            remote_ref_data       = None
            try:
                remote_ref_data = self.api.read(c.vault_id, named_ref_file_id)
                if remote_ref_data:
                    parsed = self._parse_ref(remote_ref_data, read_key)
                    if not parsed:                               # reachable but unreadable: never "in sync" (F3)
                        baseline_error = self._unreadable_ref_message(str(named_meta.head_ref_id))
                    named_head = parsed or named_head
            except Exception:
                pass
            # The local copy of the named ref is never advanced by status (below).

            if clone_head and clone_head == named_head:
                push_status = 'up_to_date'
            elif clone_head and named_head:
                # The remote may have moved: make sure its history is local before
                # counting. _fetch_commit_chain walks from the remote head, fetching
                # the commit objects that are absent (small: one per commit, no
                # trees or blobs), and says whether the chain joins what we have.
                # Without this the walk from a missing head was empty, every local
                # commit counted as "ahead", and a fresh clone one commit behind
                # reported "200 ahead, 1 behind — push".
                try:                                           # '' on a branch never fetched
                    accepted_head = self._read_remote_baseline(directory, storage, str(named_meta.head_ref_id))
                except Exception as error:                     # unreadable or missing record: pull refuses on it,
                    accepted_head  = ''                        # and status says so instead of "in sync" (0a0707d F8)
                    baseline_error = str(error)
                fetched, connected = self._fetch_commit_chain(c, obj_store, read_key, named_head,
                                                              limit=int(self.commit_fetch_limit),
                                                              boundaries=set(scope.boundary_ids()),
                                                              known={last_known_named_head, clone_head, accepted_head})
                # The named branch only moves forward. A remote head that does not
                # descend from the last one this clone fetched is a rewind (rollback,
                # rewritten history, or a host replaying an old ref): report it and
                # keep the local ref where it was, so `ahead` stays honest.
                from sgit_ai.core.actions.pull.Vault__Ref_Guard import Vault__Ref_Guard, REWOUND
                verdict = Vault__Ref_Guard(crypto=self.crypto).classify(
                    c, read_key, named_head, accepted_head, connected,
                    getattr(self, '_chain_reached_known', False), set(scope.boundary_ids())) if accepted_head else 'forward'
                if verdict == REWOUND:
                    rewound_from = accepted_head
                    connected    = False                                   # never advance the local ref onto a rewind
                # Neither the local named ref nor the baseline moves here: status observes, and
                # only a pull's verify-then-accept writes them. Writing the server's head into
                # the local ref let the next pull or switch take it as already held and skip
                # the signature policy (reviews B2, d3b8eef N3).
                if rewound_from:
                    ahead              = self._count_unique_commits(obj_store, read_key,
                                                                    clone_head, last_known_named_head)
                    behind             = 0
                    behind_lower_bound = False
                    push_status        = 'rewound'
                elif not connected:                            # offline, or more new commits than the limit: do not invent
                    ahead              = self._count_unique_commits(obj_store, read_key,
                                                                    clone_head, last_known_named_head)
                    behind             = max(fetched, 1)
                    behind_lower_bound = True
                    push_status        = 'diverged' if ahead else 'behind'
                if not behind_lower_bound and not rewound_from:
                    ahead  = self._count_unique_commits(obj_store, read_key, clone_head, named_head)
                    behind = self._count_unique_commits(obj_store, read_key, named_head, clone_head)
                    if ahead > 0 and behind == 0:
                        push_status = 'ahead'
                    elif ahead == 0 and behind > 0:
                        push_status = 'behind'
                    else:                              # ahead > 0 and behind > 0
                        push_status = 'diverged'
            elif clone_head and not named_head:
                ahead       = self._count_commits_from(obj_store, read_key, clone_head)
                push_status = 'ahead'
            elif not clone_head and named_head:
                behind      = self._count_commits_from(obj_store, read_key, named_head)
                push_status = 'behind'

        if baseline_error:
            push_status = 'baseline_unreadable'
        token_path        = os.path.join(directory, '.sg_vault', 'local', 'token')
        base_url_path     = os.path.join(directory, '.sg_vault', 'local', 'base_url')
        has_remotes       = bool(Vault__Remote_Manager(storage=storage).list_remotes(directory))
        remote_configured = os.path.isfile(token_path) or os.path.isfile(base_url_path) or has_remotes
        never_pushed      = not remote_configured and not named_head

        from sgit_ai.core.actions.merge.Vault__Merge__State import Vault__Merge__State
        ms_mgr        = Vault__Merge__State()
        merge_state   = ms_mgr.read(directory) if ms_mgr.exists(directory) else None
        merge_info    = {}
        if merge_state:
            merge_info = dict(
                merge_in_progress   = True,
                merge_ours          = str(merge_state.ours_commit_id   or ''),
                merge_theirs        = str(merge_state.theirs_commit_id or ''),
                merge_lca           = str(merge_state.lca_id           or ''),
                merge_conflicts     = [str(p) for p in (merge_state.conflict_paths or [])],
                merge_resolved      = [str(p) for p in (merge_state.resolved_paths  or [])],
            )
        else:
            merge_info = dict(merge_in_progress=False)

        return dict(added=added, modified=modified, deleted=deleted,
                    clean=not added and not modified and not deleted and not unreadable,
                    clone_branch_id=clone_branch_id,
                    named_branch_id=named_branch_id,
                    clone_head=clone_head,
                    named_head=named_head,
                    ahead=ahead,
                    behind=behind,
                    behind_lower_bound=behind_lower_bound,
                    push_status=push_status,
                    rewound_from=rewound_from,
                    baseline_error=baseline_error,
                    remote_configured=remote_configured,
                    never_pushed=never_pushed,
                    sparse=_sparse,
                    files_total=_files_total,
                    files_fetched=_files_fetched,
                    linked=linked, unreadable=sorted(unreadable),
                    **merge_info)

    def _parse_ref(self, ref_data: bytes, read_key: bytes) -> str:
        """The commit id inside an encrypted ref payload, without touching disk."""
        import json
        try:
            return json.loads(self.crypto.decrypt(read_key, ref_data)).get('commit_id') or ''
        except Exception:
            return ''

    def _fetch_commit_chain(self, c, obj_store, read_key: bytes, head: str, limit: int = 50,
                            boundaries: set = None, known: set = None) -> tuple:
        """Walk the commit graph from head, downloading every commit object that is
        absent locally (verify-before-write like every other download path), and
        report (fetched, connected). `connected` is True only when every commit
        reachable from head is now local — a head whose parents are missing would
        give a short count. At most `limit` commits are fetched (one small object
        each, one round trip per commit on a linear chain); past that, or offline,
        connected is False and the caller reports a lower bound instead of a number."""
        from sgit_ai.crypto.PKI__Crypto             import PKI__Crypto
        from sgit_ai.storage.Vault__Ref_Manager      import Vault__Ref_Manager
        from sgit_ai.storage.Vault__Verified_Write   import Vault__Verified_Write
        if not head:
            return 0, False
        writer    = Vault__Verified_Write(crypto=self.crypto)
        vc        = Vault__Commit(crypto=self.crypto, pki=PKI__Crypto(),
                                  object_store=obj_store, ref_manager=Vault__Ref_Manager())
        # The walk from the remote head stops at a commit whose history is known
        # complete locally: the last remote head this clone fully fetched and the
        # clone's own head (local commits sit on fetched history), plus shallow
        # boundaries (never expanded, by design). So an up-to-date clone does no
        # walk, a clone N behind opens exactly N commits, and a head left local
        # by an earlier truncated fetch (limit hit) is still expanded down to
        # its missing parents instead of being taken for a complete chain.
        known     = {str(k) for k in (known or set()) if k and obj_store.exists(str(k))}
        visited   = set()
        queue     = [head]
        fetched   = 0
        connected = True
        self._chain_reached_known = (head in known)              # read by the caller after the walk
        while queue:
            missing   = []
            to_expand = []
            for cid in queue:
                if cid in known:
                    self._chain_reached_known = True
                if cid in visited or cid in missing or cid in to_expand or cid in known:
                    continue
                (to_expand if obj_store.exists(cid) else missing).append(cid)
            room = max(limit - fetched, 0)
            if room < len(missing):
                connected = False
                missing   = missing[:room]
            if missing:
                try:
                    data = self.api.batch_read(c.vault_id, [f'bare/data/{cid}' for cid in missing])
                except Exception:
                    return fetched, False                      # offline: the caller falls back honestly
                for fid, blob in data.items():
                    if blob and writer.save(c.sg_dir, fid, blob, read_key=read_key) == writer.VERIFIED:
                        fetched += 1
            next_queue = []
            for cid in to_expand + missing:
                visited.add(cid)
                if not obj_store.exists(cid):
                    connected = False                          # absent on the host too
                    continue
                try:
                    commit = vc.load_commit(cid, read_key)
                except Exception:
                    connected = False
                    continue
                if boundaries and cid in boundaries:
                    continue
                for pid in (commit.parents or []):
                    pid = str(pid)
                    if pid in known:
                        self._chain_reached_known = True       # the new history joins what this clone already has
                    if pid and pid not in visited and pid not in next_queue and pid not in known:
                        next_queue.append(pid)
            queue = next_queue
        return fetched, connected

    def _status_read_only(self, directory: str, c, local_config) -> dict:
        """Status for a read-only clone (architect contract §5.4).

        HEAD is the named-branch ref; there is no clone branch. Reports working-tree
        changes against the named-branch HEAD. clone_branch_id='', clone_head=None,
        ahead=0, push_status='read_only', read_only=True. behind is counted against
        the remote named HEAD with a 3-second timeout, falling back to '?' on error.
        """
        read_key       = c.read_key
        obj_store      = c.obj_store
        ref_manager    = c.ref_manager
        branch_manager = c.branch_manager
        pki            = c.pki

        index_id = c.branch_index_file_id
        if not index_id:
            return self._empty_read_only_status(local_config)

        branch_index = branch_manager.load_branch_index(directory, index_id, read_key)
        branch_name  = self._tracked_branch_name(directory)
        named_meta   = self._resolve_working_branch(local_config, branch_index,
                                                    branch_manager, branch_name)
        if not named_meta:
            return self._empty_read_only_status(local_config)

        named_branch_id = str(named_meta.branch_id)
        named_head      = ref_manager.read_ref(str(named_meta.head_ref_id), read_key)

        # Working-tree diff against the named-branch HEAD tree.
        old_entries = {}
        if named_head:
            vc         = Vault__Commit(crypto=self.crypto, pki=pki,
                                       object_store=obj_store, ref_manager=ref_manager)
            old_commit = vc.load_commit(named_head, read_key)
            ro_scope   = Vault__Scope().from_local_config(local_config)
            if ro_scope.is_scoped():
                old_entries, _ = Vault__Scoped_Tree(crypto=self.crypto, obj_store=obj_store).flatten(
                    str(old_commit.tree_id), read_key, ro_scope)
            else:
                sub_tree    = Vault__Sub_Tree(crypto=self.crypto, obj_store=obj_store)
                old_entries = sub_tree.flatten(str(old_commit.tree_id), read_key)

        linked       = []
        unreadable   = []                                      # kept as committed, never "deleted" (review eed8084 B2)
        new_file_map = self._scan_local_directory(directory, linked_out=linked, unreadable_out=unreadable)
        old_paths    = set(old_entries.keys())
        new_paths    = set(new_file_map.keys())

        added   = sorted(new_paths - old_paths)
        deleted = sorted(old_paths - new_paths)

        _sparse        = bool(local_config.sparse)
        _files_total   = 0
        _files_fetched = 0
        if _sparse:
            _files_total   = len(old_entries)
            _files_fetched = sum(1 for e in old_entries.values()
                                 if obj_store.exists(e.get('blob_id', '')))
            deleted = [p for p in deleted
                       if obj_store.exists(old_entries[p].get('blob_id', ''))]

        modified = []
        for path in sorted(old_paths & new_paths):
            old_entry = old_entries[path]
            old_hash  = old_entry.get('content_hash', '')
            file_hash = new_file_map[path].get('content_hash', '')             # the scan's hash; never re-read (a link is never followed)
            if old_hash and old_hash != file_hash:
                modified.append(path)
            elif not old_hash and new_file_map[path].get('size') != old_entry.get('size', -1):
                modified.append(path)

        behind = self._count_behind_remote(c, named_meta, named_head, read_key,
                                            obj_store, ref_manager)

        return dict(added=added, modified=modified, deleted=deleted, linked=linked, unreadable=sorted(unreadable),
                    clean=not added and not modified and not deleted and not unreadable,
                    clone_branch_id='',
                    named_branch_id=named_branch_id,
                    clone_head=None,
                    named_head=named_head,
                    ahead=0,
                    behind=behind,
                    push_status='read_only',
                    remote_configured=True,
                    never_pushed=False,
                    read_only=True,
                    sparse=_sparse,
                    files_total=_files_total,
                    files_fetched=_files_fetched,
                    merge_in_progress=False)

    def _empty_read_only_status(self, local_config) -> dict:
        return dict(added=[], modified=[], deleted=[], clean=True,
                    clone_branch_id='', named_branch_id='',
                    clone_head=None, named_head=None,
                    ahead=0, behind=0, push_status='read_only',
                    remote_configured=True, never_pushed=False,
                    read_only=True, sparse=bool(local_config.sparse),
                    files_total=0, files_fetched=0,
                    merge_in_progress=False)

    def _count_behind_remote(self, c, named_meta, named_head, read_key,
                             obj_store, ref_manager) -> object:
        """Count commits the remote named HEAD has that the local cache does not.

        Q4: 3-second timeout; returns the literal '?' on timeout/error. Compares the
        local cached named HEAD against the freshly-fetched remote named HEAD.
        """
        import socket
        named_ref_file_id = f'bare/refs/{named_meta.head_ref_id}'
        prev_timeout      = socket.getdefaulttimeout()
        try:
            socket.setdefaulttimeout(3)
            remote_ref_data = self.api.read(c.vault_id, named_ref_file_id)
            if not remote_ref_data:
                return 0
            remote_head = self._parse_ref(remote_ref_data, read_key)     # in memory: status never writes refs (N3)
            if not remote_head or remote_head == named_head:
                return 0
            if not obj_store.exists(remote_head):
                # Remote advanced to a commit we have never fetched — we cannot walk
                # it locally; report at least one commit behind (consistent with the
                # full-clone 'diverged' sentinel doctrine).
                return 1
            return self._count_unique_commits(obj_store, read_key, remote_head, named_head)
        except Exception:
            return '?'
        finally:
            socket.setdefaulttimeout(prev_timeout)
