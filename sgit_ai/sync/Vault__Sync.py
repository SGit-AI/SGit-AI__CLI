import json
import os
import secrets
import string
import sys
import time
from   urllib.request                                import urlopen
from   datetime                                      import datetime, timezone
from   osbot_utils.type_safe.Type_Safe               import Type_Safe
from   sgit_ai.crypto.Vault__Crypto              import Vault__Crypto
from   sgit_ai.crypto.PKI__Crypto                import PKI__Crypto
from   sgit_ai.crypto.Vault__Key_Manager         import Vault__Key_Manager
from   sgit_ai.api.Vault__API                    import Vault__API, LARGE_BLOB_THRESHOLD
from   sgit_ai.sync.Vault__Storage               import Vault__Storage
from   sgit_ai.sync.Vault__Branch_Manager        import Vault__Branch_Manager
from   sgit_ai.sync.Vault__Batch                 import Vault__Batch
from   sgit_ai.sync.Vault__Fetch                 import Vault__Fetch
from   sgit_ai.sync.Vault__Merge                 import Vault__Merge
from   sgit_ai.sync.Vault__Change_Pack           import Vault__Change_Pack
from   sgit_ai.sync.Vault__GC                   import Vault__GC
from   sgit_ai.sync.Vault__Remote_Manager        import Vault__Remote_Manager
from   sgit_ai.sync.Vault__Sub_Tree              import Vault__Sub_Tree
from   sgit_ai.objects.Vault__Object_Store       import Vault__Object_Store
from   sgit_ai.objects.Vault__Ref_Manager        import Vault__Ref_Manager
from   sgit_ai.objects.Vault__Commit             import Vault__Commit
from   sgit_ai.schemas.Schema__Object_Commit     import Schema__Object_Commit
from   sgit_ai.schemas.Schema__Object_Tree       import Schema__Object_Tree
from   sgit_ai.schemas.Schema__Object_Tree_Entry import Schema__Object_Tree_Entry
from   sgit_ai.schemas.Schema__Object_Ref        import Schema__Object_Ref
from   sgit_ai.schemas.Schema__Branch_Index      import Schema__Branch_Index
from   sgit_ai.schemas.Schema__Local_Config      import Schema__Local_Config
from   sgit_ai.sync.Vault__Components             import Vault__Components
from   sgit_ai.sync.Vault__Ignore                import Vault__Ignore
from   sgit_ai.sync.Vault__Storage               import SG_VAULT_DIR


