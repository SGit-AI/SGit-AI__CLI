"""Vault__Sync__Commit — commit and write_file operations (Brief 22 — E5).

Inherits shared helpers (_init_components, _read_local_config, _scan_local_directory,
_checkout_flat_map, _remove_deleted_flat, _remove_empty_dirs) from Vault__Sync__Base.
"""
import mimetypes
from sgit_ai.storage.Vault__Path_Guard import Vault__Path_Guard
import os
from sgit_ai.core.Vault__Secret_Guard import Vault__Secret_Guard
from   sgit_ai.storage.Vault__Commit              import Vault__Commit
from   sgit_ai.core.Vault__Errors                 import Vault__Read_Only_Error, Vault__Scoped_Clone_Error
from   sgit_ai.core.scope.Vault__Scope            import Vault__Scope
from   sgit_ai.storage.Vault__Scoped_Tree         import Vault__Scoped_Tree
from   sgit_ai.storage.Vault__Sub_Tree               import Vault__Sub_Tree
from   sgit_ai.core.Vault__Sync__Base             import Vault__Sync__Base


class Vault__Sync__Commit(Vault__Sync__Base):

    def _load_signing_key(self, key_manager, branch_meta, storage, directory: str):
        """This clone's signing key, or None with a warning: a commit is never made
        unsigned silently (under signatures-required, teammates refuse it)."""
        try:
            return key_manager.load_private_key_locally(str(branch_meta.public_key_id), storage.local_dir(directory))
        except Exception:
            import sys
            print(f'  warning: this commit is UNSIGNED: no signing key for this clone '
                  f'({branch_meta.public_key_id}.pem missing from .sg_vault/local/). '
                  f'Teammates whose vault requires signed commits will refuse it.', file=sys.stderr)
            return None

    def commit(self, directory: str, message: str = '', allow_deletions: bool = False,
               no_merge_commit: bool = False, amend: bool = False) -> dict:
        """amend=True replaces this clone's head with a new commit (same parents, the
        working copy's tree, the new message or the old one). Refused when the head
        is already on the server, is a merge, or a merge is in progress; the old head
        stays in the local store and in the reflog (sgit history undo)."""
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
        scope    = Vault__Scope().from_local_config(local_config)

        old_flat_entries = {}
        old_commit       = None
        opaque           = None                       # out-of-scope siblings, carried by id (scoped clones)
        if parent_id:
            vault_commit_reader = Vault__Commit(crypto=self.crypto, pki=pki,
                                                object_store=obj_store, ref_manager=ref_manager)
            old_commit       = vault_commit_reader.load_commit(parent_id, read_key)
            if scope.is_scoped():
                old_flat_entries, opaque = Vault__Scoped_Tree(crypto=self.crypto, obj_store=obj_store).flatten(
                    str(old_commit.tree_id), read_key, scope)
            else:
                old_flat_entries = sub_tree.flatten(str(old_commit.tree_id), read_key)

        new_file_map = self._scan_local_directory(directory, warn_links=True)
        Vault__Secret_Guard().refuse_files(directory, new_file_map)       # a backup zip, a hard link to a key (N1, L4)

        if scope.is_scoped():
            outside = scope.paths_outside(new_file_map)
            if outside:
                shown = ', '.join(outside[:5]) + (f' (+{len(outside) - 5} more)' if len(outside) > 5 else '')
                raise Vault__Scoped_Clone_Error(
                    f'this clone holds only {", ".join(scope.folders())}; files outside it cannot be '
                    f'committed from here: {shown}. Widen the clone first (sgit fetch <folder>) or '
                    f'move the files into a held folder.')

        if sparse and not allow_deletions:
            # Sparse-safe: start from parent tree, overlay on-disk changes, preserve unfetched entries
            merged_flat = dict(old_flat_entries)
            for rel_path in new_file_map:
                full_path = os.path.join(directory, rel_path)
                if os.path.islink(full_path) or not os.path.isfile(full_path) or \
                        Vault__Path_Guard().has_link_component(os.path.abspath(directory), os.path.abspath(full_path)):
                    continue                                       # a tracked path under a link keeps its committed entry
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
            root_tree_id  = sub_tree.build_from_flat(merged_flat, read_key, opaque=opaque)
            auto_msg      = message or self._generate_sparse_commit_message(old_flat_entries, new_file_map)
            old_paths     = set(old_flat_entries.keys())
            on_disk_paths = set(new_file_map.keys())
            files_changed = len(on_disk_paths - old_paths) + sum(
                1 for p in on_disk_paths & old_paths
                if new_file_map[p].get('content_hash') != old_flat_entries[p].get('content_hash')
            )
        else:
            root_tree_id  = sub_tree.build(directory, new_file_map, read_key,
                                           old_flat_entries=old_flat_entries, opaque=opaque)
            auto_msg      = message or self._generate_commit_message(old_flat_entries, new_file_map)
            old_paths     = set(old_flat_entries.keys())
            new_paths     = set(new_file_map.keys())
            files_changed = len(new_paths - old_paths) + len(old_paths - new_paths)

        from sgit_ai.core.actions.merge.Vault__Merge__State import Vault__Merge__State
        from sgit_ai.core.actions.merge.Vault__Merge        import Vault__Merge
        ms_mgr             = Vault__Merge__State()
        merge_state        = ms_mgr.read(directory) if ms_mgr.exists(directory) else None
        has_conflict_files = Vault__Merge(crypto=self.crypto).has_conflicts(directory)

        pending_merge = merge_state and not has_conflict_files and not no_merge_commit
        amend_parents = None
        if amend:
            amend_parents, auto_msg = self._amend_plan(directory, c, parent_id, old_commit, merge_state,
                                                       message, auto_msg, root_tree_id)
        elif parent_id and old_commit and root_tree_id == str(old_commit.tree_id):
            if not pending_merge:
                raise RuntimeError('nothing to commit, working tree clean')

        signing_key = self._load_signing_key(key_manager, branch_meta, storage, directory)

        vault_commit = Vault__Commit(crypto=self.crypto, pki=pki,
                                     object_store=obj_store, ref_manager=ref_manager)

        parent_ids = [parent_id] if parent_id else []
        if amend_parents is not None:
            parent_ids = amend_parents
        merge_commit_id = None

        if merge_state and not has_conflict_files and not no_merge_commit and not amend:
            theirs_id = str(merge_state.theirs_commit_id) if merge_state.theirs_commit_id else ''
            if theirs_id and theirs_id not in parent_ids:
                parent_ids = parent_ids + [theirs_id]
            theirs_short = theirs_id[len('obj-cas-imm-'):len('obj-cas-imm-')+12] if theirs_id.startswith('obj-cas-imm-') else theirs_id[:12]
            ours_short   = (parent_id or '')[len('obj-cas-imm-'):len('obj-cas-imm-')+12] if (parent_id or '').startswith('obj-cas-imm-') else (parent_id or '')[:12]
            auto_msg = auto_msg or f'Merge {theirs_short} into {ours_short}'

        commit_id = vault_commit.create_commit(tree_id     = root_tree_id,
                                               read_key    = read_key,
                                               parent_ids  = parent_ids,
                                               message     = auto_msg,
                                               branch_id   = branch_id,
                                               signing_key = signing_key,
                                               author_key_id = str(branch_meta.public_key_id) if (signing_key and branch_meta.public_key_id) else None)

        ref_manager.write_ref(ref_id, commit_id, read_key)

        if merge_state and not has_conflict_files:
            ms_mgr.delete(directory)
        elif merge_state and has_conflict_files:
            ms_mgr.write(directory, merge_state)

        return dict(commit_id     = commit_id,
                    branch_id     = branch_id,
                    message       = auto_msg,
                    files_changed = files_changed,
                    merge_commit  = len(parent_ids) > 1)

    def _amend_plan(self, directory: str, c, head_id: str, head_commit, merge_state, message: str,
                    auto_msg: str, root_tree_id: str) -> tuple:
        """(parent_ids, message) for `commit --amend`, or a refusal naming why not."""
        from sgit_ai.core.Vault__Errors                               import Vault__Revision_Error
        from sgit_ai.core.actions.history.Vault__Sync__History_Edit   import Vault__Sync__History_Edit
        if not head_id or head_commit is None:
            raise Vault__Revision_Error('nothing to amend: this clone has no commits yet')
        if merge_state is not None:
            raise Vault__Revision_Error('a merge is in progress: finish it with sgit commit, then amend')
        parents = [str(p) for p in (head_commit.parents or []) if str(p)]
        if len(parents) > 1:
            raise Vault__Revision_Error(f'{head_id} is a merge commit; amend only rewrites a commit of your own')
        if Vault__Sync__History_Edit(crypto=self.crypto, api=self.api).is_pushed(directory, head_id, c):
            raise Vault__Revision_Error(
                f'{head_id} is already on the server; amending it would rewrite shared history. '
                f'Make a new commit instead (or sgit history revert --as-commit {head_id}).')
        old_message = ''
        if head_commit.message_enc:
            try:
                old_message = self.crypto.decrypt_metadata(c.read_key, str(head_commit.message_enc))
            except Exception:
                old_message = ''
        if not message and root_tree_id == str(head_commit.tree_id):
            raise Vault__Revision_Error('nothing to amend: no file changes and no new message (-m)')
        return parents, (message or old_message or auto_msg)

    def write_file(self, directory: str, path: str, content: bytes,
                   message: str = '', also: dict = None) -> dict:
        """Write file content directly to vault HEAD without scanning the working directory.

        `also` is an optional {vault_path: bytes} dict for atomic multi-file writes.
        Returns dict: {blob_id, commit_id, message, paths, unchanged}.
        If content is identical to the existing entry, no new commit is created.
        """
        targets = self._write_targets(directory, path, content, also)     # every path checked before anything (N4)
        path    = next(iter(targets))
        also    = {p: data for p, (data, _) in list(targets.items())[1:]} or None
        content = targets[path][0]

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
        scope    = Vault__Scope().from_local_config(local_config)

        old_flat = {}
        opaque   = None
        if parent_id:
            vault_commit_reader = Vault__Commit(crypto=self.crypto, pki=pki,
                                                object_store=obj_store, ref_manager=ref_manager)
            old_commit = vault_commit_reader.load_commit(parent_id, read_key)
            if scope.is_scoped():
                old_flat, opaque = Vault__Scoped_Tree(crypto=self.crypto, obj_store=obj_store).flatten(
                    str(old_commit.tree_id), read_key, scope)
            else:
                old_flat = sub_tree.flatten(str(old_commit.tree_id), read_key)

        flat = dict(old_flat)

        files_to_write = {path: content}
        if also:
            files_to_write.update(also)
        if scope.is_scoped():
            outside = scope.paths_outside(files_to_write)
            if outside:
                raise Vault__Scoped_Clone_Error(
                    f'this clone holds only {", ".join(scope.folders())}; cannot write outside it: '
                    f'{", ".join(outside)}')

        for file_path, file_content in files_to_write.items():
            Vault__Secret_Guard().refuse_bytes(file_path, file_content)
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

        root_tree_id = sub_tree.build_from_flat(flat, read_key, opaque=opaque)

        signing_key = self._load_signing_key(key_manager, branch_meta, storage, directory)

        vault_commit = Vault__Commit(crypto=self.crypto, pki=pki,
                                     object_store=obj_store, ref_manager=ref_manager)
        auto_msg  = message or f'write {path}'
        commit_id = vault_commit.create_commit(tree_id     = root_tree_id,
                                               read_key    = read_key,
                                               parent_ids  = [parent_id] if parent_id else [],
                                               message     = auto_msg,
                                               branch_id   = branch_id,
                                               signing_key = signing_key,
                                               author_key_id = str(branch_meta.public_key_id) if (signing_key and branch_meta.public_key_id) else None)
        ref_manager.write_ref(ref_id, commit_id, read_key)

        for file_path, file_content in files_to_write.items():
            dest = Vault__Path_Guard().safe_join(os.path.abspath(directory), file_path)   # again: the tree may have
            os.makedirs(os.path.dirname(dest), exist_ok=True)                            # changed since the check
            with open(dest, 'wb') as f:
                f.write(file_content)

        return dict(blob_id   = result_blobs.get(path),
                    commit_id = commit_id,
                    message   = auto_msg,
                    paths     = result_blobs,
                    unchanged = False)

    def _write_targets(self, directory: str, path: str, content: bytes, also: dict) -> dict:
        """{vault path: (content, absolute destination)} for `sgit write`, path first.
        Each path goes through the same guard as checkout: no '..', no absolute path, no
        .git / .sg_vault, nothing through a link inside the tree. `write` used to commit
        '../escape.txt' or '.git/hooks/x' into the tree and write through an in-tree link
        into .sg_vault/local (review d3b8eef N4). Paths are stored normalised ('a/./b' is 'a/b')."""
        import posixpath
        guard   = Vault__Path_Guard()
        base    = os.path.abspath(directory)
        targets = {}
        for raw, data in [(path, content)] + list((also or {}).items()):
            dest = guard.safe_join(base, raw)
            norm = posixpath.normpath(str(raw).replace(os.sep, '/'))
            targets[norm] = (data, dest)
        return targets

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
