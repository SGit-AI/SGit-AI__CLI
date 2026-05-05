"""Vault__Sync__Commit — commit and write_file operations (Brief 22 — E5).

Inherits shared helpers (_init_components, _read_local_config, _scan_local_directory,
_checkout_flat_map, _remove_deleted_flat, _remove_empty_dirs) from Vault__Sync__Base.
"""
import mimetypes
import os
from   sgit_ai.storage.Vault__Commit              import Vault__Commit
from   sgit_ai.core.Vault__Errors                 import Vault__Read_Only_Error
from   sgit_ai.storage.Vault__Sub_Tree               import Vault__Sub_Tree
from   sgit_ai.core.Vault__Sync__Base             import Vault__Sync__Base


class Vault__Sync__Commit(Vault__Sync__Base):

    def commit(self, directory: str, message: str = '', allow_deletions: bool = False) -> dict:
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
        sparse       = local_config.sparse

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

        old_flat_entries = {}
        old_commit       = None
        if parent_id:
            vault_commit_reader = Vault__Commit(crypto=self.crypto, pki=pki,
                                                object_store=obj_store, ref_manager=ref_manager)
            old_commit       = vault_commit_reader.load_commit(parent_id, read_key)
            old_flat_entries = sub_tree.flatten(str(old_commit.tree_id), read_key)

        new_file_map = self._scan_local_directory(directory)

        if sparse and not allow_deletions:
            # Sparse-safe: start from parent tree, overlay on-disk changes, preserve unfetched entries
            merged_flat = dict(old_flat_entries)
            for rel_path in new_file_map:
                full_path = os.path.join(directory, rel_path)
                with open(full_path, 'rb') as fh:
                    content = fh.read()
                blob_id, is_large, file_hash = sub_tree.encrypt_or_reuse_blob(
                    content, old_flat_entries.get(rel_path), read_key)
                content_type = mimetypes.guess_type(rel_path)[0] or 'application/octet-stream'
                merged_flat[rel_path] = dict(blob_id      = blob_id,
                                             size         = len(content),
                                             content_hash = file_hash,
                                             content_type = content_type,
                                             large        = is_large)
            root_tree_id  = sub_tree.build_from_flat(merged_flat, read_key)
            auto_msg      = message or self._generate_sparse_commit_message(old_flat_entries, new_file_map)
            old_paths     = set(old_flat_entries.keys())
            on_disk_paths = set(new_file_map.keys())
            files_changed = len(on_disk_paths - old_paths) + sum(
                1 for p in on_disk_paths & old_paths
                if new_file_map[p].get('content_hash') != old_flat_entries[p].get('content_hash')
            )
        else:
            root_tree_id  = sub_tree.build(directory, new_file_map, read_key,
                                           old_flat_entries=old_flat_entries)
            auto_msg      = message or self._generate_commit_message(old_flat_entries, new_file_map)
            old_paths     = set(old_flat_entries.keys())
            new_paths     = set(new_file_map.keys())
            files_changed = len(new_paths - old_paths) + len(old_paths - new_paths)

        if parent_id and old_commit and root_tree_id == str(old_commit.tree_id):
            raise RuntimeError('nothing to commit, working tree clean')

        signing_key = None
        try:
            signing_key = key_manager.load_private_key_locally(
                str(branch_meta.public_key_id), storage.local_dir(directory))
        except (FileNotFoundError, Exception):
            pass

        vault_commit = Vault__Commit(crypto=self.crypto, pki=pki,
                                     object_store=obj_store, ref_manager=ref_manager)

        commit_id = vault_commit.create_commit(tree_id     = root_tree_id,
                                               read_key    = read_key,
                                               parent_ids  = [parent_id] if parent_id else [],
                                               message     = auto_msg,
                                               branch_id   = branch_id,
                                               signing_key = signing_key)

        ref_manager.write_ref(ref_id, commit_id, read_key)

        return dict(commit_id     = commit_id,
                    branch_id     = branch_id,
                    message       = auto_msg,
                    files_changed = files_changed)

    def write_file(self, directory: str, path: str, content: bytes,
                   message: str = '', also: dict = None) -> dict:
        """Write file content directly to vault HEAD without scanning the working directory.

        `also` is an optional {vault_path: bytes} dict for atomic multi-file writes.
        Returns dict: {blob_id, commit_id, message, paths, unchanged}.
        If content is identical to the existing entry, no new commit is created.
        """
        c = self._init_components(directory)

        if not c.write_key:
            raise Vault__Read_Only_Error()

        read_key       = c.read_key
        storage        = c.storage
        obj_store      = c.obj_store
        ref_manager    = c.ref_manager
        key_manager    = c.key_manager
        branch_manager = c.branch_manager
        pki            = c.pki

        local_config = self._read_local_config(directory, storage)
        branch_id    = str(local_config.my_branch_id)
        index_id     = c.branch_index_file_id
        if not index_id:
            raise RuntimeError('No branch index found — is this a v2 vault?')
        branch_index = branch_manager.load_branch_index(directory, index_id, read_key)
        branch_meta  = branch_manager.get_branch_by_id(branch_index, branch_id)
        if not branch_meta:
            raise RuntimeError(f'Branch not found: {branch_id}')

        ref_id    = str(branch_meta.head_ref_id)
        parent_id = ref_manager.read_ref(ref_id, read_key)

        sub_tree = Vault__Sub_Tree(crypto=self.crypto, obj_store=obj_store)

        old_flat = {}
        if parent_id:
            vault_commit_reader = Vault__Commit(crypto=self.crypto, pki=pki,
                                                object_store=obj_store, ref_manager=ref_manager)
            old_commit = vault_commit_reader.load_commit(parent_id, read_key)
            old_flat   = sub_tree.flatten(str(old_commit.tree_id), read_key)

        flat = dict(old_flat)

        files_to_write = {path: content}
        if also:
            files_to_write.update(also)

        result_blobs = {}
        any_changed  = False
        for file_path, file_content in files_to_write.items():
            old_blob  = flat.get(file_path, {}).get('blob_id')
            blob_id, is_large, file_hash = sub_tree.encrypt_or_reuse_blob(
                file_content, flat.get(file_path), read_key)
            if blob_id != old_blob:
                any_changed = True

            filename     = os.path.basename(file_path)
            content_type = mimetypes.guess_type(filename)[0] or 'application/octet-stream'
            flat[file_path] = dict(blob_id      = blob_id,
                                   size         = len(file_content),
                                   content_hash = file_hash,
                                   content_type = content_type,
                                   large        = is_large)
            result_blobs[file_path] = blob_id

        new_paths = [p for p in files_to_write if p not in old_flat]
        if not any_changed and not new_paths and parent_id:
            return dict(blob_id   = result_blobs.get(path),
                        commit_id = parent_id,
                        message   = '',
                        paths     = result_blobs,
                        unchanged = True)

        root_tree_id = sub_tree.build_from_flat(flat, read_key)

        signing_key = None
        try:
            signing_key = key_manager.load_private_key_locally(
                str(branch_meta.public_key_id), storage.local_dir(directory))
        except (FileNotFoundError, Exception):
            pass

        vault_commit = Vault__Commit(crypto=self.crypto, pki=pki,
                                     object_store=obj_store, ref_manager=ref_manager)
        auto_msg  = message or f'write {path}'
        commit_id = vault_commit.create_commit(tree_id     = root_tree_id,
                                               read_key    = read_key,
                                               parent_ids  = [parent_id] if parent_id else [],
                                               message     = auto_msg,
                                               branch_id   = branch_id,
                                               signing_key = signing_key)
        ref_manager.write_ref(ref_id, commit_id, read_key)

        for file_path, file_content in files_to_write.items():
            dest = os.path.join(directory, file_path)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(dest, 'wb') as f:
                f.write(file_content)

        return dict(blob_id   = result_blobs.get(path),
                    commit_id = commit_id,
                    message   = auto_msg,
                    paths     = result_blobs,
                    unchanged = False)

    def _generate_sparse_commit_message(self, old_flat_entries: dict, on_disk_map: dict) -> str:
        old_paths     = set(old_flat_entries.keys())
        on_disk_paths = set(on_disk_map.keys())
        added         = len(on_disk_paths - old_paths)
        modified      = 0
        for path in old_paths & on_disk_paths:
            old_hash = old_flat_entries[path].get('content_hash', '')
            new_hash = on_disk_map[path].get('content_hash', '')
            if old_hash and new_hash:
                if old_hash != new_hash:
                    modified += 1
            else:
                if old_flat_entries[path].get('size', -1) != on_disk_map[path].get('size', -2):
                    modified += 1
        preserved = len(old_paths - on_disk_paths)
        if preserved:
            return (f'Commit: {added} added, {modified} modified, 0 deleted '
                    f'({preserved} sparse-preserved)')
        return f'Commit: {added} added, {modified} modified, 0 deleted'

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
