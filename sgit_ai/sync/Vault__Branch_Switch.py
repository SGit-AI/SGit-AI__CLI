import json
import os
import secrets

from osbot_utils.type_safe.Type_Safe               import Type_Safe
from sgit_ai.crypto.PKI__Crypto                    import PKI__Crypto
from sgit_ai.crypto.Vault__Crypto                  import Vault__Crypto
from sgit_ai.crypto.Vault__Key_Manager             import Vault__Key_Manager
from sgit_ai.storage.Vault__Commit                 import Vault__Commit
from sgit_ai.storage.Vault__Object_Store           import Vault__Object_Store
from sgit_ai.storage.Vault__Ref_Manager            import Vault__Ref_Manager
from sgit_ai.safe_types.Enum__Branch_Type          import Enum__Branch_Type
from sgit_ai.schemas.Schema__Branch_Index          import Schema__Branch_Index
from sgit_ai.schemas.Schema__Local_Config          import Schema__Local_Config
from sgit_ai.storage.Vault__Branch_Manager            import Vault__Branch_Manager
from sgit_ai.sync.Vault__Components                import Vault__Components
from sgit_ai.storage.Vault__Storage                   import Vault__Storage, SG_VAULT_DIR
from sgit_ai.storage.Vault__Sub_Tree                  import Vault__Sub_Tree