class Vault__Sync(Type_Safe):
    crypto       : Vault__Crypto
    api          : Vault__API

    def generate_vault_key(self) -> str:
        alphabet   = string.ascii_lowercase + string.digits
        passphrase = ''.join(secrets.choice(alphabet) for _ in range(24))
        vault_id   = ''.join(secrets.choice(alphabet) for _ in range(8))
        return f'{passphrase}:{vault_id}'

    def init(self, directory: str, vault_key: str = None,
             allow_nonempty: bool = False, token: str = None) -> dict:
        from sgit_ai.transfer.Simple_Token import Simple_Token
        if os.path.exists(directory):
            entries = [e for e in os.listdir(directory) if e != SG_VAULT_DIR]
            if entries and not allow_nonempty:
                raise RuntimeError(f'Directory is not empty: {directory}')
        os.makedirs(directory, exist_ok=True)

        # Simple token path: token arg takes precedence over vault_key
        simple_token_mode = False
        if token and Simple_Token.is_simple_token(token):
            simple_token_mode = True
            vault_key         = token
        elif vault_key and Simple_Token.is_simple_token(vault_key):
            simple_token_mode = True
            token             = vault_key

        if not vault_key:
            vault_key = self.generate_vault_key()

        if simple_token_mode:
            keys = self.crypto.derive_keys_from_simple_token(vault_key)
        else:
            keys = self.crypto.derive_keys_from_vault_key(vault_key)
        vault_id   = keys['vault_id']
        read_key   = keys['read_key_bytes']

        storage = Vault__Storage()
        sg_dir  = storage.create_bare_structure(directory)

        pki         = PKI__Crypto()
        key_manager = Vault__Key_Manager(vault_path=sg_dir, crypto=self.crypto, pki=pki)
        ref_manager = Vault__Ref_Manager(vault_path=sg_dir, crypto=self.crypto)
        obj_store   = Vault__Object_Store(vault_path=sg_dir, crypto=self.crypto)

        branch_manager = Vault__Branch_Manager(vault_path    = sg_dir,
                                               crypto        = self.crypto,
                                               key_manager   = key_manager,
                                               ref_manager   = ref_manager,
                                               storage       = storage)

        timestamp_ms   = int(time.time() * 1000)
        clone_ref_id   = 'ref-pid-snw-' + self.crypto.derive_branch_ref_file_id(
                             read_key, vault_id, 'local')
        named_branch   = branch_manager.create_named_branch(directory, 'current', read_key,
                                                             head_ref_id=keys['ref_file_id'],
                                                             timestamp_ms=timestamp_ms)
        clone_branch   = branch_manager.create_clone_branch(directory, 'local', read_key,
                                                             head_ref_id=clone_ref_id,
                                                             creator_branch_id=str(named_branch.branch_id),
                                                             timestamp_ms=timestamp_ms)

        branch_index = Schema__Branch_Index(schema   = 'branch_index_v1',
                                            branches = [named_branch, clone_branch])
        branch_manager.save_branch_index(directory, branch_index, read_key,
                                         index_file_id=keys['branch_index_file_id'])

        clone_private_key = key_manager.load_private_key_locally(
            str(clone_branch.public_key_id), storage.local_dir(directory))

        vault_commit = Vault__Commit(crypto=self.crypto, pki=pki,
                                     object_store=obj_store, ref_manager=ref_manager)

        # Create empty root tree and store it
        sub_tree     = Vault__Sub_Tree(crypto=self.crypto, obj_store=obj_store)
        empty_tree   = Schema__Object_Tree(schema='tree_v1')
        root_tree_id = sub_tree._store_tree(empty_tree, read_key)

        commit_id = vault_commit.create_commit(read_key      = read_key,
                                               tree_id       = root_tree_id,
                                               message       = 'init',
                                               branch_id     = str(clone_branch.branch_id),
                                               signing_key   = clone_private_key,
                                               timestamp_ms  = timestamp_ms)

        ref_manager.write_ref(str(named_branch.head_ref_id), commit_id, read_key)
        ref_manager.write_ref(str(clone_branch.head_ref_id), commit_id, read_key)

        local_config_data = dict(Schema__Local_Config(my_branch_id=str(clone_branch.branch_id)).json())
        if simple_token_mode:
            local_config_data['mode']       = 'simple_token'
            local_config_data['edit_token'] = vault_key
        config_path  = storage.local_config_path(directory)
        with open(config_path, 'w') as f:
            json.dump(local_config_data, f, indent=2)

        with open(storage.vault_key_path(directory), 'w') as f:
            f.write(vault_key)

        return dict(directory    = directory,
                    vault_key    = vault_key,
                    vault_id     = vault_id,
                    branch_id    = str(clone_branch.branch_id),
                    named_branch = str(named_branch.branch_id),
                    commit_id    = commit_id)

    def commit(self, directory: str, message: str = '') -> dict:
        c = self._init_components(directory)
        read_key       = c.read_key
        storage        = c.storage
        pki            = c.pki
        obj_store      = c.obj_store
        ref_manager    = c.ref_manager
        key_manager    = c.key_manager
        branch_manager = c.branch_manager

        local_config = self._read_local_config(directory, storage)
        branch_id    = str(local_config.my_branch_id)

        index_id = c.branch_index_file_id
        if not index_id:
            raise RuntimeError('No branch index found — is this a v2 vault?')
        branch_index = branch_manager.load_branch_index(directory, index_id, read_key)
        branch_meta  = branch_manager.get_branch_by_id(branch_index, branch_id)
        if not branch_meta:
            raise RuntimeError(f'Branch not found: {branch_id}')

        ref_id     = str(branch_meta.head_ref_id)
        parent_id  = ref_manager.read_ref(ref_id, read_key)

        sub_tree = Vault__Sub_Tree(crypto=self.crypto, obj_store=obj_store)

        # Flatten old tree for blob reuse and diff generation
        old_flat_entries = {}
        if parent_id:
            vault_commit_reader = Vault__Commit(crypto=self.crypto, pki=pki,
                                                object_store=obj_store, ref_manager=ref_manager)
            old_commit  = vault_commit_reader.load_commit(parent_id, read_key)
            old_flat_entries = sub_tree.flatten(str(old_commit.tree_id), read_key)

        new_file_map = self._scan_local_directory(directory)

        # Build sub-trees bottom-up (one tree per directory level)
        root_tree_id = sub_tree.build(directory, new_file_map, read_key,
                                       old_flat_entries=old_flat_entries)

        signing_key = None
        try:
            signing_key = key_manager.load_private_key_locally(
                str(branch_meta.public_key_id), storage.local_dir(directory))
        except (FileNotFoundError, Exception):
            pass

        vault_commit = Vault__Commit(crypto=self.crypto, pki=pki,
                                     object_store=obj_store, ref_manager=ref_manager)

        auto_msg = message or self._generate_commit_message(old_flat_entries, new_file_map)
        commit_id = vault_commit.create_commit(tree_id     = root_tree_id,
                                               read_key    = read_key,
                                               parent_ids  = [parent_id] if parent_id else [],
                                               message     = auto_msg,
                                               branch_id   = branch_id,
                                               signing_key = signing_key)

        ref_manager.write_ref(ref_id, commit_id, read_key)

        old_paths     = set(old_flat_entries.keys())
        new_paths     = set(new_file_map.keys())
        files_changed = len(new_paths - old_paths) + len(old_paths - new_paths)

        return dict(commit_id     = commit_id,
                    branch_id     = branch_id,
                    message       = auto_msg,
                    files_changed = files_changed)

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
            old_commit = vault_commit_reader.load_commit(parent_id, read_key)
            sub_tree   = Vault__Sub_Tree(crypto=self.crypto, obj_store=obj_store)
            old_entries = sub_tree.flatten(str(old_commit.tree_id), read_key)

        new_file_map = self._scan_local_directory(directory)

        old_paths = set(old_entries.keys())
        new_paths = set(new_file_map.keys())

        added   = sorted(new_paths - old_paths)
        deleted = sorted(old_paths - new_paths)
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

        # --- push-tracking: compare clone branch HEAD vs named branch HEAD ---
        clone_branch_id  = branch_id
        named_branch_id  = ''
        clone_head       = parent_id        # HEAD of the clone branch
        named_head       = None
        ahead            = 0
        behind           = 0
        push_status      = 'unknown'

        # Find the named branch this clone tracks (via creator_branch on clone_meta)
        creator_branch_id = str(branch_meta.creator_branch) if branch_meta.creator_branch else ''
        named_meta = None
        if creator_branch_id:
            named_meta = branch_manager.get_branch_by_id(branch_index, creator_branch_id)
        if named_meta is None:
            # Fallback: look for the branch named 'current'
            named_meta = branch_manager.get_branch_by_name(branch_index, 'current')

        if named_meta:
            named_branch_id = str(named_meta.branch_id)
            named_head      = ref_manager.read_ref(str(named_meta.head_ref_id), read_key)

            if clone_head and clone_head == named_head:
                push_status = 'up_to_date'
            elif clone_head and named_head:
                # Walk commit chains to count ahead / behind
                ahead  = self._count_unique_commits(obj_store, read_key, clone_head, named_head)
                behind = self._count_unique_commits(obj_store, read_key, named_head, clone_head)
                if ahead > 0 and behind == 0:
                    push_status = 'ahead'
                elif ahead == 0 and behind > 0:
                    push_status = 'behind'
                elif ahead > 0 and behind > 0:
                    push_status = 'diverged'
                else:
                    push_status = 'up_to_date'
            elif clone_head and not named_head:
                ahead       = self._count_commits_from(obj_store, read_key, clone_head)
                push_status = 'ahead'
            elif not clone_head and named_head:
                behind      = self._count_commits_from(obj_store, read_key, named_head)
                push_status = 'behind'

        # Determine whether a remote has been configured (token or base_url stored, or named remote added)
        token_path        = os.path.join(directory, '.sg_vault', 'local', 'token')
        base_url_path     = os.path.join(directory, '.sg_vault', 'local', 'base_url')
        has_remotes       = bool(Vault__Remote_Manager(storage=storage).list_remotes(directory))
        remote_configured = os.path.isfile(token_path) or os.path.isfile(base_url_path) or has_remotes

        # "never pushed" = no remote token/config AND the vault has never been synced
        # (named branch HEAD is absent — it only gets set after the first successful push)
        never_pushed = not remote_configured and not named_head

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
                    never_pushed=never_pushed)

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

        # Fetch remote named ref and any missing objects
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

        clone_short = (clone_commit_id or '')[:12]
        named_short = (named_commit_id or '')[:12]
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

        # Fetch any missing objects reachable from the remote commit
        _p('step', 'Downloading missing objects')
        self._fetch_missing_objects(vault_id, named_commit_id, obj_store, read_key, c.sg_dir, _p)

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
        self._checkout_flat_map(directory, merged_map, obj_store, read_key)
        self._remove_deleted_flat(directory, ours_map, merged_map)

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

        return dict(status    = 'merged',
                    commit_id = merge_commit_id,
                    added     = merge_result['added'],
                    modified  = merge_result['modified'],
                    deleted   = merge_result['deleted'],
                    conflicts = [])

    def push(self, directory: str, message: str = '', force: bool = False,
             use_batch: bool = True, branch_only: bool = False,
             on_progress: callable = None) -> dict:
        """Push local clone branch state to the named branch (or clone branch only).

        Workflow:
        0. Drain any pending change packs (GC)
        1. Check for uncommitted changes — reject if dirty
        2. Pull first (fetch-first pattern) — merge remote changes
        3. Snapshot the named ref hash for write-if-match CAS
        4. Compute delta between named branch tree and clone branch tree
        5. Build batch operations (data objects + commit chain + ref update)
        6. Execute via batch API (with CAS on ref) or individually as fallback
        7. Update local named branch ref on success

        If branch_only=True, uploads clone branch objects and ref without
        touching the named branch. Used for sharing work-in-progress.
        """
        _p = on_progress or (lambda *a, **k: None)
        self._auto_gc_drain(directory)

        c = self._init_components(directory)
        vault_id       = c.vault_id
        read_key       = c.read_key
        write_key      = c.write_key
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
            raise RuntimeError('No branch index found — is this a v2 vault?')
        branch_index = branch_manager.load_branch_index(directory, index_id, read_key)

        clone_meta = branch_manager.get_branch_by_id(branch_index, clone_branch_id)
        if not clone_meta:
            raise RuntimeError(f'Clone branch not found: {clone_branch_id}')

        named_meta = branch_manager.get_branch_by_name(branch_index, 'current')
        if not named_meta:
            raise RuntimeError('Named branch "current" not found')

        # Register clone branch on remote if this is the first push after clone
        self._register_pending_branch(directory, vault_id, write_key,
                                       read_key, storage, ref_manager, _p)

        _p('step', 'Checking for uncommitted changes')
        local_status = self.status(directory)
        if not local_status['clean']:
            raise RuntimeError('Working directory has uncommitted changes. '
                               'Commit your changes before pushing.')

        clone_commit_id = ref_manager.read_ref(str(clone_meta.head_ref_id), read_key)
        named_commit_id = ref_manager.read_ref(str(named_meta.head_ref_id), read_key)

        if not clone_commit_id:
            return dict(status='up_to_date', message='No commits to push')

        if clone_commit_id == named_commit_id:
            # Re-sync bare structure to server only when:
            #  (a) the commit has actual files (not a freshly init'd empty vault), AND
            #  (b) the server has no files (data was lost or never uploaded)
            # A freshly init'd vault with an empty tree has nothing worth syncing.
            if (not self._commit_tree_is_empty(clone_commit_id, obj_store, read_key)
                    and self._is_first_push(vault_id)):
                _p('step', 'Re-syncing vault structure to server')
                self._upload_bare_to_server(directory, vault_id, write_key, storage, read_key)
                return dict(status='resynced', message='Vault structure re-synced to server')
            return dict(status='up_to_date', message='Nothing to push')

        # First push: if server has no files for this vault, upload entire bare structure
        # then continue with the normal delta push (skip pull since server is empty)
        first_push = self._is_first_push(vault_id)
        if first_push:
            _p('step', 'First push — uploading vault structure')
            self._upload_bare_to_server(directory, vault_id, write_key, storage, read_key)

        if branch_only:
            return self._push_branch_only(
                directory=directory, vault_id=vault_id, read_key=read_key,
                write_key=write_key, clone_meta=clone_meta,
                clone_commit_id=clone_commit_id,
                obj_store=obj_store, ref_manager=ref_manager,
                storage=storage, pki=pki, use_batch=use_batch)

        if not first_push and not force:
            _p('step', 'Pulling remote changes first')
            pull_result = self.pull(directory)
            if pull_result['status'] == 'conflicts':
                raise RuntimeError('Pull resulted in merge conflicts. '
                                   'Resolve conflicts before pushing.')

        clone_commit_id = ref_manager.read_ref(str(clone_meta.head_ref_id), read_key)
        named_commit_id = ref_manager.read_ref(str(named_meta.head_ref_id), read_key)

        if clone_commit_id == named_commit_id:
            return dict(status='up_to_date', message='Nothing to push')

        if not clone_commit_id:
            return dict(status='up_to_date', message='No commits to push')

        named_ref_id      = str(named_meta.head_ref_id)
        expected_ref_hash = ref_manager.get_ref_file_hash(named_ref_id)

        vault_commit = Vault__Commit(crypto=self.crypto, pki=pki,
                                     object_store=obj_store, ref_manager=ref_manager)
        sub_tree     = Vault__Sub_Tree(crypto=self.crypto, obj_store=obj_store)

        clone_commit   = vault_commit.load_commit(clone_commit_id, read_key)
        clone_flat     = sub_tree.flatten(str(clone_commit.tree_id), read_key)

        named_blob_ids = set()
        if named_commit_id:
            named_commit = vault_commit.load_commit(named_commit_id, read_key)
            named_flat   = sub_tree.flatten(str(named_commit.tree_id), read_key)
            for entry in named_flat.values():
                bid = entry.get('blob_id')
                if bid:
                    named_blob_ids.add(bid)

        _p('step', 'Computing delta')
        fetcher = Vault__Fetch(crypto=self.crypto, api=self.api, storage=storage)
        commit_chain = fetcher.fetch_commit_chain(obj_store, read_key, clone_commit_id,
                                                   stop_at=named_commit_id)

        # Only count commits that are genuinely new (not the stop_at commit)
        new_commits = [cid for cid in commit_chain if cid != named_commit_id]

        # Convert flat entries to list for batch operations
        clone_tree_entries = list(clone_flat.values())

        batch = Vault__Batch(crypto=self.crypto, api=self.api)
        operations, large_uploaded = batch.build_push_operations(
            obj_store          = obj_store,
            ref_manager        = ref_manager,
            clone_tree_entries = clone_tree_entries,
            named_blob_ids     = named_blob_ids,
            commit_chain       = commit_chain,
            named_commit_id    = named_commit_id,
            read_key           = read_key,
            named_ref_id       = named_ref_id,
            clone_commit_id    = clone_commit_id,
            expected_ref_hash  = expected_ref_hash,
            vault_id           = vault_id,
            write_key          = write_key,
            on_progress        = on_progress)

        commit_and_tree_ids = set()
        for cid in new_commits:
            commit_and_tree_ids.add(cid)
            chain_commit = vault_commit.load_commit(cid, read_key)
            commit_and_tree_ids.add(str(chain_commit.tree_id))

        blob_count = large_uploaded + sum(1 for op in operations
                         if op['file_id'].startswith('bare/data/') and
                            op['file_id'].replace('bare/data/', '') not in commit_and_tree_ids)
        commit_count = len(new_commits)

        if first_push:
            # _upload_bare_to_server already uploaded all objects.
            # Only execute the CAS ref update — skip the redundant object re-uploads.
            operations     = [op for op in operations if op['op'] == 'write-if-match']
            large_uploaded = 0

        upload_count = len(operations) + large_uploaded
        _p('step', 'Uploading objects', f'{upload_count} object(s)')
        if use_batch:
            try:
                batch.execute_batch(vault_id, write_key, operations)
            except Exception as e:
                _p('warning', 'Batch upload failed, falling back to individual uploads', str(e))
                batch.execute_individually(vault_id, write_key, operations)
        else:
            batch.execute_individually(vault_id, write_key, operations)

        _p('step', 'Updating remote ref')
        ref_manager.write_ref(named_ref_id, clone_commit_id, read_key)

        return dict(status          = 'pushed',
                    commit_id       = clone_commit_id,
                    objects_uploaded = blob_count,
                    commits_pushed  = commit_count)

    def _push_branch_only(self, directory, vault_id, read_key, write_key,
                          clone_meta, clone_commit_id,
                          obj_store, ref_manager, storage, pki,
                          use_batch=True):
        """Push clone branch objects and ref without updating the named branch.

        Uploads all objects reachable from the clone branch HEAD and updates
        only the clone branch ref on the server. The named branch is untouched.
        """
        vault_commit = Vault__Commit(crypto=self.crypto, pki=pki,
                                     object_store=obj_store, ref_manager=ref_manager)
        sub_tree     = Vault__Sub_Tree(crypto=self.crypto, obj_store=obj_store)

        clone_commit = vault_commit.load_commit(clone_commit_id, read_key)
        clone_flat   = sub_tree.flatten(str(clone_commit.tree_id), read_key)

        fetcher = Vault__Fetch(crypto=self.crypto, api=self.api, storage=storage)
        commit_chain = fetcher.fetch_commit_chain(obj_store, read_key, clone_commit_id,
                                                   stop_at=None)

        clone_ref_id      = str(clone_meta.head_ref_id)
        expected_ref_hash = ref_manager.get_ref_file_hash(clone_ref_id)

        batch = Vault__Batch(crypto=self.crypto, api=self.api)
        operations, large_uploaded = batch.build_push_operations(
            obj_store          = obj_store,
            ref_manager        = ref_manager,
            clone_tree_entries = list(clone_flat.values()),
            named_blob_ids     = set(),
            commit_chain       = commit_chain,
            named_commit_id    = None,
            read_key           = read_key,
            named_ref_id       = clone_ref_id,
            clone_commit_id    = clone_commit_id,
            expected_ref_hash  = expected_ref_hash,
            vault_id           = vault_id,
            write_key          = write_key,
            on_progress        = None)

        blob_count   = large_uploaded + sum(1 for op in operations if op['file_id'].startswith('bare/data/'))
        commit_count = len(commit_chain)

        if use_batch:
            try:
                batch.execute_batch(vault_id, write_key, operations)
            except Exception as e:
                _p('warning', 'Batch upload failed, falling back to individual uploads', str(e))
                batch.execute_individually(vault_id, write_key, operations)
        else:
            batch.execute_individually(vault_id, write_key, operations)

        return dict(status          = 'pushed_branch_only',
                    commit_id       = clone_commit_id,
                    branch_ref_id   = clone_ref_id,
                    objects_uploaded = blob_count,
                    commits_pushed  = commit_count)

    def merge_abort(self, directory: str) -> dict:
        """Abort an in-progress merge by restoring the pre-merge state."""
        c = self._init_components(directory)
        read_key    = c.read_key
        storage     = c.storage
        pki         = c.pki
        obj_store   = c.obj_store
        ref_manager = c.ref_manager
        merger      = Vault__Merge(crypto=self.crypto)

        merge_state_path = os.path.join(storage.local_dir(directory), 'merge_state.json')
        if not os.path.isfile(merge_state_path):
            raise RuntimeError('No merge in progress')

        with open(merge_state_path, 'r') as f:
            merge_state = json.load(f)

        clone_commit_id = merge_state['clone_commit_id']

        vault_commit = Vault__Commit(crypto=self.crypto, pki=pki,
                                     object_store=obj_store, ref_manager=ref_manager)

        if clone_commit_id:
            ours_commit = vault_commit.load_commit(clone_commit_id, read_key)
            sub_tree    = Vault__Sub_Tree(crypto=self.crypto, obj_store=obj_store)
            sub_tree.checkout(directory, str(ours_commit.tree_id), read_key)

        removed = merger.remove_conflict_files(directory)
        os.remove(merge_state_path)

        return dict(status          = 'aborted',
                    restored_commit = clone_commit_id,
                    removed_files   = removed)

    def branches(self, directory: str) -> dict:
        """List all branches in the vault."""
        c = self._init_components(directory)
        read_key       = c.read_key
        storage        = c.storage
        ref_manager    = c.ref_manager
        branch_manager = c.branch_manager

        index_id = c.branch_index_file_id
        if not index_id:
            return dict(branches=[], my_branch_id='')

        branch_index = branch_manager.load_branch_index(directory, index_id, read_key)

        local_config = self._read_local_config(directory, storage)
        my_branch_id = str(local_config.my_branch_id)

        result = []
        for branch in branch_index.branches:
            head_commit_id = ref_manager.read_ref(str(branch.head_ref_id), read_key)
            result.append(dict(branch_id   = str(branch.branch_id),
                               name        = str(branch.name),
                               branch_type = str(branch.branch_type.value) if branch.branch_type else 'unknown',
                               head_ref_id = str(branch.head_ref_id),
                               head_commit = head_commit_id or '',
                               is_current  = str(branch.branch_id) == my_branch_id))

        return dict(branches=result, my_branch_id=my_branch_id)

    def gc_drain(self, directory: str) -> dict:
        """Drain all pending change packs into the object store.

        Called automatically during push and pull to integrate
        any externally-submitted change packs.
        """
        vault_key  = self._read_vault_key(directory)
        keys       = self.crypto.derive_keys_from_vault_key(vault_key)
        read_key   = keys['read_key_bytes']

        storage = Vault__Storage()
        local_config    = self._read_local_config(directory, storage)
        clone_branch_id = str(local_config.my_branch_id)

        gc = Vault__GC(crypto=self.crypto, storage=storage)
        return gc.drain_pending(directory, read_key, clone_branch_id,
                                branch_index_file_id=keys['branch_index_file_id'])

    def create_change_pack(self, directory: str, files: dict) -> dict:
        """Create a change pack in bare/pending/ for later integration.

        files: dict of {path: content_bytes_or_str}
        """
        vault_key  = self._read_vault_key(directory)
        keys       = self.crypto.derive_keys_from_vault_key(vault_key)
        read_key   = keys['read_key_bytes']

        storage = Vault__Storage()
        local_config    = self._read_local_config(directory, storage)
        clone_branch_id = str(local_config.my_branch_id)

        change_pack = Vault__Change_Pack(crypto=self.crypto, storage=storage)
        return change_pack.create_change_pack(directory, read_key, files, clone_branch_id)

    def remote_add(self, directory: str, name: str, url: str, vault_id: str) -> dict:
        """Add a named remote to the vault."""
        storage = Vault__Storage()
        manager = Vault__Remote_Manager(storage=storage)
        remote  = manager.add_remote(directory, name, url, vault_id)
        return dict(name=str(remote.name), url=str(remote.url), vault_id=str(remote.vault_id))

    def remote_remove(self, directory: str, name: str) -> dict:
        """Remove a named remote from the vault."""
        storage = Vault__Storage()
        manager = Vault__Remote_Manager(storage=storage)
        removed = manager.remove_remote(directory, name)
        if not removed:
            raise RuntimeError(f'Remote not found: {name}')
        return dict(removed=name)

    def remote_list(self, directory: str) -> dict:
        """List all configured remotes."""
        storage = Vault__Storage()
        manager = Vault__Remote_Manager(storage=storage)
        remotes = manager.list_remotes(directory)
        return dict(remotes=remotes)

    def clone(self, vault_key: str, directory: str, on_progress: callable = None) -> dict:
        """Clone a vault from the remote server into a local directory.

        Workflow:
        1.  Derive keys from vault_key
        2.  Create directory and bare structure
        3.  Download branch index (deterministic file ID from keys)
        4.  From index: batch-download all refs + public keys (always small)
        5.  Walk commit chain → BFS walk all tree objects (batch per wave)
        6.  Flatten trees → collect all blob IDs + sizes + large flags
        7.  Download small blobs via budget-chunked batch_read (parallel chunks)
        8.  Download large blobs via presigned S3 (parallel)
        9.  Create new clone branch with EC P-256 key pair
        10. Set clone branch ref to same HEAD as named branch
        11. Set up local/ (config.json, vault_key)
        12. Extract working copy from HEAD tree
        """
        from sgit_ai.transfer.Simple_Token import Simple_Token
        if Simple_Token.is_simple_token(vault_key) or vault_key.startswith('vault://'):
            token_str = vault_key.removeprefix('vault://')
            return self._clone_resolve_simple_token(token_str, directory, on_progress)

        return self._clone_with_keys(vault_key, directory, on_progress)

    def _clone_with_keys(self, vault_key: str, directory: str, on_progress: callable = None) -> dict:
        """Internal clone implementation — works with any vault_key (passphrase:id OR simple token)."""
        if os.path.exists(directory):
            entries = os.listdir(directory)
            if entries:
                raise RuntimeError(f'Directory is not empty: {directory}')
        os.makedirs(directory, exist_ok=True)

        _p = on_progress or (lambda *a, **k: None)

        keys      = self._derive_keys_from_stored_key(vault_key)
        vault_id  = keys['vault_id']
        read_key  = keys['read_key_bytes']
        write_key = keys['write_key']

        _p('step', 'Deriving vault keys')

        storage = Vault__Storage()
        sg_dir  = storage.create_bare_structure(directory)

        # Helper: save a downloaded file to the local bare structure
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

        # Phase 1: Download branch index (1 deterministic file, always small)
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

        # Phase 2: Download all refs + public keys from all known branches (always small)
        _p('step', 'Downloading branch metadata')
        structural_fids = []
        for branch in branch_index.branches:
            if branch.head_ref_id:
                structural_fids.append(f'bare/refs/{str(branch.head_ref_id)}')
            if branch.public_key_id:
                structural_fids.append(f'bare/keys/{str(branch.public_key_id)}')
        if structural_fids:
            for fid, data in self.api.batch_read(vault_id, structural_fids).items():
                if data:
                    save_file(fid, data)

        named_commit_id = ref_manager.read_ref(str(named_meta.head_ref_id), read_key)

        if named_commit_id:
            vc       = Vault__Commit(crypto=self.crypto, pki=pki,
                                     object_store=obj_store, ref_manager=ref_manager)
            sub_tree = Vault__Sub_Tree(crypto=self.crypto, obj_store=obj_store)

            # Phase 3: Walk commit chain — download commits in BFS waves
            _p('step', 'Downloading vault structure')
            visited_commits = set()
            commit_queue    = [named_commit_id]
            root_tree_ids   = []

            while commit_queue:
                to_dl = [f'bare/data/{cid}' for cid in commit_queue
                         if cid not in visited_commits]
                if to_dl:
                    for fid, data in self.api.batch_read(vault_id, to_dl).items():
                        if data:
                            save_file(fid, data)
                next_commits = []
                for cid in commit_queue:
                    if cid in visited_commits:
                        continue
                    visited_commits.add(cid)
                    commit  = vc.load_commit(cid, read_key)
                    tree_id = str(commit.tree_id)
                    if tree_id:
                        root_tree_ids.append(tree_id)
                    for pid in (commit.parents or []):
                        pid_str = str(pid)
                        if pid_str and pid_str not in visited_commits:
                            next_commits.append(pid_str)
                commit_queue = next_commits

            # Phase 4: BFS walk all tree objects — download per wave, large trees never exist
            visited_trees = set()
            tree_queue    = list(root_tree_ids)
            while tree_queue:
                to_dl = [f'bare/data/{tid}' for tid in tree_queue
                         if tid not in visited_trees]
                if to_dl:
                    for fid, data in self.api.batch_read(vault_id, to_dl).items():
                        if data:
                            save_file(fid, data)
                next_trees = []
                for tid in tree_queue:
                    if tid in visited_trees:
                        continue
                    visited_trees.add(tid)
                    tree = vc.load_tree(tid, read_key)
                    for entry in tree.entries:
                        sub_tid = str(entry.tree_id) if entry.tree_id else None
                        if sub_tid and sub_tid not in visited_trees:
                            next_trees.append(sub_tid)
                tree_queue = next_trees

            # Phase 5: Flatten HEAD tree → collect blob IDs + sizes + large flags
            commit_obj   = vc.load_commit(named_commit_id, read_key)
            flat_entries = sub_tree.flatten(str(commit_obj.tree_id), read_key)

            small_blobs = []   # list of (file_id, plaintext_size)
            large_blobs = []   # list of file_id
            for entry_data in flat_entries.values():
                blob_id = entry_data.get('blob_id', '')
                if not blob_id:
                    continue
                fid = f'bare/data/{blob_id}'
                if entry_data.get('large'):
                    large_blobs.append(fid)
                else:
                    small_blobs.append((fid, entry_data.get('size', 0)))

            total_blobs = len(small_blobs) + len(large_blobs)
            if total_blobs:
                _p('step', f'Downloading {total_blobs} file(s)')

            # Phase 6: Download small blobs in budget-based chunks (parallel)
            MAX_RESPONSE_BYTES = 3 * 1024 * 1024   # 3 MB response budget per batch_read
            chunks        = []
            cur_chunk     = []
            cur_chunk_sz  = 0
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
                for fid, data in self.api.batch_read(vault_id, chunk).items():
                    if data:
                        save_file(fid, data)

            if len(chunks) > 1:
                from concurrent.futures import ThreadPoolExecutor
                with ThreadPoolExecutor(max_workers=len(chunks)) as executor:
                    for fut in [executor.submit(fetch_small_chunk, c) for c in chunks]:
                        fut.result()
            elif chunks:
                fetch_small_chunk(chunks[0])

            # Phase 7: Download large blobs via presigned S3 (parallel)
            if large_blobs:
                debug_log = getattr(self.api, 'debug_log', None)

                def download_large_blob(fid):
                    url_info = self.api.presigned_read_url(vault_id, fid)
                    s3_url   = url_info.get('url') or url_info.get('presigned_url', '')
                    entry    = debug_log.log_request('GET', s3_url) if debug_log else None
                    with urlopen(s3_url) as resp:
                        data = resp.read()
                        if entry:
                            debug_log.log_response(entry, resp.status, len(data))
                    save_file(fid, data)

                from concurrent.futures import ThreadPoolExecutor
                with ThreadPoolExecutor(max_workers=min(len(large_blobs), 4)) as executor:
                    for fut in [executor.submit(download_large_blob, fid) for fid in large_blobs]:
                        fut.result()

        _p('step', 'Creating clone branch')
        timestamp_ms = int(time.time() * 1000)
        clone_branch = branch_manager.create_clone_branch(directory, 'local', read_key,
                                                           creator_branch_id=str(named_meta.branch_id),
                                                           timestamp_ms=timestamp_ms)

        if named_commit_id:
            ref_manager.write_ref(str(clone_branch.head_ref_id), named_commit_id, read_key)

        branch_index.branches.append(clone_branch)
        branch_manager.save_branch_index(directory, branch_index, read_key,
                                         index_file_id=index_id)

        # Save pending registration data so it can be uploaded on first push
        pending_path = os.path.join(storage.local_dir(directory), 'pending_registration.json')
        pending_data = dict(index_id      = index_id,
                            head_ref_id   = str(clone_branch.head_ref_id),
                            public_key_id = str(clone_branch.public_key_id),
                            commit_id     = named_commit_id or '')
        with open(pending_path, 'w') as f:
            json.dump(pending_data, f, indent=2)
        _p('step', 'Clone branch will be registered on first push')

        _p('step', 'Setting up local config')
        local_config_data = dict(Schema__Local_Config(my_branch_id=str(clone_branch.branch_id)).json())
        from sgit_ai.transfer.Simple_Token import Simple_Token as _ST
        if _ST.is_simple_token(vault_key):
            local_config_data['mode']       = 'simple_token'
            local_config_data['edit_token'] = vault_key
        config_path  = storage.local_config_path(directory)
        with open(config_path, 'w') as f:
            json.dump(local_config_data, f, indent=2)

        with open(storage.vault_key_path(directory), 'w') as f:
            f.write(vault_key)

        if named_commit_id:
            _p('step', 'Extracting working copy')
            vc_checkout  = Vault__Commit(crypto=self.crypto, pki=pki,
                                         object_store=obj_store, ref_manager=ref_manager)
            commit_obj   = vc_checkout.load_commit(named_commit_id, read_key)
            st_checkout  = Vault__Sub_Tree(crypto=self.crypto, obj_store=obj_store)
            st_checkout.checkout(directory, str(commit_obj.tree_id), read_key)

        return dict(directory    = directory,
                    vault_key    = vault_key,
                    vault_id     = vault_id,
                    branch_id    = str(clone_branch.branch_id),
                    named_branch = str(named_meta.branch_id),
                    commit_id    = named_commit_id or '')

    def clone_from_transfer(self, token_str: str, directory: str) -> dict:
        """Scenario A: download and import a SG/Send transfer, creating a new local vault.

        Steps:
        1. Receive transfer files via Simple Token
        2. Generate a new edit token for the local vault
        3. Init the vault with the new edit token
        4. Write received files into the working directory
        5. Commit with an import message
        6. Save the share_token in local/config.json
        7. Return summary dict
        """
        from sgit_ai.api.API__Transfer            import API__Transfer
        from sgit_ai.transfer.Vault__Transfer     import Vault__Transfer
        from sgit_ai.transfer.Simple_Token__Wordlist import Simple_Token__Wordlist

        api      = API__Transfer()
        api.setup()
        transfer = Vault__Transfer(api=api, crypto=self.crypto)

        receive_result = transfer.receive(token_str)
        files          = receive_result['files']

        new_token = str(Simple_Token__Wordlist().setup().generate())
        self.init(directory, token=new_token)

        for path, content in files.items():
            # Skip sgit metadata folders (_share.* / __share__* / __gallery__*)
            top = path.split('/')[0]
            if top.startswith('__share__') or top.startswith('_share.') or top.startswith('__gallery__'):
                continue
            full_path = os.path.join(directory, path)
            parent    = os.path.dirname(full_path)
            if parent and parent != directory:
                os.makedirs(parent, exist_ok=True)
            with open(full_path, 'wb') as f:
                f.write(content if isinstance(content, bytes) else content.encode('utf-8'))

        self.commit(directory, message=f'Imported from vault://{token_str}')

        storage     = Vault__Storage()
        config_path = storage.local_config_path(directory)
        with open(config_path, 'r') as f:
            config_data = json.load(f)
        config_data['share_token'] = token_str
        with open(config_path, 'w') as f:
            json.dump(config_data, f, indent=2)

        return dict(vault_id    = new_token,
                    share_token = token_str,
                    file_count  = len(files),
                    directory   = directory)

    def _clone_resolve_simple_token(self, token_str: str, directory: str,
                                    on_progress: callable = None) -> dict:
        """Resolve a simple token clone: check SGit-AI vault first, then SG/Send transfer."""
        _p = on_progress or (lambda *a, **k: None)

        # Step 1: try SGit-AI vault lookup
        _p('step', f'Checking SGit-AI for vault: {token_str}')
        try:
            keys     = self.crypto.derive_keys_from_simple_token(token_str)
            vault_id = keys['vault_id']
            read_key = keys['read_key_bytes']
            index_id = keys['branch_index_file_id']
            index_fid = f'bare/indexes/{index_id}'
            idx_data  = self.api.batch_read(vault_id, [index_fid])
            if idx_data.get(index_fid):
                _p('step', 'Vault found on SGit-AI — cloning with simple token keys')
                return self._clone_with_keys(token_str, directory, on_progress)
        except Exception:
            pass

        # Step 2: try SG/Send transfer lookup
        _p('step', f'Vault not found — checking SG/Send for transfer: {token_str}')
        try:
            return self.clone_from_transfer(token_str, directory)
        except Exception as e:
            raise RuntimeError(f"No vault or transfer found for '{token_str}'") from e

    def _read_local_config(self, directory: str, storage: Vault__Storage) -> Schema__Local_Config:
        config_path = storage.local_config_path(directory)
        with open(config_path, 'r') as f:
            data = json.load(f)
        return Schema__Local_Config.from_json(data)

    def _generate_commit_message(self, old_entries: dict, new_file_map: dict) -> str:
        old_paths = set(old_entries.keys())
        new_paths = set(new_file_map.keys())
        added     = len(new_paths - old_paths)
        deleted   = len(old_paths - new_paths)
        modified  = 0
        for path in old_paths & new_paths:
            old_entry = old_entries[path]
            old_hash  = old_entry.get('content_hash', '')
            new_hash  = new_file_map[path].get('content_hash', '')
            if old_hash and new_hash:
                if old_hash != new_hash:
                    modified += 1
            else:
                old_size = old_entry.get('size', -1)
                new_size = new_file_map[path].get('size', -2)
                if old_size != new_size:
                    modified += 1
        return f'Commit: {added} added, {modified} modified, {deleted} deleted'

    def _checkout_flat_map(self, directory: str, flat_map: dict,
                           obj_store: Vault__Object_Store, read_key: bytes) -> None:
        """Write all files from a flat {path: dict} map to the working directory."""
        for path, entry in sorted(flat_map.items()):
            blob_id = entry.get('blob_id')
            if not blob_id:
                continue
            try:
                ciphertext = obj_store.load(blob_id)
                plaintext  = self.crypto.decrypt(read_key, ciphertext)
                full_path  = os.path.join(directory, path)
                os.makedirs(os.path.dirname(full_path), exist_ok=True)
                with open(full_path, 'wb') as f:
                    f.write(plaintext)
            except Exception:
                pass

    def _remove_deleted_flat(self, directory: str, old_map: dict, new_map: dict) -> None:
        """Remove files present in old_map but not in new_map."""
        for path in set(old_map.keys()) - set(new_map.keys()):
            full_path = os.path.join(directory, path)
            if os.path.isfile(full_path):
                os.remove(full_path)

    # --- push-tracking helpers ---

    def _walk_commit_ids(self, obj_store, read_key: bytes, start: str,
                         limit: int = 200) -> set:
        """Return the set of all commit IDs reachable from start (inclusive)."""
        pki     = PKI__Crypto()
        vc      = Vault__Commit(crypto=self.crypto, pki=pki,
                                object_store=obj_store, ref_manager=Vault__Ref_Manager())
        visited = set()
        queue   = [start] if start else []
        while queue and len(visited) < limit:
            cid = queue.pop(0)
            if not cid or cid in visited:
                continue
            visited.add(cid)
            try:
                commit  = vc.load_commit(cid, read_key)
                parents = list(commit.parents) if commit.parents else []
                queue.extend(str(p) for p in parents if str(p))
            except Exception:
                pass
        return visited

    def _count_unique_commits(self, obj_store, read_key: bytes,
                              from_head: str, stop_head: str,
                              limit: int = 200) -> int:
        """Count commits reachable from from_head that are NOT reachable from stop_head."""
        if not from_head:
            return 0
        stop_ancestors = self._walk_commit_ids(obj_store, read_key, stop_head, limit)
        from_ancestors = self._walk_commit_ids(obj_store, read_key, from_head, limit)
        return len(from_ancestors - stop_ancestors)

    def _count_commits_from(self, obj_store, read_key: bytes,
                            start: str, limit: int = 200) -> int:
        """Count commits reachable from start (i.e. entire chain length)."""
        if not start:
            return 0
        return len(self._walk_commit_ids(obj_store, read_key, start, limit))

    # --- internal helpers ---

    def _auto_gc_drain(self, directory: str) -> None:
        """Silently drain any pending change packs. Called at start of push/pull."""
        try:
            storage     = Vault__Storage()
            pending_dir = storage.bare_pending_dir(directory)
            if not os.path.isdir(pending_dir):
                return
            if not any(d.startswith('pack-') for d in os.listdir(pending_dir)):
                return
            self.gc_drain(directory)
        except Exception:
            pass

    def _derive_keys_from_stored_key(self, vault_key: str) -> dict:
        from sgit_ai.transfer.Simple_Token import Simple_Token
        if Simple_Token.is_simple_token(vault_key):
            return self.crypto.derive_keys_from_simple_token(vault_key)
        return self.crypto.derive_keys_from_vault_key(vault_key)

    def _init_components(self, directory: str) -> Vault__Components:
        vault_key   = self._read_vault_key(directory)
        keys        = self._derive_keys_from_stored_key(vault_key)
        sg_dir      = os.path.join(directory, SG_VAULT_DIR)
        storage     = Vault__Storage()
        pki         = PKI__Crypto()
        obj_store   = Vault__Object_Store(vault_path=sg_dir, crypto=self.crypto)
        ref_manager = Vault__Ref_Manager(vault_path=sg_dir, crypto=self.crypto)
        key_manager = Vault__Key_Manager(vault_path=sg_dir, crypto=self.crypto, pki=pki)
        branch_manager = Vault__Branch_Manager(vault_path=sg_dir, crypto=self.crypto,
                                               key_manager=key_manager, ref_manager=ref_manager,
                                               storage=storage)
        return Vault__Components(vault_key              = vault_key,
                                 vault_id               = keys['vault_id'],
                                 read_key               = keys['read_key_bytes'],
                                 write_key              = keys['write_key'],
                                 ref_file_id            = keys['ref_file_id'],
                                 branch_index_file_id   = keys['branch_index_file_id'],
                                 sg_dir                 = sg_dir,
                                 storage                = storage,
                                 pki                    = pki,
                                 obj_store              = obj_store,
                                 ref_manager            = ref_manager,
                                 key_manager            = key_manager,
                                 branch_manager         = branch_manager)

    def _fetch_missing_objects(self, vault_id: str, commit_id: str,
                               obj_store: Vault__Object_Store, read_key: bytes,
                               sg_dir: str, _p: callable = None) -> None:
        """Walk the commit chain from commit_id, downloading any missing objects."""
        _p = _p or (lambda *a, **k: None)
        pki = PKI__Crypto()
        vc  = Vault__Commit(crypto=self.crypto, pki=pki,
                            object_store=obj_store, ref_manager=Vault__Ref_Manager())
        visited    = set()
        queue      = [commit_id]
        downloaded = 0

        while queue:
            oid = queue.pop(0)
            if not oid or oid in visited:
                continue
            visited.add(oid)

            if not obj_store.exists(oid):
                try:
                    data = self.api.read(vault_id, f'bare/data/{oid}')
                    if data:
                        local_path = os.path.join(sg_dir, 'bare', 'data', oid)
                        os.makedirs(os.path.dirname(local_path), exist_ok=True)
                        with open(local_path, 'wb') as f:
                            f.write(data)
                        downloaded += 1
                except Exception:
                    continue

            try:
                commit = vc.load_commit(oid, read_key)
                tree_id = str(commit.tree_id)
                if tree_id and not obj_store.exists(tree_id):
                    try:
                        data = self.api.read(vault_id, f'bare/data/{tree_id}')
                        if data:
                            local_path = os.path.join(sg_dir, 'bare', 'data', tree_id)
                            os.makedirs(os.path.dirname(local_path), exist_ok=True)
                            with open(local_path, 'wb') as f:
                                f.write(data)
                    except Exception:
                        pass

                # Recursively walk all trees reachable from this commit
                tree_queue   = [tree_id]
                visited_trees = set()
                while tree_queue:
                    tid = tree_queue.pop(0)
                    if not tid or tid in visited_trees:
                        continue
                    visited_trees.add(tid)

                    cur_tree = vc.load_tree(tid, read_key) if obj_store.exists(tid) else None
                    if not cur_tree:
                        continue
                    for entry in cur_tree.entries:
                        blob_id = str(entry.blob_id) if entry.blob_id else None
                        if blob_id and not obj_store.exists(blob_id):
                            try:
                                if getattr(entry, 'large', False):
                                    url_info = self.api.presigned_read_url(vault_id, f'bare/data/{blob_id}')
                                    data = urlopen(url_info['url']).read()
                                else:
                                    data = self.api.read(vault_id, f'bare/data/{blob_id}')
                                if data:
                                    local_path = os.path.join(sg_dir, 'bare', 'data', blob_id)
                                    os.makedirs(os.path.dirname(local_path), exist_ok=True)
                                    with open(local_path, 'wb') as f:
                                        f.write(data)
                                    downloaded += 1
                            except Exception:
                                pass
                        sub_tree_id = str(entry.tree_id) if entry.tree_id else None
                        if sub_tree_id:
                            if not obj_store.exists(sub_tree_id):
                                try:
                                    data = self.api.read(vault_id, f'bare/data/{sub_tree_id}')
                                    if data:
                                        local_path = os.path.join(sg_dir, 'bare', 'data', sub_tree_id)
                                        os.makedirs(os.path.dirname(local_path), exist_ok=True)
                                        with open(local_path, 'wb') as f:
                                            f.write(data)
                                except Exception:
                                    pass
                            tree_queue.append(sub_tree_id)

                parents = list(commit.parents) if commit.parents else []
                for pid in parents:
                    if str(pid) not in visited:
                        queue.append(str(pid))
            except Exception:
                pass

        if downloaded:
            _p('step', f'Downloaded {downloaded} objects')

    def fsck(self, directory: str, repair: bool = False, on_progress: callable = None) -> dict:
        """Verify vault integrity and optionally repair by downloading missing objects.

        Returns dict with:
          ok       : bool  — True if vault is healthy (or was repaired)
          missing  : list  — object IDs missing from local store
          corrupt  : list  — object IDs that fail integrity check
          repaired : list  — object IDs re-downloaded (repair mode only)
          errors   : list  — human-readable error descriptions
        """
        _p      = on_progress or (lambda *a, **k: None)
        result  = dict(ok=True, missing=[], corrupt=[], repaired=[], errors=[])

        # --- basic structure checks ---
        sg_dir = os.path.join(directory, SG_VAULT_DIR)
        if not os.path.isdir(sg_dir):
            result['ok'] = False
            result['errors'].append(f'Not a vault: {directory} (no .sg_vault/ directory)')
            return result

        _p('step', 'Reading vault configuration')
        try:
            c = self._init_components(directory)
        except Exception as e:
            result['ok'] = False
            result['errors'].append(f'Cannot read vault config: {e}')
            return result

        read_key    = c.read_key
        obj_store   = c.obj_store
        ref_manager = c.ref_manager
        pki         = c.pki

        # --- find HEAD commit ---
        _p('step', 'Loading branch index')
        try:
            index_id     = c.branch_index_file_id
            branch_index = c.branch_manager.load_branch_index(directory, index_id, read_key)
            local_config = self._read_local_config(directory, c.storage)
            clone_meta   = c.branch_manager.get_branch_by_id(branch_index, str(local_config.my_branch_id))
            commit_id    = ref_manager.read_ref(str(clone_meta.head_ref_id), read_key) if clone_meta else None
        except Exception as e:
            result['ok'] = False
            result['errors'].append(f'Cannot read branch info: {e}')
            return result

        if not commit_id:
            _p('step', 'Empty vault — no commits to check')
            return result

        # --- walk commit chain, verify all referenced objects ---
        _p('step', 'Walking commit chain')
        vc       = Vault__Commit(crypto=self.crypto, pki=pki,
                                  object_store=obj_store, ref_manager=ref_manager)
        visited  = set()
        queue    = [commit_id]
        checked  = 0

        while queue:
            oid = queue.pop(0)
            if not oid or oid in visited:
                continue
            visited.add(oid)
            checked += 1

            if not obj_store.exists(oid):
                result['missing'].append(oid)
                result['ok'] = False
                if repair:
                    if self._repair_object(oid, c.vault_id, c.sg_dir):
                        result['repaired'].append(oid)
                else:
                    continue                                # can't walk further without the object

            if not obj_store.exists(oid):
                continue                                    # repair failed, skip

            if not obj_store.verify_integrity(oid):
                result['corrupt'].append(oid)
                result['ok'] = False

            try:
                commit = vc.load_commit(oid, read_key)
            except Exception:
                result['errors'].append(f'Cannot load commit {oid}')
                result['ok'] = False
                continue

            # walk tree
            tree_queue    = [str(commit.tree_id)] if commit.tree_id else []
            visited_trees = set()
            while tree_queue:
                tid = tree_queue.pop(0)
                if not tid or tid in visited_trees:
                    continue
                visited_trees.add(tid)

                if not obj_store.exists(tid):
                    result['missing'].append(tid)
                    result['ok'] = False
                    if repair:
                        if self._repair_object(tid, c.vault_id, c.sg_dir):
                            result['repaired'].append(tid)
                    if not obj_store.exists(tid):
                        continue

                if not obj_store.verify_integrity(tid):
                    result['corrupt'].append(tid)
                    result['ok'] = False

                try:
                    tree = vc.load_tree(tid, read_key)
                except Exception:
                    result['errors'].append(f'Cannot load tree {tid}')
                    result['ok'] = False
                    continue

                for entry in tree.entries:
                    blob_id = str(entry.blob_id) if entry.blob_id else None
                    if blob_id:
                        if not obj_store.exists(blob_id):
                            result['missing'].append(blob_id)
                            result['ok'] = False
                            if repair:
                                if self._repair_object(blob_id, c.vault_id, c.sg_dir):
                                    result['repaired'].append(blob_id)
                        elif not obj_store.verify_integrity(blob_id):
                            result['corrupt'].append(blob_id)
                            result['ok'] = False
                    sub_tree_id = str(entry.tree_id) if entry.tree_id else None
                    if sub_tree_id:
                        tree_queue.append(sub_tree_id)

            parents = list(commit.parents) if commit.parents else []
            for pid in parents:
                if str(pid) not in visited:
                    queue.append(str(pid))

        _p('step', f'Checked {checked} commits, {len(visited_trees) if "visited_trees" in dir() else 0} trees')

        # after repair, re-check
        if repair and result['repaired']:
            still_missing = [oid for oid in result['missing'] if not obj_store.exists(oid)]
            result['missing'] = still_missing
            if not still_missing and not result['corrupt'] and not result['errors']:
                result['ok'] = True

        return result

    def _repair_object(self, object_id: str, vault_id: str, sg_dir: str) -> bool:
        """Try to download a single missing object from the remote."""
        try:
            data = self.api.read(vault_id, f'bare/data/{object_id}')
            if data:
                local_path = os.path.join(sg_dir, 'bare', 'data', object_id)
                os.makedirs(os.path.dirname(local_path), exist_ok=True)
                with open(local_path, 'wb') as f:
                    f.write(data)
                return True
        except Exception:
            pass
        return False

    def _read_vault_key(self, directory: str) -> str:
        storage        = Vault__Storage()
        vault_key_path = storage.vault_key_path(directory)
        if not os.path.isfile(vault_key_path):
            legacy_path = os.path.join(directory, SG_VAULT_DIR, 'VAULT-KEY')
            if os.path.isfile(legacy_path):
                vault_key_path = legacy_path
        with open(vault_key_path, 'r') as f:
            return f.read().strip()

    def _get_read_key(self, directory: str) -> bytes:
        vault_key = self._read_vault_key(directory)
        keys      = self._derive_keys_from_stored_key(vault_key)
        return keys['read_key_bytes']

    def _commit_tree_is_empty(self, commit_id: str,
                              obj_store: Vault__Object_Store, read_key: bytes) -> bool:
        """Return True if the commit's root tree has no entries (fresh init vault)."""
        try:
            pki    = PKI__Crypto()
            vc     = Vault__Commit(crypto=self.crypto, pki=pki,
                                   object_store=obj_store,
                                   ref_manager=Vault__Ref_Manager(vault_path=obj_store.vault_path,
                                                                   crypto=self.crypto))
            commit = vc.load_commit(commit_id, read_key)
            tree   = vc.load_tree(str(commit.tree_id), read_key)
            return len(tree.entries) == 0
        except Exception:
            return False

    def _is_first_push(self, vault_id: str) -> bool:
        """Check if this vault has any files on the server yet."""
        try:
            remote_files = self.api.list_files(vault_id, 'bare/')
            return len(remote_files) == 0
        except Exception:
            return True

    def _upload_bare_to_server(self, directory: str, vault_id: str,
                               write_key: str, storage: Vault__Storage,
                               read_key: bytes = None) -> None:
        """Upload all bare/ files to the remote server.

        Walks .sg_vault/bare/ and uploads each file with its relative path
        (e.g. bare/data/obj-cas-imm-xxx, bare/refs/ref-pid-muw-xxx).
        Used on first push to bootstrap the vault on the server.
        """
        import base64
        bare_dir = storage.bare_dir(directory)
        if not os.path.isdir(bare_dir):
            return

        batch_ops   = []
        large_files = []
        for root, dirs, files in os.walk(bare_dir):
            for filename in files:
                full_path = os.path.join(root, filename)
                rel_path  = os.path.relpath(full_path, storage.sg_vault_dir(directory))
                rel_path  = rel_path.replace(os.sep, '/')

                with open(full_path, 'rb') as f:
                    data = f.read()
                if len(data) > LARGE_BLOB_THRESHOLD:
                    large_files.append((rel_path, data))
                else:
                    batch_ops.append(dict(op      = 'write',
                                          file_id = rel_path,
                                          data    = base64.b64encode(data).decode('ascii')))

        batch = Vault__Batch(crypto=self.crypto, api=self.api)

        # Upload large blobs via presigned multipart (bypasses Lambda size limit)
        for file_id, data in large_files:
            if not batch._upload_large(vault_id, file_id, data, write_key):
                # presigned_not_available (in-memory/dev) — add to batch as fallback
                batch_ops.append(dict(op      = 'write',
                                      file_id = file_id,
                                      data    = base64.b64encode(data).decode('ascii')))

        if batch_ops:
            try:
                batch.execute_batch(vault_id, write_key, batch_ops)
            except Exception as e:
                print(f'Warning: batch upload failed ({e}), falling back to individual uploads', file=sys.stderr)
                batch.execute_individually(vault_id, write_key, batch_ops)

    def _register_pending_branch(self, directory: str, vault_id: str,
                                  write_key: str, read_key: bytes,
                                  storage: Vault__Storage,
                                  ref_manager: Vault__Ref_Manager,
                                  _p: callable) -> None:
        """Upload clone branch metadata to the server if not yet registered.

        This is called on the first push after a clone. It uploads the branch
        index, ref, and public key that were deferred from clone time.
        """
        import base64
        pending_path = os.path.join(storage.local_dir(directory), 'pending_registration.json')
        if not os.path.isfile(pending_path):
            return

        with open(pending_path, 'r') as f:
            pending = json.load(f)

        _p('step', 'Registering clone branch on remote')
        batch_ops = []

        index_id = pending['index_id']
        index_file_path = storage.index_path(directory, index_id)
        if os.path.isfile(index_file_path):
            with open(index_file_path, 'rb') as f:
                index_data = f.read()
            batch_ops.append(dict(op      = 'write',
                                  file_id = f'bare/indexes/{index_id}',
                                  data    = base64.b64encode(index_data).decode('ascii')))

        commit_id = pending.get('commit_id')
        if commit_id:
            ref_ciphertext = ref_manager.encrypt_ref_value(commit_id, read_key)
            batch_ops.append(dict(op      = 'write',
                                  file_id = f'bare/refs/{pending["head_ref_id"]}',
                                  data    = base64.b64encode(ref_ciphertext).decode('ascii')))

        pub_key_id   = pending['public_key_id']
        pub_key_path = storage.key_path(directory, pub_key_id)
        if os.path.isfile(pub_key_path):
            with open(pub_key_path, 'rb') as f:
                pub_key_data = f.read()
            batch_ops.append(dict(op      = 'write',
                                  file_id = f'bare/keys/{pub_key_id}',
                                  data    = base64.b64encode(pub_key_data).decode('ascii')))

        if batch_ops:
            _p('step', 'Uploading branch registration', f'{len(batch_ops)} objects')
            batch = Vault__Batch(crypto=self.crypto, api=self.api)
            try:
                batch.execute_batch(vault_id, write_key, batch_ops)
            except Exception as e:
                _p('warning', 'Batch upload failed, falling back to individual uploads', str(e))
                batch.execute_individually(vault_id, write_key, batch_ops)

        os.remove(pending_path)

    def uninit(self, directory: str) -> dict:
        """Remove .sg_vault/ from a vault directory after creating an auto-backup zip.

        The backup zip is always created first — it is the safety net.
        Naming: .vault__{folder_name_no_spaces}__<int(time.time())>.zip
        Returns a dict with backup_path, working_files, sg_vault_dir.
        """
        import io
        import re
        import shutil
        import zipfile

        storage = Vault__Storage()
        sg_dir  = storage.sg_vault_dir(directory)
        if not os.path.isdir(sg_dir):
            raise RuntimeError(f'Not a vault directory: {directory} (no .sg_vault/ found)')

        abs_directory = os.path.abspath(directory)
        folder_name   = os.path.basename(abs_directory)
        # Remove spaces from folder name for the filename
        safe_name     = re.sub(r'\s+', '', folder_name)
        timestamp_sec = int(time.time())                # seconds — shorter, human-readable in filenames
        backup_name   = f'.vault__{safe_name}__{timestamp_sec}.zip'
        backup_path   = os.path.join(abs_directory, backup_name)

        # Build zip of the entire .sg_vault/ directory
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, mode='w', compression=zipfile.ZIP_DEFLATED) as zf:
            for root, dirs, files in os.walk(sg_dir):
                for fname in files:
                    full_path  = os.path.join(root, fname)
                    arc_name   = os.path.relpath(full_path, abs_directory)
                    zf.write(full_path, arc_name)
        with open(backup_path, 'wb') as f:
            f.write(buf.getvalue())

        # Count working files (excludes .sg_vault and the backup itself)
        working_files = 0
        for root, dirs, files in os.walk(abs_directory):
            dirs[:] = [d for d in dirs if d != SG_VAULT_DIR]
            for fname in files:
                rel = os.path.relpath(os.path.join(root, fname), abs_directory)
                if not rel.startswith('.vault__'):
                    working_files += 1

        shutil.rmtree(sg_dir)

        return dict(backup_path   = backup_path,
                    backup_size   = os.path.getsize(backup_path),
                    working_files = working_files,
                    sg_vault_dir  = sg_dir)

    def restore_from_backup(self, zip_path: str, directory: str) -> dict:
        """Restore a vault from a .vault__*.zip backup into the given directory.

        The zip must contain a .sg_vault/ tree at its root (as produced by uninit).
        Returns a dict with vault_id, branch_id (loaded from restored local config).
        """
        import json as _json
        import zipfile

        if not os.path.isfile(zip_path):
            raise RuntimeError(f'Backup zip not found: {zip_path}')

        abs_directory = os.path.abspath(directory)
        sg_dir        = os.path.join(abs_directory, SG_VAULT_DIR)

        if os.path.isdir(sg_dir):
            raise RuntimeError(f'Vault already exists in {directory} — remove .sg_vault/ first')

        with zipfile.ZipFile(zip_path, 'r') as zf:
            # Validate: must contain .sg_vault/ entries
            names = zf.namelist()
            if not any(n.startswith(SG_VAULT_DIR + '/') or n.startswith(SG_VAULT_DIR + os.sep)
                       for n in names):
                raise RuntimeError(f'Zip does not look like a vault backup: {zip_path}')
            zf.extractall(abs_directory)

        # Read restored local config for vault_id and branch_id
        storage           = Vault__Storage()
        local_config_path = storage.local_config_path(abs_directory)
        vault_key_path    = storage.vault_key_path(abs_directory)

        vault_id  = None
        branch_id = None
        if os.path.isfile(local_config_path):
            with open(local_config_path, 'r') as f:
                cfg = _json.load(f)
            branch_id = cfg.get('my_branch_id', '')

        if os.path.isfile(vault_key_path):
            with open(vault_key_path, 'r') as f:
                vault_key = f.read().strip()
            keys     = self.crypto.derive_keys_from_vault_key(vault_key)
            vault_id = keys['vault_id']

        return dict(directory = abs_directory,
                    vault_id  = vault_id or '',
                    branch_id = branch_id or '')

    def _scan_local_directory(self, directory: str) -> dict:
        ignore = Vault__Ignore().load_gitignore(directory)
        result = {}
        for root, dirs, files in os.walk(directory):
            rel_root = os.path.relpath(root, directory).replace(os.sep, '/')
            if rel_root == '.':
                rel_root = ''
            dirs[:] = [d for d in dirs
                       if not ignore.should_ignore_dir(f'{rel_root}/{d}' if rel_root else d)]
            for filename in files:
                rel_path = f'{rel_root}/{filename}' if rel_root else filename
                if ignore.should_ignore_file(rel_path):
                    continue
                full_path = os.path.join(root, filename)
                file_size = os.path.getsize(full_path)
                with open(full_path, 'rb') as f:
                    file_hash = self.crypto.content_hash(f.read())
                result[rel_path] = dict(size=file_size, content_hash=file_hash)
        return result
