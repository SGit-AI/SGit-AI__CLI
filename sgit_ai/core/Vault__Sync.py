import json
import os
import secrets
import string
import time
from   sgit_ai.crypto.Vault__Crypto              import Vault__Crypto
from   sgit_ai.crypto.PKI__Crypto                import PKI__Crypto
from   sgit_ai.crypto.Vault__Key_Manager         import Vault__Key_Manager
from   sgit_ai.network.api.Vault__API                    import Vault__API
from   sgit_ai.storage.Vault__Storage               import Vault__Storage, SG_VAULT_DIR
from   sgit_ai.storage.Vault__Branch_Manager        import Vault__Branch_Manager
from   sgit_ai.storage.Vault__Sub_Tree              import Vault__Sub_Tree
from   sgit_ai.storage.Vault__Object_Store       import Vault__Object_Store
from   sgit_ai.storage.Vault__Ref_Manager        import Vault__Ref_Manager
from   sgit_ai.storage.Vault__Commit             import Vault__Commit
from   sgit_ai.schemas.Schema__Object_Tree       import Schema__Object_Tree
from   sgit_ai.schemas.Schema__Branch_Index      import Schema__Branch_Index
from   sgit_ai.schemas.Schema__Local_Config      import Schema__Local_Config
from   sgit_ai.core.Vault__Sync__Base            import Vault__Sync__Base
from   sgit_ai.core.actions.commit.Vault__Sync__Commit          import Vault__Sync__Commit
from   sgit_ai.core.actions.pull.Vault__Sync__Pull            import Vault__Sync__Pull
from   sgit_ai.core.actions.push.Vault__Sync__Push            import Vault__Sync__Push
from   sgit_ai.core.actions.status.Vault__Sync__Status          import Vault__Sync__Status
from   osbot_utils.type_safe.primitives.core.Safe_UInt           import Safe_UInt
from   sgit_ai.core.actions.clone.Vault__Sync__Clone           import Vault__Sync__Clone
from   sgit_ai.core.actions.branch.Vault__Sync__Branch_Ops      import Vault__Sync__Branch_Ops
from   sgit_ai.core.actions.gc.Vault__Sync__GC_Ops          import Vault__Sync__GC_Ops
from   sgit_ai.core.actions.lifecycle.Vault__Sync__Lifecycle       import Vault__Sync__Lifecycle
from   sgit_ai.core.actions.sparse.Vault__Sync__Sparse          import Vault__Sync__Sparse
from   sgit_ai.core.actions.fsck.Vault__Sync__Fsck            import Vault__Sync__Fsck
from   sgit_ai.core.actions.scope.Vault__Sync__Scope          import Vault__Sync__Scope


