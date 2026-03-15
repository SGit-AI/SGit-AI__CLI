import hashlib
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
        ref_manager = Vault__Ref_Manager(vault_path=sg_dir, crypto=self.crypto, use_v2=True)
        obj_store   = Vault__Object_Store(vault_path=sg_dir, crypto=self.crypto, use_v2=True)

        branch_manager = Vault__Branch_Manager(vault_path    = sg_dir,
                                               crypto        = self.crypto,
                                               key_manager   = key_manager,
                                               ref_manager   = ref_manager,
                                               storage       = storage)

        timestamp_ms   = int(time.time() * 1000)
        named_branch   = branch_manager.create_named_branch(directory, 'current', read_key,
                                                             timestamp_ms=timestamp_ms)
        clone_branch   = branch_manager.create_clone_branch(directory, 'local', read_key,
                                                             creator_branch_id=str(named_branch.branch_id),
                                                             timestamp_ms=timestamp_ms)

        branch_index = Schema__Branch_Index(schema   = 'branch_index_v1',
                                            branches = [named_branch, clone_branch])
        branch_manager.save_branch_index(directory, branch_index, read_key)

        clone_private_key = key_manager.load_private_key_locally(
            str(clone_branch.public_key_id), storage.local_dir(directory))

        vault_commit = Vault__Commit(crypto=self.crypto, pki=pki,
                                     object_store=obj_store, ref_manager=ref_manager)

        tree_obj = Schema__Object_Tree(schema='tree_v1')
        commit_id = vault_commit.create_commit(tree          = tree_obj,
                                               read_key      = read_key,
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

        index_id = branch_manager.find_branch_index_id(directory)
        if not index_id:
            raise RuntimeError('No branch index found — is this a v2 vault?')
        branch_index = branch_manager.load_branch_index(directory, index_id, read_key)
        branch_meta  = branch_manager.get_branch_by_id(branch_index, branch_id)
        if not branch_meta:
            raise RuntimeError(f'Branch not found: {branch_id}')

        ref_id     = str(branch_meta.head_ref_id)
        parent_id  = ref_manager.read_ref(ref_id, read_key)

        old_tree = Schema__Object_Tree(schema='tree_v1')
        if parent_id:
            vault_commit_reader = Vault__Commit(crypto=self.crypto, pki=pki,
                                                object_store=obj_store, ref_manager=ref_manager)
            old_commit  = vault_commit_reader.load_commit(parent_id, read_key)
            old_tree    = vault_commit_reader.load_tree(str(old_commit.tree_id), read_key)

        new_file_map = self._scan_local_directory(directory)

        old_entries = {}
        for entry in old_tree.entries:
            path = self._entry_path(entry)
            old_entries[path] = entry

        new_tree = Schema__Object_Tree(schema='tree_v1')
        for path in sorted(new_file_map.keys()):
            local_file = os.path.join(directory, path)
            with open(local_file, 'rb') as f:
                content = f.read()

            file_hash = self.crypto.content_hash(content)
            old_entry = old_entries.get(path)
            if old_entry and str(old_entry.content_hash or '') == file_hash:
                new_tree.entries.append(Schema__Object_Tree_Entry(path=path, blob_id=str(old_entry.blob_id),
                                                                  size=len(content), content_hash=file_hash))
            else:
                encrypted = self.crypto.encrypt(read_key, content)
                blob_id   = obj_store.store(encrypted)
                new_tree.entries.append(Schema__Object_Tree_Entry(path=path, blob_id=blob_id,
                                                                  size=len(content), content_hash=file_hash))

        signing_key = None
        try:
            signing_key = key_manager.load_private_key_locally(
                str(branch_meta.public_key_id), storage.local_dir(directory))
        except (FileNotFoundError, Exception):
            pass

        vault_commit = Vault__Commit(crypto=self.crypto, pki=pki,
                                     object_store=obj_store, ref_manager=ref_manager)

        auto_msg = message or self._generate_commit_message(old_entries, new_file_map)
        commit_id = vault_commit.create_commit(tree        = new_tree,
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

        index_id = branch_manager.find_branch_index_id(directory)
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
            old_tree   = vault_commit_reader.load_tree(str(old_commit.tree_id), read_key)
            for entry in old_tree.entries:
                path = self._entry_path(entry)
                old_entries[path] = entry

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
            old_hash   = str(old_entry.content_hash or '') if old_entry.content_hash else ''
            file_hash  = self.crypto.content_hash(content)
            if old_hash and old_hash != file_hash:
                modified.append(path)
            elif not old_hash and len(content) != int(old_entry.size):
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

        index_id = branch_manager.find_branch_index_id(directory)
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
        try:
            remote_ref_data = self.api.read(vault_id, named_ref_file_id)
            if remote_ref_data:
                ref_path = os.path.join(c.sg_dir, named_ref_file_id)
                os.makedirs(os.path.dirname(ref_path), exist_ok=True)
                with open(ref_path, 'wb') as f:
                    f.write(remote_ref_data)
        except Exception:
            pass

        named_commit_id = ref_manager.read_ref(str(named_meta.head_ref_id), read_key)

        if not named_commit_id:
            return dict(status='up_to_date', message='Named branch has no commits')

        if clone_commit_id == named_commit_id:
            return dict(status='up_to_date', message='Already up to date')

        # Fetch any missing objects reachable from the remote commit
        _p('step', 'Downloading missing objects')
        self._fetch_missing_objects(vault_id, named_commit_id, obj_store, read_key, c.sg_dir)

        vault_commit = Vault__Commit(crypto=self.crypto, pki=pki,
                                     object_store=obj_store, ref_manager=ref_manager)
        fetcher      = Vault__Fetch(crypto=self.crypto, api=self.api, storage=storage)
        merger       = Vault__Merge(crypto=self.crypto)

        lca_id = fetcher.find_lca(obj_store, read_key, clone_commit_id, named_commit_id)

        if lca_id == named_commit_id:
            return dict(status='up_to_date', message='Clone branch is ahead of named branch')

        base_tree = Schema__Object_Tree(schema='tree_v1')
        if lca_id:
            lca_commit = vault_commit.load_commit(lca_id, read_key)
            base_tree  = vault_commit.load_tree(str(lca_commit.tree_id), read_key)

        ours_tree = Schema__Object_Tree(schema='tree_v1')
        if clone_commit_id:
            ours_commit = vault_commit.load_commit(clone_commit_id, read_key)
            ours_tree   = vault_commit.load_tree(str(ours_commit.tree_id), read_key)

        named_commit = vault_commit.load_commit(named_commit_id, read_key)
        theirs_tree  = vault_commit.load_tree(str(named_commit.tree_id), read_key)

        _p('step', 'Merging trees')
        merge_result = merger.three_way_merge(base_tree, ours_tree, theirs_tree)
        merged_tree  = merge_result['merged_tree']
        conflicts    = merge_result['conflicts']

        _p('step', 'Updating working copy')
        self._checkout_tree(directory, merged_tree, obj_store, read_key)
        self._remove_deleted_files(directory, ours_tree, merged_tree)

        if conflicts:
            conflict_files = merger.write_conflict_files(directory, conflicts,
                                                         ours_tree, theirs_tree,
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

        parent_ids = [clone_commit_id, named_commit_id]
        parent_ids = [p for p in parent_ids if p]

        merge_commit_id = vault_commit.create_commit(
            tree        = merged_tree,
            read_key    = read_key,
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

        index_id = branch_manager.find_branch_index_id(directory)
        if not index_id:
            raise RuntimeError('No branch index found — is this a v2 vault?')
        branch_index = branch_manager.load_branch_index(directory, index_id, read_key)

        clone_meta = branch_manager.get_branch_by_id(branch_index, clone_branch_id)
        if not clone_meta:
            raise RuntimeError(f'Clone branch not found: {clone_branch_id}')

        named_meta = branch_manager.get_branch_by_name(branch_index, 'current')
        if not named_meta:
            raise RuntimeError('Named branch "current" not found')

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
                    self._upload_bare_to_server(directory, vault_id, write_key, storage)
            except Exception:
                pass
            return dict(status='up_to_date', message='Nothing to push')

        # First push: if server has no files for this vault, upload entire bare structure
        # then continue with the normal delta push (skip pull since server is empty)
        first_push = self._is_first_push(vault_id)
        if first_push:
            _p('step', 'First push — uploading vault structure')
            self._upload_bare_to_server(directory, vault_id, write_key, storage)

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

        clone_commit = vault_commit.load_commit(clone_commit_id, read_key)
        clone_tree   = vault_commit.load_tree(str(clone_commit.tree_id), read_key)

        named_blob_ids = set()
        if named_commit_id:
            named_commit = vault_commit.load_commit(named_commit_id, read_key)
            named_tree   = vault_commit.load_tree(str(named_commit.tree_id), read_key)
            for entry in named_tree.entries:
                if entry.blob_id:
                    named_blob_ids.add(str(entry.blob_id))

        _p('step', 'Computing delta')
        fetcher = Vault__Fetch(crypto=self.crypto, api=self.api, storage=storage)
        commit_chain = fetcher.fetch_commit_chain(obj_store, read_key, clone_commit_id,
                                                   stop_at=named_commit_id)

        batch = Vault__Batch(crypto=self.crypto, api=self.api)
        operations = batch.build_push_operations(
            obj_store          = obj_store,
            ref_manager        = ref_manager,
            clone_tree_entries = list(clone_tree.entries),
            named_blob_ids     = named_blob_ids,
            commit_chain       = commit_chain,
            named_commit_id    = named_commit_id,
            read_key           = read_key,
            named_ref_id       = named_ref_id,
            clone_commit_id    = clone_commit_id,
            expected_ref_hash  = expected_ref_hash)

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

        clone_commit = vault_commit.load_commit(clone_commit_id, read_key)
        clone_tree   = vault_commit.load_tree(str(clone_commit.tree_id), read_key)

        fetcher = Vault__Fetch(crypto=self.crypto, api=self.api, storage=storage)
        commit_chain = fetcher.fetch_commit_chain(obj_store, read_key, clone_commit_id,
                                                   stop_at=None)

        clone_ref_id      = str(clone_meta.head_ref_id)
        expected_ref_hash = ref_manager.get_ref_file_hash(clone_ref_id)

        batch = Vault__Batch(crypto=self.crypto, api=self.api)
        operations = batch.build_push_operations(
            obj_store          = obj_store,
            ref_manager        = ref_manager,
            clone_tree_entries = list(clone_tree.entries),
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
            ours_tree   = vault_commit.load_tree(str(ours_commit.tree_id), read_key)
            self._checkout_tree(directory, ours_tree, obj_store, read_key)

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

        index_id = branch_manager.find_branch_index_id(directory)
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
        return gc.drain_pending(directory, read_key, clone_branch_id)

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
        ref_manager = Vault__Ref_Manager(vault_path=sg_dir, crypto=self.crypto, use_v2=True)
        obj_store   = Vault__Object_Store(vault_path=sg_dir, crypto=self.crypto, use_v2=True)

        branch_manager = Vault__Branch_Manager(vault_path    = sg_dir,
                                               crypto        = self.crypto,
                                               key_manager   = key_manager,
                                               ref_manager   = ref_manager,
                                               storage       = storage)

        _p('step', 'Loading branch index')
        index_id = branch_manager.find_branch_index_id(directory)
        if not index_id:
            raise RuntimeError('No branch index found on remote — is this a valid vault?')
        branch_index = branch_manager.load_branch_index(directory, index_id, read_key)
        branch_index.index_id = index_id

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
        branch_manager.save_branch_index(directory, branch_index, read_key)

        import base64
        batch_ops = []

        index_path = storage.index_path(directory, str(branch_index.index_id))
        with open(index_path, 'rb') as f:
            index_data = f.read()
        batch_ops.append(dict(op      = 'write',
                              file_id = f'bare/indexes/{branch_index.index_id}',
                              data    = base64.b64encode(index_data).decode('ascii')))

        if named_commit_id:
            ref_ciphertext = ref_manager.encrypt_ref_value(named_commit_id, read_key)
            batch_ops.append(dict(op      = 'write',
                                  file_id = f'bare/refs/{clone_branch.head_ref_id}',
                                  data    = base64.b64encode(ref_ciphertext).decode('ascii')))

        pub_key_path = storage.key_path(directory, str(clone_branch.public_key_id))
        if os.path.isfile(pub_key_path):
            with open(pub_key_path, 'rb') as f:
                pub_key_data = f.read()
            batch_ops.append(dict(op      = 'write',
                                  file_id = f'bare/keys/{clone_branch.public_key_id}',
                                  data    = base64.b64encode(pub_key_data).decode('ascii')))

        if batch_ops:
            _p('step', 'Registering clone branch on remote', f'{len(batch_ops)} objects')
            batch = Vault__Batch(crypto=self.crypto, api=self.api)
            try:
                batch.execute_batch(vault_id, write_key, batch_ops)
            except Exception:
                batch.execute_individually(vault_id, write_key, batch_ops)

        _p('step', 'Setting up local config')
        local_config = Schema__Local_Config(my_branch_id=str(clone_branch.branch_id))
        config_path  = storage.local_config_path(directory)
        with open(config_path, 'w') as f:
            json.dump(local_config.json(), f, indent=2)

        with open(storage.vault_key_path(directory), 'w') as f:
            f.write(vault_key)

        if named_commit_id:
            vault_commit = Vault__Commit(crypto=self.crypto, pki=pki,
                                          object_store=obj_store, ref_manager=ref_manager)
            commit_obj = vault_commit.load_commit(named_commit_id, read_key)
            tree_obj   = vault_commit.load_tree(str(commit_obj.tree_id), read_key)
            _p('step', 'Extracting working copy', f'{len(tree_obj.entries)} files')
            self._checkout_tree(directory, tree_obj, obj_store, read_key)

        return dict(directory    = directory,
                    vault_key    = vault_key,
                    vault_id     = vault_id,
                    branch_id    = str(clone_branch.branch_id),
                    named_branch = str(named_meta.branch_id),
                    commit_id    = named_commit_id or '')

    def _checkout_tree(self, directory: str, tree: Schema__Object_Tree,
                       obj_store: Vault__Object_Store, read_key: bytes) -> None:
        """Write all files from a tree to the working directory."""
        for entry in tree.entries:
            path    = self._entry_path(entry)
            blob_id = str(entry.blob_id) if entry.blob_id else None
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

    def _remove_deleted_files(self, directory: str, old_tree: Schema__Object_Tree,
                              new_tree: Schema__Object_Tree) -> None:
        """Remove files that exist in old_tree but not in new_tree."""
        old_paths = set()
        for entry in old_tree.entries:
            path = self._entry_path(entry)
            old_paths.add(path)

        new_paths = set()
        for entry in new_tree.entries:
            path = self._entry_path(entry)
            new_paths.add(path)

        for path in old_paths - new_paths:
            full_path = os.path.join(directory, path)
            if os.path.isfile(full_path):
                os.remove(full_path)

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
            old_hash  = str(old_entry.content_hash or '') if hasattr(old_entry, 'content_hash') and old_entry.content_hash else ''
            new_hash  = new_file_map[path].get('content_hash', '')
            if old_hash and new_hash:
                if old_hash != new_hash:
                    modified += 1
            else:
                old_size = int(old_entry.size) if hasattr(old_entry, 'size') else -1
                new_size = new_file_map[path].get('size', -2)
                if old_size != new_size:
                    modified += 1
        return f'Commit: {added} added, {modified} modified, {deleted} deleted'

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

    def _entry_path(self, entry: Schema__Object_Tree_Entry) -> str:
        return str(entry.path) if entry.path else str(entry.name)

    def _init_components(self, directory: str) -> Vault__Components:
        vault_key   = self._read_vault_key(directory)
        keys        = self.crypto.derive_keys_from_vault_key(vault_key)
        sg_dir      = os.path.join(directory, SG_VAULT_DIR)
        storage     = Vault__Storage()
        pki         = PKI__Crypto()
        obj_store   = Vault__Object_Store(vault_path=sg_dir, crypto=self.crypto, use_v2=True)
        ref_manager = Vault__Ref_Manager(vault_path=sg_dir, crypto=self.crypto, use_v2=True)
        key_manager = Vault__Key_Manager(vault_path=sg_dir, crypto=self.crypto, pki=pki)
        branch_manager = Vault__Branch_Manager(vault_path=sg_dir, crypto=self.crypto,
                                               key_manager=key_manager, ref_manager=ref_manager,
                                               storage=storage)
        return Vault__Components(vault_key      = vault_key,
                                 vault_id       = keys['vault_id'],
                                 read_key       = keys['read_key_bytes'],
                                 write_key      = keys['write_key'],
                                 sg_dir         = sg_dir,
                                 storage        = storage,
                                 pki            = pki,
                                 obj_store      = obj_store,
                                 ref_manager    = ref_manager,
                                 key_manager    = key_manager,
                                 branch_manager = branch_manager)

    def _fetch_missing_objects(self, vault_id: str, commit_id: str,
                               obj_store: Vault__Object_Store, read_key: bytes,
                               sg_dir: str) -> None:
        """Walk the commit chain from commit_id, downloading any missing objects."""
        pki = PKI__Crypto()
        vc  = Vault__Commit(crypto=self.crypto, pki=pki,
                            object_store=obj_store, ref_manager=Vault__Ref_Manager())
        visited = set()
        queue   = [commit_id]

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

                tree = vc.load_tree(tree_id, read_key) if obj_store.exists(tree_id) else None
                if tree:
                    for entry in tree.entries:
                        blob_id = str(entry.blob_id) if entry.blob_id else None
                        if blob_id and not obj_store.exists(blob_id):
                            try:
                                data = self.api.read(vault_id, f'bare/data/{blob_id}')
                                if data:
                                    local_path = os.path.join(sg_dir, 'bare', 'data', blob_id)
                                    os.makedirs(os.path.dirname(local_path), exist_ok=True)
                                    with open(local_path, 'wb') as f:
                                        f.write(data)
                            except Exception:
                                pass

                parents = list(commit.parents) if commit.parents else []
                if not parents and commit.parent:
                    parents = [str(commit.parent)]
                for pid in parents:
                    if str(pid) not in visited:
                        queue.append(str(pid))
            except Exception:
                pass

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
                               write_key: str, storage: Vault__Storage) -> None:
        """Upload all bare/ files to the remote server.

        Walks .sg_vault/bare/ and uploads each file with its relative path
        (e.g. bare/data/obj-xxx, bare/refs/ref-xxx, bare/keys/key-xxx).
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

    def _scan_local_directory(self, directory: str) -> dict:
        result = {}
        for root, dirs, files in os.walk(directory):
            dirs[:] = [d for d in dirs if d != SG_VAULT_DIR and not d.startswith('.')]
            for filename in files:
                if filename.startswith('.'):
                    continue
                full_path = os.path.join(root, filename)
                rel_path  = os.path.relpath(full_path, directory)
                rel_path  = rel_path.replace(os.sep, '/')
                file_size = os.path.getsize(full_path)
                with open(full_path, 'rb') as f:
                    file_hash = hashlib.sha256(f.read()).hexdigest()[:12]
                result[rel_path] = dict(size=file_size, content_hash=file_hash)
        return result
