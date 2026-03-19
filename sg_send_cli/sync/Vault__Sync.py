import json
import os
import secrets
import string
import time
from   datetime                                      import datetime, timezone
from   osbot_utils.type_safe.Type_Safe               import Type_Safe
from   sg_send_cli.crypto.Vault__Crypto              import Vault__Crypto
from   sg_send_cli.crypto.PKI__Crypto                import PKI__Crypto
from   sg_send_cli.crypto.Vault__Key_Manager         import Vault__Key_Manager
from   sg_send_cli.api.Vault__API                    import Vault__API
from   sg_send_cli.sync.Vault__Storage               import Vault__Storage
from   sg_send_cli.sync.Vault__Branch_Manager        import Vault__Branch_Manager
from   sg_send_cli.sync.Vault__Batch                 import Vault__Batch
from   sg_send_cli.sync.Vault__Fetch                 import Vault__Fetch
from   sg_send_cli.sync.Vault__Merge                 import Vault__Merge
from   sg_send_cli.sync.Vault__Change_Pack           import Vault__Change_Pack
from   sg_send_cli.sync.Vault__GC                   import Vault__GC
from   sg_send_cli.sync.Vault__Remote_Manager        import Vault__Remote_Manager
from   sg_send_cli.sync.Vault__Sub_Tree              import Vault__Sub_Tree
from   sg_send_cli.objects.Vault__Object_Store       import Vault__Object_Store
from   sg_send_cli.objects.Vault__Ref_Manager        import Vault__Ref_Manager
from   sg_send_cli.objects.Vault__Commit             import Vault__Commit
from   sg_send_cli.schemas.Schema__Object_Commit     import Schema__Object_Commit
from   sg_send_cli.schemas.Schema__Object_Tree       import Schema__Object_Tree
from   sg_send_cli.schemas.Schema__Object_Tree_Entry import Schema__Object_Tree_Entry
from   sg_send_cli.schemas.Schema__Object_Ref        import Schema__Object_Ref
from   sg_send_cli.schemas.Schema__Branch_Index      import Schema__Branch_Index
from   sg_send_cli.schemas.Schema__Local_Config      import Schema__Local_Config
from   sg_send_cli.sync.Vault__Components             import Vault__Components
from   sg_send_cli.sync.Vault__Ignore                import Vault__Ignore
from   sg_send_cli.sync.Vault__Storage               import SG_VAULT_DIR


