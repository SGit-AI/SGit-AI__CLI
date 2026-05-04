"""Vault__Sync__Status — status command (Brief 22 — E5)."""
import os
from   sgit_ai.storage.Vault__Commit              import Vault__Commit
from   sgit_ai.sync.Vault__Remote_Manager         import Vault__Remote_Manager
from   sgit_ai.storage.Vault__Storage                import Vault__Storage
from   sgit_ai.storage.Vault__Sub_Tree               import Vault__Sub_Tree
from   sgit_ai.sync.Vault__Sync__Base             import Vault__Sync__Base


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
                    files_fetched=_files_fetched)
