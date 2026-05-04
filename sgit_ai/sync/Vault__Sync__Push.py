"""Vault__Sync__Push — push operations and upload helpers (Brief 22 — E5)."""
import base64
import json
import os
import stat
import sys
from   sgit_ai.api.Vault__API                     import Vault__API, LARGE_BLOB_THRESHOLD
from   sgit_ai.crypto.PKI__Crypto                 import PKI__Crypto
from   sgit_ai.storage.Vault__Commit              import Vault__Commit
from   sgit_ai.storage.Vault__Object_Store        import Vault__Object_Store
from   sgit_ai.storage.Vault__Ref_Manager         import Vault__Ref_Manager
from   sgit_ai.safe_types.Safe_Str__Object_Id     import Safe_Str__Object_Id
from   sgit_ai.schemas.Schema__Push_State         import Schema__Push_State
from   sgit_ai.sync.Vault__Batch                  import Vault__Batch
from   sgit_ai.sync.Vault__Fetch                  import Vault__Fetch
from   sgit_ai.storage.Vault__Storage                import Vault__Storage
from   sgit_ai.storage.Vault__Sub_Tree               import Vault__Sub_Tree
from   sgit_ai.sync.Vault__Sync__Base             import Vault__Sync__Base


class Vault__Sync__Push(Vault__Sync__Base):

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
        from sgit_ai.sync.Vault__Sync__Status import Vault__Sync__Status
        from sgit_ai.sync.Vault__Sync__Pull   import Vault__Sync__Pull
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

        self._register_pending_branch(directory, vault_id, write_key,
                                      read_key, storage, ref_manager, _p)

        _p('step', 'Checking for uncommitted changes')
        local_status = Vault__Sync__Status(crypto=self.crypto, api=self.api).status(directory)
        if not local_status['clean']:
            raise RuntimeError('Working directory has uncommitted changes. '
                               'Commit your changes before pushing.')

        clone_commit_id = ref_manager.read_ref(str(clone_meta.head_ref_id), read_key)
        named_commit_id = ref_manager.read_ref(str(named_meta.head_ref_id), read_key)

        if not clone_commit_id:
            return dict(status='up_to_date', message='No commits to push')

        if clone_commit_id == named_commit_id:
            if not self._commit_tree_is_empty(clone_commit_id, obj_store, read_key):
                named_ref_id_str = str(named_meta.head_ref_id)
                if (self._is_first_push(vault_id) or
                        not self._server_has_named_ref(vault_id, named_ref_id_str)):
                    _p('step', 'Re-syncing vault structure to server')
                    self._upload_bare_to_server(directory, vault_id, write_key, storage, read_key)
                    return dict(status='resynced', message='Vault structure re-synced to server')
            return dict(status='up_to_date', message='Nothing to push')

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
            pull_result = Vault__Sync__Pull(crypto=self.crypto, api=self.api).pull(directory)
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

        new_commits = [cid for cid in commit_chain if cid != named_commit_id]

        clone_tree_entries = list(clone_flat.values())

        batch = Vault__Batch(crypto=self.crypto, api=self.api)

        _new_blob_id_set = set()
        for _e in clone_tree_entries:
            _bid = _e.get('blob_id') if isinstance(_e, dict) else (str(_e.blob_id) if hasattr(_e, 'blob_id') and _e.blob_id else None)
            if _bid and _bid not in named_blob_ids:
                _new_blob_id_set.add(_bid)

        # === Phase A: Upload blobs with per-blob checkpointing ===
        large_uploaded       = 0
        small_blobs_uploaded = 0
        uploaded_blob_ids    = set(named_blob_ids)

        if not first_push:
            state_path   = storage.push_state_path(directory)
            push_state   = self._load_push_state(state_path, vault_id, clone_commit_id)
            already_done = set(str(b) for b in push_state.blobs_uploaded)

            seen_in_pass = set()
            new_blob_ids = []
            for entry in clone_tree_entries:
                bid = entry.get('blob_id') if isinstance(entry, dict) else None
                if bid and bid not in named_blob_ids and bid not in seen_in_pass:
                    seen_in_pass.add(bid)
                    new_blob_ids.append(bid)

            to_upload    = [bid for bid in new_blob_ids if bid not in already_done]
            skipped_done = len(already_done & set(new_blob_ids))
            if new_blob_ids:
                resume_note = f', {skipped_done} already uploaded' if skipped_done else ''
                _p('step', f'Blobs: {len(to_upload)}/{len(new_blob_ids)} to upload{resume_note}')

            small_blob_ops = []
            for bid in to_upload:
                ciphertext = obj_store.load(bid)
                if len(ciphertext) > LARGE_BLOB_THRESHOLD:
                    uploaded = batch._upload_large(vault_id, f'bare/data/{bid}',
                                                   ciphertext, write_key, on_progress)
                    if uploaded:
                        large_uploaded += 1
                        push_state.blobs_uploaded.append(Safe_Str__Object_Id(bid))
                        self._save_push_state(state_path, push_state)
                        uploaded_blob_ids.add(bid)
                    else:
                        small_blob_ops.append(dict(op      = 'write',
                                                   file_id = f'bare/data/{bid}',
                                                   data    = base64.b64encode(ciphertext).decode('ascii')))
                else:
                    small_blob_ops.append(dict(op      = 'write',
                                               file_id = f'bare/data/{bid}',
                                               data    = base64.b64encode(ciphertext).decode('ascii')))

            if small_blob_ops:
                if use_batch:
                    try:
                        batch.execute_batch(vault_id, write_key, small_blob_ops)
                    except Exception:
                        batch.execute_individually(vault_id, write_key, small_blob_ops)
                else:
                    batch.execute_individually(vault_id, write_key, small_blob_ops)
                small_blobs_uploaded = len(small_blob_ops)
                for op in small_blob_ops:
                    bid = op['file_id'].replace('bare/data/', '')
                    push_state.blobs_uploaded.append(Safe_Str__Object_Id(bid))
                    uploaded_blob_ids.add(bid)
                self._save_push_state(state_path, push_state)

            uploaded_blob_ids.update(already_done)

        # === Phase B: Upload commits, trees, and ref ===
        operations, _ = batch.build_push_operations(
            obj_store          = obj_store,
            ref_manager        = ref_manager,
            clone_tree_entries = clone_tree_entries,
            named_blob_ids     = uploaded_blob_ids,
            commit_chain       = commit_chain,
            named_commit_id    = named_commit_id,
            read_key           = read_key,
            named_ref_id       = named_ref_id,
            clone_commit_id    = clone_commit_id,
            expected_ref_hash  = expected_ref_hash,
            vault_id           = vault_id,
            write_key          = write_key,
            on_progress        = on_progress,
            force              = force)

        commit_and_tree_ids = set()
        for cid in new_commits:
            commit_and_tree_ids.add(cid)
            chain_commit = vault_commit.load_commit(cid, read_key)
            commit_and_tree_ids.add(str(chain_commit.tree_id))

        blob_count   = len(_new_blob_id_set)
        commit_count = len(new_commits)

        if first_push:
            operations = [op for op in operations if op['op'] == 'write-if-match']

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

        if not first_push:
            self._clear_push_state(state_path)

        return dict(status           = 'pushed',
                    commit_id        = clone_commit_id,
                    objects_uploaded = blob_count,
                    commits_pushed   = commit_count)

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

        _p = lambda *a, **k: None  # noqa: E731 — branch_only has no progress callback
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

    def _load_push_state(self, path: str, vault_id: str, clone_commit_id: str) -> Schema__Push_State:
        """Load a push checkpoint if it matches the current push context, else start fresh."""
        if os.path.isfile(path):
            try:
                with open(path, 'r') as f:
                    raw = json.load(f)
                state = Schema__Push_State.from_json(raw)
                if (str(state.vault_id) == vault_id and
                        str(state.clone_commit_id) == clone_commit_id):
                    return state
            except Exception:
                pass
        return Schema__Push_State(vault_id=vault_id, clone_commit_id=clone_commit_id)

    def _save_push_state(self, path: str, state: Schema__Push_State) -> None:
        with open(path, 'w') as f:
            json.dump(state.json(), f)
        try:
            os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            pass

    def _clear_push_state(self, path: str) -> None:
        if os.path.isfile(path):
            os.remove(path)

    def _server_has_named_ref(self, vault_id: str, named_ref_id: str) -> bool:
        """Check whether the named branch ref exists on the server."""
        try:
            remote_refs = self.api.list_files(vault_id, 'bare/refs/')
            return any(named_ref_id in f for f in remote_refs)
        except Exception:
            return False

    def _upload_bare_to_server(self, directory: str, vault_id: str,
                               write_key: str, storage: Vault__Storage,
                               read_key: bytes = None) -> None:
        """Upload all bare/ files to the remote server.

        Walks .sg_vault/bare/ and uploads each file with its relative path.
        Used on first push to bootstrap the vault on the server.
        """
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

        for file_id, data in large_files:
            if not batch._upload_large(vault_id, file_id, data, write_key):
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
        """Upload clone branch metadata to the server if not yet registered."""
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