class Vault__Sync(Type_Safe):
    crypto       : Vault__Crypto
    api          : Vault__API

    def generate_vault_key(self) -> str:
        alphabet   = string.ascii_lowercase + string.digits
        passphrase = ''.join(secrets.choice(alphabet) for _ in range(24))
        vault_id   = ''.join(secrets.choice(alphabet) for _ in range(8))
        return f'{passphrase}:{vault_id}'

    def init(self, directory: str, vault_key: str = None) -> dict:
        if os.path.exists(directory):
            entries = os.listdir(directory)
            if entries:
                raise RuntimeError(f'Directory is not empty: {directory}')
        os.makedirs(directory, exist_ok=True)

        if not vault_key:
            vault_key = self.generate_vault_key()

        keys       = self.crypto.derive_keys_from_vault_key(vault_key)
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

        local_config = Schema__Local_Config(my_branch_id=str(clone_branch.branch_id))
        config_path  = storage.local_config_path(directory)
        with open(config_path, 'w') as f:
            json.dump(local_config.json(), f, indent=2)

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

        return dict(commit_id = commit_id,
                    branch_id = branch_id,
                    message   = auto_msg)

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
        if not index_id:
            return dict(added=[], modified=[], deleted=[], clean=True)
        branch_index = branch_manager.load_branch_index(directory, index_id, read_key)
        branch_meta  = branch_manager.get_branch_by_id(branch_index, branch_id)
        if not branch_meta:
            return dict(added=[], modified=[], deleted=[], clean=True)

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

        return dict(added=added, modified=modified, deleted=deleted,
                    clean=not added and not modified and not deleted)

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
            # Even when there's no delta, first push must upload bare structure to the server
            try:
                if self._is_first_push(vault_id):
                    self._upload_bare_to_server(directory, vault_id, write_key, storage, read_key)
            except Exception:
                pass
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

        # Convert flat entries to list for batch operations
        clone_tree_entries = list(clone_flat.values())

        batch = Vault__Batch(crypto=self.crypto, api=self.api)
        operations = batch.build_push_operations(
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
            vault_id           = vault_id)

        commit_and_tree_ids = set()
        for cid in commit_chain:
            if cid == named_commit_id:
                continue
            commit_and_tree_ids.add(cid)
            chain_commit = vault_commit.load_commit(cid, read_key)
            commit_and_tree_ids.add(str(chain_commit.tree_id))

        blob_count = sum(1 for op in operations
                         if op['file_id'].startswith('bare/data/') and
                            op['file_id'].replace('bare/data/', '') not in commit_and_tree_ids)
        commit_count = len([cid for cid in commit_chain if cid != named_commit_id])

        _p('step', 'Uploading objects', f'{len(operations)} operations')
        if use_batch:
            try:
                batch.execute_batch(vault_id, write_key, operations)
            except Exception:
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
        operations = batch.build_push_operations(
            obj_store          = obj_store,
            ref_manager        = ref_manager,
            clone_tree_entries = list(clone_flat.values()),
            named_blob_ids     = set(),
            commit_chain       = commit_chain,
            named_commit_id    = None,
            read_key           = read_key,
            named_ref_id       = clone_ref_id,
            clone_commit_id    = clone_commit_id,
            expected_ref_hash  = expected_ref_hash)

        blob_count   = sum(1 for op in operations if op['file_id'].startswith('bare/data/'))
        commit_count = len(commit_chain)

        if use_batch:
            try:
                batch.execute_batch(vault_id, write_key, operations)
            except Exception:
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
        1. Derive keys from vault_key
        2. Create directory and bare structure
        3. Download all bare/ files from the server into local .sg_vault/bare/
        4. Load branch index, find named branch "current"
        5. Create new clone branch with EC P-256 key pair
        6. Set clone branch ref to same HEAD as named branch
        7. Upload new clone branch metadata to server (index, ref, public key)
        8. Set up local/ (config.json, vault_key)
        9. Extract working copy from HEAD tree
        """
        if os.path.exists(directory):
            entries = os.listdir(directory)
            if entries:
                raise RuntimeError(f'Directory is not empty: {directory}')
        os.makedirs(directory, exist_ok=True)

        _p = on_progress or (lambda *a, **k: None)

        keys       = self.crypto.derive_keys_from_vault_key(vault_key)
        vault_id   = keys['vault_id']
        read_key   = keys['read_key_bytes']
        write_key  = keys['write_key']

        _p('step', 'Deriving vault keys')

        storage = Vault__Storage()
        sg_dir  = storage.create_bare_structure(directory)

        _p('step', 'Downloading vault structure')
        remote_files = self.api.list_files(vault_id, 'bare/')
        total_files  = len(remote_files)
        for i, file_id in enumerate(remote_files, 1):
            _p('download', 'Downloading', f'{i}/{total_files}')
            data       = self.api.read(vault_id, file_id)
            local_path = os.path.join(sg_dir, file_id)
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            with open(local_path, 'wb') as f:
                f.write(data)

        pki         = PKI__Crypto()
        key_manager = Vault__Key_Manager(vault_path=sg_dir, crypto=self.crypto, pki=pki)
        ref_manager = Vault__Ref_Manager(vault_path=sg_dir, crypto=self.crypto)
        obj_store   = Vault__Object_Store(vault_path=sg_dir, crypto=self.crypto)

        branch_manager = Vault__Branch_Manager(vault_path    = sg_dir,
                                               crypto        = self.crypto,
                                               key_manager   = key_manager,
                                               ref_manager   = ref_manager,
                                               storage       = storage)

        _p('step', 'Loading branch index')
        index_id = keys['branch_index_file_id']
        if not index_id:
            raise RuntimeError('No branch index found on remote — is this a valid vault?')
        branch_index = branch_manager.load_branch_index(directory, index_id, read_key)

        named_meta = branch_manager.get_branch_by_name(branch_index, 'current')
        if not named_meta:
            raise RuntimeError('Named branch "current" not found on remote')

        named_commit_id = ref_manager.read_ref(str(named_meta.head_ref_id), read_key)

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
        local_config = Schema__Local_Config(my_branch_id=str(clone_branch.branch_id))
        config_path  = storage.local_config_path(directory)
        with open(config_path, 'w') as f:
            json.dump(local_config.json(), f, indent=2)

        with open(storage.vault_key_path(directory), 'w') as f:
            f.write(vault_key)

        if named_commit_id:
            _p('step', 'Verifying objects')
            self._fetch_missing_objects(vault_id, named_commit_id, obj_store, read_key, sg_dir, _p)

            vault_commit = Vault__Commit(crypto=self.crypto, pki=pki,
                                          object_store=obj_store, ref_manager=ref_manager)
            commit_obj = vault_commit.load_commit(named_commit_id, read_key)
            _p('step', 'Extracting working copy')
            sub_tree = Vault__Sub_Tree(crypto=self.crypto, obj_store=obj_store)
            sub_tree.checkout(directory, str(commit_obj.tree_id), read_key)

        return dict(directory    = directory,
                    vault_key    = vault_key,
                    vault_id     = vault_id,
                    branch_id    = str(clone_branch.branch_id),
                    named_branch = str(named_meta.branch_id),
                    commit_id    = named_commit_id or '')

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

    def _init_components(self, directory: str) -> Vault__Components:
        vault_key   = self._read_vault_key(directory)
        keys        = self.crypto.derive_keys_from_vault_key(vault_key)
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
        keys      = self.crypto.derive_keys_from_vault_key(vault_key)
        return keys['read_key_bytes']

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

        batch_ops = []
        for root, dirs, files in os.walk(bare_dir):
            for filename in files:
                full_path = os.path.join(root, filename)
                rel_path  = os.path.relpath(full_path, storage.sg_vault_dir(directory))
                rel_path  = rel_path.replace(os.sep, '/')

                with open(full_path, 'rb') as f:
                    data = f.read()
                batch_ops.append(dict(op      = 'write',
                                      file_id = rel_path,
                                      data    = base64.b64encode(data).decode('ascii')))

        if batch_ops:
            batch = Vault__Batch(crypto=self.crypto, api=self.api)
            try:
                batch.execute_batch(vault_id, write_key, batch_ops)
            except Exception:
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
            except Exception:
                batch.execute_individually(vault_id, write_key, batch_ops)

        os.remove(pending_path)

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