class Vault__Branch_Switch(Type_Safe):
    crypto : Vault__Crypto

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def switch(self, directory: str, name_or_id: str, force: bool = False) -> dict:
        """Switch to a named branch, reusing an existing local clone when available.

        Accepts either a branch name (e.g. 'main') or a branch ID
        (e.g. 'branch-named-abc123').

        Raises RuntimeError if there are uncommitted changes (unless force=True).
        Returns a dict with new_clone_branch_id, old_clone_branch_id,
        named_branch_id, files_restored, and reused (bool).
        """
        c              = self._init_components(directory)
        read_key       = c.read_key
        storage        = c.storage
        branch_manager = c.branch_manager
        ref_manager    = c.ref_manager
        obj_store      = c.obj_store

        # Check for uncommitted changes (skipped when force=True)
        if not force:
            self._assert_clean(directory, c)

        # Load branch index
        index_id = c.branch_index_file_id
        if not index_id:
            raise RuntimeError('No branch index found — is this a v2 vault?')
        branch_index = branch_manager.load_branch_index(directory, index_id, read_key)

        # Resolve the named branch (by name OR by branch_id)
        named_meta = branch_manager.get_branch_by_name(branch_index, name_or_id)
        if named_meta is None:
            named_meta = branch_manager.get_branch_by_id(branch_index, name_or_id)
        if named_meta is None:
            raise RuntimeError(f'Branch not found: {name_or_id}')
        if named_meta.branch_type != Enum__Branch_Type.NAMED:
            raise RuntimeError(f'Cannot switch to a clone branch: {name_or_id}')

        named_branch_id = str(named_meta.branch_id)
        named_name      = str(named_meta.name)

        # Capture old clone branch
        local_config        = self._read_local_config(directory, storage)
        old_clone_branch_id = str(local_config.my_branch_id)

        # Look for an existing usable clone branch before creating a new one
        existing_clone_meta = self.find_usable_clone_branch(directory, branch_index,
                                                            named_branch_id, storage)
        reused = existing_clone_meta is not None

        if reused:
            # Reuse the existing clone branch
            new_clone_meta      = existing_clone_meta
            new_clone_branch_id = str(new_clone_meta.branch_id)

            # Update the clone HEAD to match the current named branch HEAD
            named_head_commit_id = ref_manager.read_ref(str(named_meta.head_ref_id), read_key)
            ref_manager.write_ref(str(new_clone_meta.head_ref_id), named_head_commit_id, read_key)

            # No need to append to index — branch already exists there
        else:
            # Create new clone branch tracking the named branch
            new_clone_meta = branch_manager.create_clone_branch(
                directory,
                f'clone-{named_name}',
                read_key,
                creator_branch_id = named_branch_id,
            )
            new_clone_branch_id = str(new_clone_meta.branch_id)

            # Point the new clone branch HEAD at the named branch HEAD commit
            named_head_commit_id = ref_manager.read_ref(str(named_meta.head_ref_id), read_key)
            ref_manager.write_ref(str(new_clone_meta.head_ref_id), named_head_commit_id, read_key)

            # Persist updated branch index
            branch_index.branches.append(new_clone_meta)
            branch_manager.save_branch_index(directory, branch_index, read_key,
                                             index_file_id=index_id)

        # Update local config
        self._write_local_config(directory, storage, new_clone_branch_id)

        # Checkout working copy from named branch HEAD
        files_restored = 0
        if named_head_commit_id:
            files_restored = self._checkout_commit(directory, c, named_head_commit_id)

        return dict(
            named_branch_id     = named_branch_id,
            named_name          = named_name,
            new_clone_branch_id = new_clone_branch_id,
            old_clone_branch_id = old_clone_branch_id,
            files_restored      = files_restored,
            reused              = reused,
        )

    def find_usable_clone_branch(self, directory: str,
                                 branch_index: 'Schema__Branch_Index',
                                 named_branch_id: str,
                                 storage: 'Vault__Storage') -> 'Schema__Branch_Meta | None':
        """Find the most recent clone branch for *named_branch_id* whose private key
        still exists on disk in the local directory.

        Returns the matching Schema__Branch_Meta, or None if none found.
        """
        local_dir = storage.local_dir(directory)

        candidates = [
            branch for branch in branch_index.branches
            if (branch.branch_type == Enum__Branch_Type.CLONE
                and str(branch.creator_branch) == named_branch_id)
        ]

        if not candidates:
            return None

        # Sort descending by created_at so the most recent comes first
        candidates.sort(key=lambda b: int(b.created_at) if b.created_at else 0, reverse=True)

        for candidate in candidates:
            pub_key_id = str(candidate.public_key_id) if candidate.public_key_id else ''
            if not pub_key_id:
                continue
            key_file = os.path.join(local_dir, pub_key_id + '.pem')
            if os.path.isfile(key_file):
                return candidate

        return None

    def branch_new(self, directory: str, name: str, from_branch_id: str = None) -> dict:
        """Create a new named branch plus a new clone branch tracking it.

        If from_branch_id is given, the new named branch HEAD is seeded from
        that named branch's HEAD commit.  Otherwise uses the current clone
        branch's creator (named) branch HEAD.

        Returns a dict with named_branch_id, clone_branch_id.
        """
        c              = self._init_components(directory)
        read_key       = c.read_key
        storage        = c.storage
        branch_manager = c.branch_manager
        ref_manager    = c.ref_manager

        index_id = c.branch_index_file_id
        if not index_id:
            raise RuntimeError('No branch index found — is this a v2 vault?')
        branch_index = branch_manager.load_branch_index(directory, index_id, read_key)

        # Determine the source commit to branch from
        source_commit_id = None
        if from_branch_id:
            src_meta = branch_manager.get_branch_by_id(branch_index, from_branch_id)
            if src_meta is None:
                src_meta = branch_manager.get_branch_by_name(branch_index, from_branch_id)
            if src_meta is None:
                raise RuntimeError(f'Source branch not found: {from_branch_id}')
            if src_meta.branch_type != Enum__Branch_Type.NAMED:
                raise RuntimeError(f'--from must point to a named branch: {from_branch_id}')
            source_commit_id = ref_manager.read_ref(str(src_meta.head_ref_id), read_key)
        else:
            # Use current clone's creator named branch HEAD
            local_config    = self._read_local_config(directory, storage)
            clone_branch_id = str(local_config.my_branch_id)
            clone_meta      = branch_manager.get_branch_by_id(branch_index, clone_branch_id)
            if clone_meta and clone_meta.creator_branch:
                creator_id = str(clone_meta.creator_branch)
                creator_meta = branch_manager.get_branch_by_id(branch_index, creator_id)
                if creator_meta:
                    source_commit_id = ref_manager.read_ref(
                        str(creator_meta.head_ref_id), read_key)

        # Create new named branch
        new_named_meta = branch_manager.create_named_branch(directory, name, read_key)
        new_named_id   = str(new_named_meta.branch_id)

        # Write named branch HEAD ref
        ref_manager.write_ref(str(new_named_meta.head_ref_id), source_commit_id or '', read_key)

        # Create clone branch tracking the new named branch
        new_clone_meta = branch_manager.create_clone_branch(
            directory,
            f'clone-{name}',
            read_key,
            creator_branch_id = new_named_id,
        )
        new_clone_id = str(new_clone_meta.branch_id)

        # Point clone HEAD at same commit
        ref_manager.write_ref(str(new_clone_meta.head_ref_id), source_commit_id or '', read_key)

        # Persist updated index
        branch_index.branches.append(new_named_meta)
        branch_index.branches.append(new_clone_meta)
        branch_manager.save_branch_index(directory, branch_index, read_key,
                                         index_file_id=index_id)

        # Update local config to point at new clone
        self._write_local_config(directory, storage, new_clone_id)

        return dict(
            named_branch_id = new_named_id,
            named_name      = name,
            clone_branch_id = new_clone_id,
        )

    def branch_list(self, directory: str) -> dict:
        """Return all branches with current-branch marker.

        Returns dict with keys 'branches' (list of dicts) and 'my_branch_id'.
        Each branch dict contains: branch_id, name, branch_type, head_ref_id,
        head_commit, is_current, creator_branch.
        """
        c              = self._init_components(directory)
        read_key       = c.read_key
        storage        = c.storage
        branch_manager = c.branch_manager
        ref_manager    = c.ref_manager

        local_config = self._read_local_config(directory, storage)
        my_branch_id = str(local_config.my_branch_id)

        index_id = c.branch_index_file_id
        if not index_id:
            return dict(branches=[], my_branch_id=my_branch_id)

        branch_index = branch_manager.load_branch_index(directory, index_id, read_key)

        # Build a lookup: clone_branch_id -> named_branch_id it tracks
        clone_to_named = {}
        for branch in branch_index.branches:
            if branch.branch_type == Enum__Branch_Type.CLONE and branch.creator_branch:
                clone_to_named[str(branch.branch_id)] = str(branch.creator_branch)

        result = []
        for branch in branch_index.branches:
            head_commit_id = ref_manager.read_ref(str(branch.head_ref_id), read_key)
            is_current     = str(branch.branch_id) == my_branch_id
            result.append(dict(
                branch_id      = str(branch.branch_id),
                name           = str(branch.name),
                branch_type    = str(branch.branch_type.value) if branch.branch_type else 'unknown',
                head_ref_id    = str(branch.head_ref_id),
                head_commit    = head_commit_id or '',
                is_current     = is_current,
                creator_branch = str(branch.creator_branch) if branch.creator_branch else '',
            ))

        return dict(branches=result, my_branch_id=my_branch_id)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _assert_clean(self, directory: str, c: Vault__Components) -> None:
        """Raise RuntimeError if the working copy has uncommitted changes."""
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
            return
        branch_index = branch_manager.load_branch_index(directory, index_id, read_key)
        branch_meta  = branch_manager.get_branch_by_id(branch_index, branch_id)
        if not branch_meta:
            return

        ref_id    = str(branch_meta.head_ref_id)
        parent_id = ref_manager.read_ref(ref_id, read_key)

        old_entries = {}
        if parent_id:
            vault_commit = Vault__Commit(crypto=self.crypto, pki=pki,
                                         object_store=obj_store, ref_manager=ref_manager)
            old_commit   = vault_commit.load_commit(parent_id, read_key)
            sub_tree     = Vault__Sub_Tree(crypto=self.crypto, obj_store=obj_store)
            old_entries  = sub_tree.flatten(str(old_commit.tree_id), read_key)

        new_file_map = self._scan_local_directory(directory)

        old_paths = set(old_entries.keys())
        new_paths = set(new_file_map.keys())

        added    = new_paths - old_paths
        deleted  = old_paths - new_paths
        modified = set()
        for path in old_paths & new_paths:
            local_file = os.path.join(directory, path)
            with open(local_file, 'rb') as f:
                content = f.read()
            old_hash  = old_entries[path].get('content_hash', '')
            file_hash = self.crypto.content_hash(content)
            if old_hash and old_hash != file_hash:
                modified.add(path)

        if added or deleted or modified:
            raise RuntimeError(
                'You have uncommitted changes. Please commit or stash them first.\n'
                '  sgit commit    — commit changes\n'
                '  sgit stash     — stash changes temporarily'
            )

    def _checkout_commit(self, directory: str, c: Vault__Components,
                         commit_id: str) -> int:
        """Restore working copy to the given commit. Returns number of files restored."""
        pki       = c.pki
        obj_store = c.obj_store
        ref_manager = c.ref_manager
        read_key    = c.read_key

        vault_commit = Vault__Commit(crypto=self.crypto, pki=pki,
                                     object_store=obj_store, ref_manager=ref_manager)
        commit_obj   = vault_commit.load_commit(commit_id, read_key)
        sub_tree     = Vault__Sub_Tree(crypto=self.crypto, obj_store=obj_store)
        flat_map     = sub_tree.flatten(str(commit_obj.tree_id), read_key)

        # Write committed files to working directory
        restored = 0
        for path, entry in sorted(flat_map.items()):
            blob_id = entry.get('blob_id')
            if not blob_id:
                continue
            try:
                ciphertext = obj_store.load(blob_id)
                plaintext  = self.crypto.decrypt(read_key, ciphertext)
                full_path  = os.path.join(directory, path)
                os.makedirs(os.path.dirname(full_path), exist_ok=True)
                with open(full_path, 'wb') as fh:
                    fh.write(plaintext)
                restored += 1
            except Exception:
                pass

        # Remove files that are in the working copy but not in the committed tree
        from sgit_ai.sync.Vault__Ignore import Vault__Ignore
        ignore = Vault__Ignore().load_gitignore(directory)
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
                if rel_path not in flat_map:
                    full_path = os.path.join(root, filename)
                    if os.path.isfile(full_path):
                        os.remove(full_path)

        return restored

    def _scan_local_directory(self, directory: str) -> dict:
        """Scan working directory and return {rel_path: {size, content_hash}} map."""
        from sgit_ai.sync.Vault__Ignore import Vault__Ignore
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
                with open(full_path, 'rb') as f:
                    content = f.read()
                result[rel_path] = dict(
                    size         = len(content),
                    content_hash = self.crypto.content_hash(content),
                )
        return result

    def _init_components(self, directory: str) -> Vault__Components:
        vault_key_path = os.path.join(directory, SG_VAULT_DIR, 'local', 'vault_key')
        with open(vault_key_path, 'r') as fh:
            vault_key = fh.read().strip()

        keys    = self.crypto.derive_keys_from_vault_key(vault_key)
        sg_dir  = os.path.join(directory, SG_VAULT_DIR)
        storage = Vault__Storage()
        pki     = PKI__Crypto()

        obj_store      = Vault__Object_Store(vault_path=sg_dir, crypto=self.crypto)
        ref_manager    = Vault__Ref_Manager(vault_path=sg_dir,  crypto=self.crypto)
        key_manager    = Vault__Key_Manager(vault_path=sg_dir,  crypto=self.crypto, pki=pki)
        branch_manager = Vault__Branch_Manager(vault_path    = sg_dir,
                                               crypto        = self.crypto,
                                               key_manager   = key_manager,
                                               ref_manager   = ref_manager,
                                               storage       = storage)
        return Vault__Components(
            vault_key            = vault_key,
            vault_id             = keys['vault_id'],
            read_key             = keys['read_key_bytes'],
            write_key            = keys['write_key'],
            ref_file_id          = keys['ref_file_id'],
            branch_index_file_id = keys['branch_index_file_id'],
            sg_dir               = sg_dir,
            storage              = storage,
            pki                  = pki,
            obj_store            = obj_store,
            ref_manager          = ref_manager,
            key_manager          = key_manager,
            branch_manager       = branch_manager,
        )

    def _read_local_config(self, directory: str, storage: Vault__Storage) -> Schema__Local_Config:
        config_path = storage.local_config_path(directory)
        with open(config_path, 'r') as fh:
            data = json.load(fh)
        return Schema__Local_Config.from_json(data)

    def _write_local_config(self, directory: str, storage: Vault__Storage,
                            branch_id: str) -> None:
        local_config = Schema__Local_Config(my_branch_id=branch_id)
        config_path  = storage.local_config_path(directory)
        with open(config_path, 'w') as fh:
            json.dump(local_config.json(), fh, indent=2)
