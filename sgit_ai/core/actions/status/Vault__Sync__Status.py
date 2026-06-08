"""Vault__Sync__Status — status command (Brief 22 — E5)."""
import os
from   sgit_ai.storage.Vault__Commit              import Vault__Commit
from   sgit_ai.core.Vault__Remote_Manager         import Vault__Remote_Manager
from   sgit_ai.storage.Vault__Storage                import Vault__Storage
from   sgit_ai.storage.Vault__Sub_Tree               import Vault__Sub_Tree
from   sgit_ai.core.Vault__Sync__Base             import Vault__Sync__Base


class Vault__Sync__Status(Vault__Sync__Base):

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

        old_entries = {}
        if parent_id:
            vault_commit_reader = Vault__Commit(crypto=self.crypto, pki=pki,
                                                object_store=obj_store, ref_manager=ref_manager)
            old_commit  = vault_commit_reader.load_commit(parent_id, read_key)
            sub_tree    = Vault__Sub_Tree(crypto=self.crypto, obj_store=obj_store)
            old_entries = sub_tree.flatten(str(old_commit.tree_id), read_key)

        new_file_map = self._scan_local_directory(directory)

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
            local_file = os.path.join(directory, path)
            with open(local_file, 'rb') as f:
                content = f.read()
            old_entry  = old_entries[path]
            old_hash   = old_entry.get('content_hash', '')
            file_hash  = self.crypto.content_hash(content)
            if old_hash and old_hash != file_hash:
                modified.append(path)
            elif not old_hash and len(content) != old_entry.get('size', -1):
                modified.append(path)

        clone_branch_id  = branch_id
        named_branch_id  = ''
        clone_head       = parent_id
        named_head       = None
        ahead            = 0
        behind           = 0
        push_status      = 'unknown'

        creator_branch_id = str(branch_meta.creator_branch) if branch_meta.creator_branch else ''
        named_meta = None
        if creator_branch_id:
            named_meta = branch_manager.get_branch_by_id(branch_index, creator_branch_id)
        if named_meta is None:
            named_meta = branch_manager.get_branch_by_name(branch_index, 'current')

        if named_meta:
            named_branch_id   = str(named_meta.branch_id)
            named_ref_file_id = f'bare/refs/{named_meta.head_ref_id}'
            try:
                remote_ref_data = self.api.read(c.vault_id, named_ref_file_id)
                if remote_ref_data:
                    ref_path = os.path.join(c.sg_dir, named_ref_file_id)
                    os.makedirs(os.path.dirname(ref_path), exist_ok=True)
                    with open(ref_path, 'wb') as f:
                        f.write(remote_ref_data)
            except Exception:
                pass
            named_head = ref_manager.read_ref(str(named_meta.head_ref_id), read_key)

            if clone_head and clone_head == named_head:
                push_status = 'up_to_date'
            elif clone_head and named_head:
                if not obj_store.exists(named_head):
                    named_walk = self._walk_commit_ids(obj_store, read_key, named_head)
                    clone_walk = self._walk_commit_ids(obj_store, read_key, clone_head)
                    local_only  = len(clone_walk - named_walk)
                    behind      = 1
                    ahead       = local_only
                    push_status = 'diverged'
                else:
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
                    clean=not added and not modified and not deleted,
                    clone_branch_id=clone_branch_id,
                    named_branch_id=named_branch_id,
                    clone_head=clone_head,
                    named_head=named_head,
                    ahead=ahead,
                    behind=behind,
                    push_status=push_status,
                    remote_configured=remote_configured,
                    never_pushed=never_pushed,
                    sparse=_sparse,
                    files_total=_files_total,
                    files_fetched=_files_fetched,
                    **merge_info)

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
            sub_tree   = Vault__Sub_Tree(crypto=self.crypto, obj_store=obj_store)
            old_entries = sub_tree.flatten(str(old_commit.tree_id), read_key)

        new_file_map = self._scan_local_directory(directory)
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
            with open(os.path.join(directory, path), 'rb') as f:
                content = f.read()
            old_entry = old_entries[path]
            old_hash  = old_entry.get('content_hash', '')
            file_hash = self.crypto.content_hash(content)
            if old_hash and old_hash != file_hash:
                modified.append(path)
            elif not old_hash and len(content) != old_entry.get('size', -1):
                modified.append(path)

        behind = self._count_behind_remote(c, named_meta, named_head, read_key,
                                            obj_store, ref_manager)

        return dict(added=added, modified=modified, deleted=deleted,
                    clean=not added and not modified and not deleted,
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
            ref_path = os.path.join(c.sg_dir, named_ref_file_id)
            os.makedirs(os.path.dirname(ref_path), exist_ok=True)
            with open(ref_path, 'wb') as f:
                f.write(remote_ref_data)
            remote_head = ref_manager.read_ref(str(named_meta.head_ref_id), read_key)
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