class Vault__Sync(Vault__Sync__Base):
    crypto       : Vault__Crypto
    api          : Vault__API
    commit_fetch_limit : Safe_UInt = 50     # new remote commits `status` fetches to count behind exactly

    def generate_vault_key(self) -> str:
        alphabet   = string.ascii_lowercase + string.digits
        passphrase = ''.join(secrets.choice(alphabet) for _ in range(24))
        vault_id   = ''.join(secrets.choice(alphabet) for _ in range(8))
        return f'{passphrase}:{vault_id}'

    def init(self, directory: str, vault_key: str = None,
             allow_nonempty: bool = False) -> dict:
        """Initialise a new vault."""
        if os.path.exists(directory):
            entries = [e for e in os.listdir(directory) if e != SG_VAULT_DIR]
            if entries and not allow_nonempty:
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
                                               author_key_id = str(clone_branch.public_key_id) if clone_branch.public_key_id else None,
                                               timestamp_ms  = timestamp_ms)

        ref_manager.write_ref(str(named_branch.head_ref_id), commit_id, read_key)
        ref_manager.write_ref(str(clone_branch.head_ref_id), commit_id, read_key)

        local_config = Schema__Local_Config(
            my_branch_id = str(clone_branch.branch_id),
            mode         = None,
        )
        config_path  = storage.local_config_path(directory)
        storage.write_local_config(directory, local_config.json())

        # Stored and returned in the self-identifying prefixed form (sgit_private_vault_…)
        # so scanners/hooks can recognise it; the value after the prefix is the
        # legacy key unchanged, and every reader strips it via parse_vault_key.
        vault_key_display = self.crypto.format_vault_key(vault_key)
        vault_key_path    = storage.vault_key_path(directory)
        storage.write_private(vault_key_path, vault_key_display)

        return dict(directory    = directory,
                    vault_key    = vault_key_display,
                    vault_id     = vault_id,
                    branch_id    = str(clone_branch.branch_id),
                    named_branch = str(named_branch.branch_id),
                    commit_id    = commit_id)

    def commit(self, directory: str, message: str = '', allow_deletions: bool = False, amend: bool = False,
               allow_secret_files: list = None) -> dict:
        kw = dict(amend=True) if amend else {}
        if allow_secret_files:
            kw['allow_secret_files'] = list(allow_secret_files)
        return Vault__Sync__Commit(crypto=self.crypto, api=self.api).commit(
            directory, message, allow_deletions=allow_deletions, **kw)

    def switch_branch(self, directory: str, name: str, force: bool = False, on_progress: callable = None) -> dict:
        """`sgit branch switch`: refresh the branch index from the server (a teammate's
        new branch is not local yet), switch, then pull the entered branch. Offline,
        the switch still happens from what this clone has; result['pull'] says why not."""
        from sgit_ai.core.actions.branch.Vault__Branch_Switch import Vault__Branch_Switch
        from sgit_ai.core.actions.index.Vault__Index_Sync     import Vault__Index_Sync
        try:
            Vault__Index_Sync(crypto=self.crypto, api=self.api).refresh(self._init_components(directory), directory)
        except Exception:
            pass
        self._fetch_branch_for_switch(directory, name)
        result = Vault__Branch_Switch(crypto=self.crypto).switch(directory, name, force=force)
        from sgit_ai.core.Vault__Errors import Vault__Ref_Rewind_Error, Vault__Signature_Error
        try:
            result['pull'] = self.pull(directory, on_progress=on_progress)
        except (Vault__Ref_Rewind_Error, Vault__Signature_Error) as error:   # refused on purpose: the switch
            result['pull'] = dict(status='error', error=str(error), refused=True)   # happened, the branch did not update
        except Exception as error:
            result['pull'] = dict(status='error', error=str(error))
        return result

    def _fetch_branch_for_switch(self, directory: str, name: str) -> None:
        """A branch this clone never fetched has no commit, tree or blob here: the switch
        checked out nothing and left the old branch's files behind (review S3). Fetch
        the branch's server head first. Its local ref and baseline are written only after
        the signature policy has passed (verify-then-accept, review d3b8eef N2): writing
        them first let the switch check out an unsigned head and the pull after it take
        that head as already held. A refusal raises; offline, the switch goes ahead from
        what this clone has."""
        import json
        from sgit_ai.core.actions.pull.Vault__Incoming_Check import Vault__Incoming_Check
        try:
            c     = self._init_components(directory)
            index = c.branch_manager.load_branch_index(directory, c.branch_index_file_id, c.read_key)
            meta  = c.branch_manager.get_branch_by_name(index, name) or c.branch_manager.get_branch_by_id(index, name)
            if meta is None or not meta.head_ref_id:
                return
            ref_id = str(meta.head_ref_id)
            if c.ref_manager.read_ref(ref_id, c.read_key) or self._read_remote_baseline(directory, c.storage, ref_id):
                return                                             # known branch: the pull after the switch guards its moves
            raw    = self.api.read(str(c.vault_id), f'bare/refs/{ref_id}')
            head   = json.loads(self.crypto.decrypt(c.read_key, raw)).get('commit_id') if raw else ''
            if not head:
                return
            from sgit_ai.core.actions.pull.Vault__Sync__Pull import Vault__Sync__Pull
            Vault__Sync__Pull(crypto=self.crypto, api=self.api)._fetch_missing_objects(
                str(c.vault_id), head, c.obj_store, c.read_key, c.sg_dir, include_blobs=True)
            config = self._read_local_config(directory, c.storage)
            mine   = c.branch_manager.get_branch_by_id(index, str(config.my_branch_id or ''))
            held   = c.ref_manager.read_ref(str(mine.head_ref_id), c.read_key) if mine else ''
        except Exception:
            return                                                 # offline: switch from what this clone has
        Vault__Incoming_Check(crypto=self.crypto, api=self.api).require_signatures(   # refusal: nothing written
            directory, c, c.read_key, head, held or '')
        if c.obj_store.exists(head):
            ref_path = os.path.join(c.sg_dir, 'bare', 'refs', ref_id)
            os.makedirs(os.path.dirname(ref_path), exist_ok=True)
            with open(ref_path, 'wb') as f:                        # the server's bytes: push's compare-and-swap uses them
                f.write(raw)
            self._write_remote_baseline(directory, c.storage, ref_id, head)

    def merge_branch(self, directory: str, name: str, on_progress: callable = None) -> dict:
        """Merge the named branch `name` (as the server has it) into this clone's head.
        Fast-forward when possible, else a merge commit; conflicts are left for
        `sgit resolve` + `sgit commit`, exactly like a pull."""
        return Vault__Sync__Pull(crypto=self.crypto, api=self.api).pull(directory, on_progress, merge_from=name)

    def undo(self, directory: str, force: bool = False) -> dict:
        from sgit_ai.core.actions.history.Vault__Sync__History_Edit import Vault__Sync__History_Edit
        return Vault__Sync__History_Edit(crypto=self.crypto, api=self.api).undo(directory, force=force)

    def revert_commit(self, directory: str, spec: str, message: str = '') -> dict:
        from sgit_ai.core.actions.history.Vault__Sync__History_Edit import Vault__Sync__History_Edit
        return Vault__Sync__History_Edit(crypto=self.crypto, api=self.api).revert_commit(directory, spec, message)

    def resolve_revision(self, directory: str, spec: str) -> str:
        from sgit_ai.core.actions.history.Vault__Revision import Vault__Revision
        return Vault__Revision(crypto=self.crypto, api=self.api).resolve(directory, spec)

    def write_file(self, directory: str, path: str, content: bytes,
                   message: str = '', also: dict = None) -> dict:
        return Vault__Sync__Commit(crypto=self.crypto, api=self.api).write_file(
            directory, path, content, message, also)

    def reset(self, directory: str, commit_id: str = None) -> dict:
        return Vault__Sync__Pull(crypto=self.crypto, api=self.api).reset(directory, commit_id)

    def status(self, directory: str) -> dict:
        return Vault__Sync__Status(crypto=self.crypto, api=self.api,
                                   commit_fetch_limit=self.commit_fetch_limit).status(directory)

    def pull(self, directory: str, on_progress: callable = None, accept_rewind: bool = False) -> dict:
        return Vault__Sync__Pull(crypto=self.crypto, api=self.api).pull(directory, on_progress, accept_rewind=accept_rewind)

    def format_info(self, directory: str) -> dict:
        from sgit_ai.core.actions.format.Vault__Sync__Format import Vault__Sync__Format
        return Vault__Sync__Format(crypto=self.crypto, api=self.api).format_info(directory)

    def set_format(self, directory: str, format: int = None, min_client: str = None,
                   add_features: list = None, remove_features: list = None, on_progress: callable = None) -> dict:
        from sgit_ai.core.actions.format.Vault__Sync__Format import Vault__Sync__Format
        return Vault__Sync__Format(crypto=self.crypto, api=self.api).set_format(
            directory, format=format, min_client=min_client, add_features=add_features,
            remove_features=remove_features, on_progress=on_progress)

    def verify_signatures(self, directory: str, limit: int = 0) -> dict:
        """Classify every commit reachable from the clone head: verified / bad / unsigned / no-key."""
        from sgit_ai.core.actions.verify.Vault__Signatures import Vault__Signatures
        c      = self._init_components(directory)
        index  = c.branch_manager.load_branch_index(directory, c.branch_index_file_id, c.read_key)
        config = self._read_local_config(directory, c.storage)
        meta   = (c.branch_manager.get_branch_by_id(index, str(config.my_branch_id)) if config.my_branch_id
                  else c.branch_manager.get_branch_by_name(index, 'current'))
        head   = c.ref_manager.read_ref(str(meta.head_ref_id), c.read_key) if meta else ''
        from sgit_ai.storage.Vault__Scope import Vault__Scope
        stop   = set(Vault__Scope().from_local_config(config).boundary_ids())
        from sgit_ai.core.actions.verify.Vault__Key_Fetch import Vault__Key_Fetch
        key_fetch = Vault__Key_Fetch(crypto=self.crypto, api=self.api)       # keys of teammates registered after this clone
        key_fetch.fetch_missing(c, key_fetch.branch_key_ids(index))
        return Vault__Signatures(crypto=self.crypto, key_fetch=key_fetch).verify_chain(
            c, c.read_key, head or '', boundaries=stop, limit=limit, index=index)

    def tag_list(self, directory: str, refresh: bool = True) -> list:
        from sgit_ai.core.actions.tag.Vault__Sync__Tag import Vault__Sync__Tag
        return Vault__Sync__Tag(crypto=self.crypto, api=self.api).list_tags(directory, refresh=refresh)

    def tag_create(self, directory: str, name: str, commit_id: str = None, message: str = '', force: bool = False) -> dict:
        from sgit_ai.core.actions.tag.Vault__Sync__Tag import Vault__Sync__Tag
        return Vault__Sync__Tag(crypto=self.crypto, api=self.api).create(directory, name, commit_id, message, force)

    def tag_show(self, directory: str, name: str) -> dict:
        from sgit_ai.core.actions.tag.Vault__Sync__Tag import Vault__Sync__Tag
        return Vault__Sync__Tag(crypto=self.crypto, api=self.api).show(directory, name)

    def tag_delete(self, directory: str, name: str) -> dict:
        from sgit_ai.core.actions.tag.Vault__Sync__Tag import Vault__Sync__Tag
        return Vault__Sync__Tag(crypto=self.crypto, api=self.api).delete(directory, name)

    def reflog(self, directory: str, all_refs: bool = False, limit: int = 0) -> list:
        """Where this clone's head (or, with all_refs, every local ref) has pointed,
        newest first: dict(timestamp_ms, ref, old, new, message)."""
        from sgit_ai.storage.Vault__Reflog import Vault__Reflog
        from sgit_ai.storage.Vault__Commit import Vault__Commit
        c      = self._init_components(directory)
        index  = c.branch_manager.load_branch_index(directory, c.branch_index_file_id, c.read_key)
        config = self._read_local_config(directory, c.storage)
        names  = {str(b.head_ref_id): str(b.name) for b in index.branches if b.head_ref_id}
        mine   = c.branch_manager.get_branch_by_id(index, str(config.my_branch_id)) if config.my_branch_id else None
        ref_id = None if all_refs or mine is None else str(mine.head_ref_id)
        vc     = Vault__Commit(crypto=self.crypto, pki=c.pki, object_store=c.obj_store, ref_manager=c.ref_manager)
        out    = []
        for e in Vault__Reflog(vault_path=c.sg_dir).entries(ref_id):
            message = ''
            try:
                commit  = vc.load_commit(str(e.new_commit), c.read_key) if e.new_commit else None
                message = self.crypto.decrypt_metadata(c.read_key, str(commit.message_enc)) if commit and commit.message_enc else ''
            except Exception:
                pass
            out.append(dict(timestamp_ms = int(e.timestamp_ms), ref = names.get(str(e.ref_id), str(e.ref_id)),
                            old = str(e.old_commit or ''), new = str(e.new_commit or ''), message = message or ''))
            if limit and len(out) >= limit:
                break
        return out

    def pull_read_only(self, directory: str, on_progress: callable = None, accept_rewind: bool = False) -> dict:
        return Vault__Sync__Pull(crypto=self.crypto, api=self.api).pull_read_only(directory, on_progress, accept_rewind=accept_rewind)

    def fetch(self, directory: str, on_progress: callable = None) -> dict:
        from sgit_ai.core.actions.fetch.Vault__Sync__Fetch import Vault__Sync__Fetch
        return Vault__Sync__Fetch(crypto=self.crypto, api=self.api).fetch(directory, on_progress)

    def push(self, directory: str, message: str = '', force: bool = False,
             use_batch: bool = True, branch_only: bool = False,
             on_progress: callable = None, lease: str = None) -> dict:
        kw = dict(lease=lease) if lease is not None else {}
        return Vault__Sync__Push(crypto=self.crypto, api=self.api).push(
            directory, message, force, use_batch, branch_only, on_progress, **kw)

    def merge_abort(self, directory: str) -> dict:
        return Vault__Sync__Branch_Ops(crypto=self.crypto, api=self.api).merge_abort(directory)

    def branches(self, directory: str) -> dict:
        return Vault__Sync__Branch_Ops(crypto=self.crypto, api=self.api).branches(directory)

    def gc_drain(self, directory: str) -> dict:
        return Vault__Sync__GC_Ops(crypto=self.crypto, api=self.api).gc_drain(directory)

    def create_change_pack(self, directory: str, files: dict) -> dict:
        return Vault__Sync__GC_Ops(crypto=self.crypto, api=self.api).create_change_pack(directory, files)

    def remote_add(self, directory: str, name: str, url: str, vault_id: str) -> dict:
        return Vault__Sync__Branch_Ops(crypto=self.crypto, api=self.api).remote_add(directory, name, url, vault_id)

    def remote_remove(self, directory: str, name: str) -> dict:
        return Vault__Sync__Branch_Ops(crypto=self.crypto, api=self.api).remote_remove(directory, name)

    def remote_list(self, directory: str) -> dict:
        return Vault__Sync__Branch_Ops(crypto=self.crypto, api=self.api).remote_list(directory)

    def clone(self, vault_key: str, directory: str, on_progress: callable = None, sparse: bool = False,
              depth: int = 0, scope_paths: list = None) -> dict:
        return Vault__Sync__Clone(crypto=self.crypto, api=self.api).clone(
            vault_key, directory, on_progress, sparse, depth=depth, scope_paths=scope_paths)

    def clone_branch(self, vault_key: str, directory: str,
                     on_progress: callable = None, bare: bool = False) -> dict:
        return Vault__Sync__Clone(crypto=self.crypto, api=self.api).clone_branch(
            vault_key, directory, on_progress, bare)

    def clone_headless(self, vault_key: str, directory: str,
                       on_progress: callable = None) -> dict:
        return Vault__Sync__Clone(crypto=self.crypto, api=self.api).clone_headless(
            vault_key, directory, on_progress)

    def clone_range(self, vault_key: str, directory: str, range_from: str = '',
                    range_to: str = '', on_progress: callable = None,
                    bare: bool = False) -> dict:
        return Vault__Sync__Clone(crypto=self.crypto, api=self.api).clone_range(
            vault_key, directory, range_from, range_to, on_progress, bare)

    # --- partial clones (scope / depth) ---
    def scope_of(self, directory: str):
        return Vault__Sync__Scope(crypto=self.crypto, api=self.api).scope_of(directory)

    def require_whole(self, directory: str, command: str) -> None:
        Vault__Sync__Scope(crypto=self.crypto, api=self.api).require_whole(directory, command)

    def widen(self, directory: str, folder: str, on_progress: callable = None) -> dict:
        return Vault__Sync__Scope(crypto=self.crypto, api=self.api).widen(directory, folder, on_progress)

    def unshallow(self, directory: str, on_progress: callable = None) -> dict:
        return Vault__Sync__Scope(crypto=self.crypto, api=self.api).unshallow(directory, on_progress)

    def clone_read_only(self, vault_id: str, read_key_hex: str, directory: str,
                        on_progress: callable = None, sparse: bool = False,
                        depth: int = 0, scope_paths: list = None) -> dict:
        return Vault__Sync__Clone(crypto=self.crypto, api=self.api).clone_read_only(
            vault_id, read_key_hex, directory, on_progress, sparse, depth=depth, scope_paths=scope_paths)

    def delete_on_remote(self, directory: str) -> dict:
        return Vault__Sync__Lifecycle(crypto=self.crypto, api=self.api).delete_on_remote(directory)

    def rekey_check(self, directory: str) -> dict:
        return Vault__Sync__Lifecycle(crypto=self.crypto, api=self.api).rekey_check(directory)

    def rekey_wipe(self, directory: str) -> dict:
        return Vault__Sync__Lifecycle(crypto=self.crypto, api=self.api).rekey_wipe(directory)

    def rekey_init(self, directory: str, new_vault_key: str = None) -> dict:
        return Vault__Sync__Lifecycle(crypto=self.crypto, api=self.api).rekey_init(directory, new_vault_key)

    def rekey_commit(self, directory: str) -> dict:
        return Vault__Sync__Lifecycle(crypto=self.crypto, api=self.api).rekey_commit(directory)

    def rekey(self, directory: str, new_vault_key: str = None) -> dict:
        return Vault__Sync__Lifecycle(crypto=self.crypto, api=self.api).rekey(directory, new_vault_key)

    def uninit(self, directory: str) -> dict:
        return Vault__Sync__Lifecycle(crypto=self.crypto, api=self.api).uninit(directory)

    def restore_from_backup(self, zip_path: str, directory: str) -> dict:
        return Vault__Sync__Lifecycle(crypto=self.crypto, api=self.api).restore_from_backup(zip_path, directory)

    def _get_head_flat_map(self, directory: str) -> tuple:
        return Vault__Sync__Sparse(crypto=self.crypto, api=self.api)._get_head_flat_map(directory)

    def sparse_ls(self, directory: str, path: str = None) -> list:
        return Vault__Sync__Sparse(crypto=self.crypto, api=self.api).sparse_ls(directory, path)

    def sparse_fetch(self, directory: str, path: str = None,
                     on_progress: callable = None) -> dict:
        return Vault__Sync__Sparse(crypto=self.crypto, api=self.api).sparse_fetch(
            directory, path, on_progress)

    def sparse_cat(self, directory: str, path: str) -> bytes:
        return Vault__Sync__Sparse(crypto=self.crypto, api=self.api).sparse_cat(directory, path)

    def fsck(self, directory: str, repair: bool = False, verbose: bool = False,
             on_progress: callable = None) -> dict:
        return Vault__Sync__Fsck(crypto=self.crypto, api=self.api).fsck(
            directory, repair, verbose, on_progress)

    def upload_objects(self, directory: str, object_ids: list,
                       on_progress: callable = None) -> dict:
        from sgit_ai.core.actions.fsck.Vault__Sync__Upload_Objects import Vault__Sync__Upload_Objects
        return Vault__Sync__Upload_Objects(crypto=self.crypto, api=self.api).upload_objects(
            directory, object_ids, on_progress)

    def _repair_object(self, object_id: str, vault_id: str, sg_dir: str) -> bool:
        return Vault__Sync__Fsck(crypto=self.crypto, api=self.api)._repair_object(
            object_id, vault_id, sg_dir)

    def move(self, directory: str, new_vault_key: str = None,
             target_api_url: str = None, reason: str = '',
             on_progress: callable = None, dry_run: bool = False) -> dict:
        from sgit_ai.core.actions.move.Vault__Sync__Move import Vault__Sync__Move
        return Vault__Sync__Move(crypto=self.crypto, api=self.api).move(
            directory, new_vault_key, target_api_url, reason, on_progress, dry_run)

    def move_cleanup(self, directory: str, on_progress: callable = None) -> dict:
        from sgit_ai.core.actions.move.Vault__Sync__Move import Vault__Sync__Move
        return Vault__Sync__Move(crypto=self.crypto, api=self.api).cleanup(
            directory, on_progress)
