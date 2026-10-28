"""Vault__Sync__Commit — commit and write_file operations (Brief 22 — E5).

Inherits shared helpers (_init_components, _read_local_config, _scan_local_directory,
_checkout_flat_map, _remove_deleted_flat, _remove_empty_dirs) from Vault__Sync__Base.
"""
import mimetypes
from sgit_ai.storage.Vault__Path_Guard import Vault__Path_Guard
import os
from sgit_ai.core.Vault__Secret_Guard import Vault__Secret_Guard
from   sgit_ai.storage.Vault__Commit              import Vault__Commit
from   sgit_ai.storage.Vault__Commit_Message      import Vault__Commit_Message
from   sgit_ai.core.Vault__Errors                 import Vault__Read_Only_Error, Vault__Scoped_Clone_Error, \
                                                         Vault__Partial_Commit_Error, Vault__Pathspec_Error
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
               no_merge_commit: bool = False, amend: bool = False, allow_secret_files: list = None,
               paths: list = None, cwd: str = None, hunks: list = None, signing=None) -> dict:
        """amend=True replaces this clone's head with a new commit (same parents, the
        working copy's tree, the new message or the old one). Refused when the head
        is already on the server, is a merge, or a merge is in progress; the old head
        stays in the local store and in the reflog (sgit history undo).

        paths (Git's `git commit --only <pathspec>`): commit HEAD's tree with only the
        matched paths taken from the working copy (Vault__Pathspec); every other change
        stays uncommitted on disk. Relative patterns are relative to `cwd`.

        hunks (`sgit commit --hunk ID…`): of those paths (every changed file when no
        paths), commit only the named hunks (Vault__Hunks ids, from list_hunks); the
        working copy is never written, so the rest stays as uncommitted changes.

        signing (Schema__Signing_Flags): -S / --gpg-sign[=KEY] / --no-gpg-sign; with none,
        `sgit.gpgSign` in the user's Git config decides. A user signature is made over the
        commit's signing bytes before anything is stored; a failure stores nothing."""
        if paths or hunks:
            from sgit_ai.core.actions.merge.Vault__Merge__State import Vault__Merge__State
            if Vault__Merge__State().exists(directory):                  # Git: exit 128, same words
                raise Vault__Partial_Commit_Error('cannot do a partial commit during a merge')
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
        message_limit = Vault__Commit_Message().limit_for(branch_index)
        Vault__Commit_Message().check(message, message_limit)            # before any blob or tree is written

        ref_id     = str(branch_meta.head_ref_id)
        parent_id  = ref_manager.read_ref(ref_id, read_key)

        sub_tree = Vault__Sub_Tree(crypto=self.crypto, obj_store=obj_store)
        scope    = Vault__Scope().from_local_config(local_config)

        old_flat_entries = {}
        old_tree_ids     = {}
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
                old_tree_ids     = sub_tree.flatten_dirs(str(old_commit.tree_id), read_key)

        conflict_files = []                                              # seen by the scan: no second walk
        new_file_map   = self._scan_local_directory(directory, warn_links=True, conflict_out=conflict_files)
        changed = [p for p, e in new_file_map.items()                     # what this commit adds or changes: a file
                   if not (old_flat_entries.get(p) or {}).get('content_hash') # committed once with --allow-secret-file
                   or old_flat_entries[p]['content_hash'] != e.get('content_hash')]   # is not refused again (F2)

        selection = None
        if paths or hunks:                                               # only the named paths; the rest stays on disk
            selection    = self._select_paths(directory, paths, cwd, old_flat_entries, new_file_map, changed,
                                              sparse and not allow_deletions)
            if hunks:
                self._select_hunks(directory, c.obj_store, c.vault_id, read_key, old_flat_entries, selection, hunks)
            changed      = selection['changed']
            new_file_map = {p: new_file_map[p] for p in changed}
        Vault__Secret_Guard().refuse_files(directory, changed,            # a backup zip, a hard link to a key (N1, L4)
                                           allowed=allow_secret_files or ())

        if scope.is_scoped():
            outside = scope.paths_outside(new_file_map)
            if outside:
                shown = ', '.join(outside[:5]) + (f' (+{len(outside) - 5} more)' if len(outside) > 5 else '')
                raise Vault__Scoped_Clone_Error(
                    f'this clone holds only {", ".join(scope.folders())}; files outside it cannot be '
                    f'committed from here: {shown}. Widen the clone first (sgit fetch <folder>) or '
                    f'move the files into a held folder.')

        removed_from_set = []
        if selection is not None:
            merged_flat = dict(old_flat_entries)
            for p in selection['deleted']:
                merged_flat.pop(p)
            partial = selection.get('content') or {}
            for rel_path in changed:
                if rel_path in partial:                                  # some hunks of the file: never on disk
                    if rel_path not in (allow_secret_files or ()):
                        Vault__Secret_Guard().refuse_bytes(rel_path, partial[rel_path])
                    entry = self._entry_for(rel_path, partial[rel_path], sub_tree, old_flat_entries.get(rel_path), read_key)
                else:
                    entry = self._read_entry(directory, rel_path, sub_tree, old_flat_entries.get(rel_path), read_key)
                if entry is not None:
                    merged_flat[rel_path] = entry
            root_tree_id     = sub_tree.build_from_flat(merged_flat, read_key, opaque=opaque,
                                                        old_flat_entries=old_flat_entries, old_tree_ids=old_tree_ids)
            auto_msg         = message or self._generate_commit_message(old_flat_entries, merged_flat)
            files_changed    = len(changed) + len(selection['deleted'])
            removed_from_set = selection['deleted']
        elif sparse and not allow_deletions:
            # Sparse-safe: start from parent tree, overlay on-disk changes, preserve unfetched entries.
            # A path the clone checked out (its checkout set) and no longer holds on disk is a
            # deletion, as on a full clone; a path never checked out is kept.
            from sgit_ai.storage.Vault__Checkout_Set import Vault__Checkout_Set
            merged_flat = dict(old_flat_entries)
            cset        = Vault__Checkout_Set()
            if cset.needs_rebuild(directory):                                  # a pack clone without its record (M2)
                cset.rebuild(directory, old_flat_entries, new_file_map)
            checked_out = cset.load(directory)
            if checked_out is not None:
                removed_from_set = sorted(p for p in merged_flat if p in checked_out and p not in new_file_map)
                for p in removed_from_set:
                    merged_flat.pop(p)
            for rel_path in new_file_map:
                full_path = os.path.join(directory, rel_path)
                if os.path.islink(full_path) or not os.path.isfile(full_path) or \
                        Vault__Path_Guard().has_link_component(os.path.abspath(directory), os.path.abspath(full_path)):
                    continue                                       # a tracked path under a link keeps its committed entry
                content = Vault__Path_Guard().read_regular(full_path, rel_path)   # O_NOFOLLOW (L4); raises if unreadable (B2)
                if content is None:
                    continue
                blob_id, is_large, file_hash = sub_tree.encrypt_or_reuse_blob(
                    content, old_flat_entries.get(rel_path), read_key)
                content_type = mimetypes.guess_type(rel_path)[0] or 'application/octet-stream'
                merged_flat[rel_path] = dict(blob_id      = blob_id,
                                             size         = len(content),
                                             content_hash = file_hash,
                                             content_type = content_type,
                                             large        = is_large)
            root_tree_id  = sub_tree.build_from_flat(merged_flat, read_key, opaque=opaque,
                                                     old_flat_entries=old_flat_entries, old_tree_ids=old_tree_ids)
            auto_msg      = message or self._generate_sparse_commit_message(old_flat_entries, new_file_map)
            old_paths     = set(old_flat_entries.keys())
            on_disk_paths = set(new_file_map.keys())
            files_changed = len(on_disk_paths - old_paths) + len(removed_from_set) + sum(
                1 for p in on_disk_paths & old_paths
                if new_file_map[p].get('content_hash') != old_flat_entries[p].get('content_hash')
            )
        else:
            root_tree_id  = sub_tree.build(directory, new_file_map, read_key,
                                           old_flat_entries=old_flat_entries, opaque=opaque,
                                           old_tree_ids=old_tree_ids)
            auto_msg      = message or self._generate_commit_message(old_flat_entries, new_file_map)
            old_paths     = set(old_flat_entries.keys())
            new_paths     = set(new_file_map.keys())
            files_changed = len(new_paths - old_paths) + len(old_paths - new_paths) + sum(   # modified files count too:
                1 for p in new_paths & old_paths                                            # "Committed 0 file(s)" (d3b8eef)
                if new_file_map[p].get('content_hash') != old_flat_entries[p].get('content_hash'))

        from sgit_ai.core.actions.merge.Vault__Merge__State import Vault__Merge__State
        from sgit_ai.core.actions.merge.Vault__Merge        import Vault__Merge
        ms_mgr             = Vault__Merge__State()
        merge_state        = ms_mgr.read(directory) if ms_mgr.exists(directory) else None
        if merge_state:                                                   # the .conflict files used to be committed
            unresolved = Vault__Merge(crypto=self.crypto).unresolved(directory, merge_state)   # here (design__00 B1)
            if unresolved:
                from sgit_ai.core.Vault__Errors import Vault__Merge_Unresolved_Error
                raise Vault__Merge_Unresolved_Error(unresolved, marker_paths=[str(p) for p in merge_state.marker_paths])
        has_conflict_files = False                                        # a merge reaching here is resolved

        pending_merge = merge_state and not has_conflict_files and not no_merge_commit
        amend_parents = None
        if amend:
            amend_parents, auto_msg = self._amend_plan(directory, c, parent_id, old_commit, merge_state,
                                                       message, auto_msg, root_tree_id)
        elif parent_id and old_commit and root_tree_id == str(old_commit.tree_id):
            if not pending_merge:
                raise RuntimeError('nothing to commit, working tree clean')

        signing_key = self._load_signing_key(key_manager, branch_meta, storage, directory)
        user_signer = self._user_signer(signing)

        vault_commit = Vault__Commit(crypto=self.crypto, pki=pki, object_store=obj_store, ref_manager=ref_manager,
                                     max_message_bytes=message_limit)

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
                                               author_key_id = str(branch_meta.public_key_id) if (signing_key and branch_meta.public_key_id) else None,
                                               **self._signer_kw(user_signer))

        ref_manager.write_ref(ref_id, commit_id, read_key)
        if sparse:                                                             # what was committed from disk is checked out
            from sgit_ai.storage.Vault__Checkout_Set import Vault__Checkout_Set
            Vault__Checkout_Set().add(directory, list(new_file_map))
            Vault__Checkout_Set().discard(directory, removed_from_set)

        if merge_state and not has_conflict_files:
            ms_mgr.delete(directory)
        elif merge_state and has_conflict_files:
            ms_mgr.write(directory, merge_state)

        result = dict(commit_id     = commit_id,
                      branch_id     = branch_id,
                      message       = auto_msg,
                      files_changed = files_changed,
                      merge_commit  = len(parent_ids) > 1)
        if user_signer is not None:
            result['signed_with'] = self._signed_with(user_signer, vault_commit, commit_id, read_key)
        if selection is not None:
            result['paths']            = sorted(changed + selection['deleted'])
            result['left_uncommitted'] = selection['left_uncommitted']
        return result

    def _user_signer(self, signing):
        from sgit_ai.core.actions.commit.Vault__User_Signing import Vault__User_Signing
        return Vault__User_Signing().signer_for(signing)

    def _signer_kw(self, user_signer) -> dict:
        return dict(user_signer=user_signer) if user_signer is not None else {}

    def _signed_with(self, user_signer, vault_commit, commit_id: str, read_key) -> str:
        return user_signer.describe(vault_commit.load_commit(commit_id, read_key).user_signature)

    def _select_paths(self, directory: str, patterns: list, cwd: str, old_flat: dict, disk: dict,
                      changed: list, sparse_safe: bool) -> dict:
        """What `commit <pathspec>` takes: the changed and deleted paths the patterns match
        (HEAD's paths and the working copy's, so a deleted tracked file and a new file both
        match). A pattern that matches nothing refuses the commit, as in Git."""
        from sgit_ai.core.actions.commit.Vault__Pathspec import Vault__Pathspec
        matched = set(old_flat) | set(disk)
        if patterns:
            pathspec           = Vault__Pathspec().from_args(patterns, cwd or directory, directory)
            matched, unmatched = pathspec.match(matched)
            if unmatched:
                raise Vault__Pathspec_Error(self._unmatched_message(directory, pathspec, unmatched))
        deletable = set(old_flat) - set(disk)
        if sparse_safe:                                                  # a path never checked out is not deleted
            from sgit_ai.storage.Vault__Checkout_Set import Vault__Checkout_Set
            checked_out = Vault__Checkout_Set().load(directory)
            deletable   = deletable & set(checked_out or ())
        all_deleted = sorted(deletable)
        selected    = sorted(p for p in changed if p in matched)
        deleted     = sorted(p for p in all_deleted if p in matched)
        left        = sorted(set(changed + all_deleted) - set(selected) - set(deleted))
        return dict(changed=selected, deleted=deleted, left_uncommitted=left)

    def _select_hunks(self, directory: str, obj_store, vault_id, read_key, old_flat: dict, selection: dict,
                      hunk_ids: list) -> None:
        """Narrow a path selection to the named hunks: selection['content'] holds the
        partial bytes of each file, and changed / deleted / left_uncommitted are redone.
        An id that is not among the hunks computed now refuses the whole commit."""
        from sgit_ai.core.actions.commit.Vault__Hunks import Vault__Hunks
        from sgit_ai.core.Vault__Errors               import Vault__Hunk_Selection_Error
        wanted    = {str(h) for h in hunk_ids}
        hunker    = Vault__Hunks()
        found     = set()
        content   = {}
        changed   = []
        deleted   = []
        left      = set(selection['left_uncommitted'])
        for path in selection['changed'] + selection['deleted']:
            base, work = self._hunk_sides(directory, obj_store, vault_id, read_key, old_flat.get(path), path,
                                          path in selection['changed'])
            base_hash  = (old_flat.get(path) or {}).get('content_hash', '')
            work_hash  = self.crypto.content_hash(work) if work is not None else ''
            hunks      = (list(hunker.hunks_of(path, base, work, base_hash, work_hash).hunks) +
                          list(hunker.hunks_of(path, base, work, base_hash, work_hash, split=True).hunks))
            ids        = {str(h.hunk_id) for h in hunks} & wanted
            if not ids:
                left.add(path)
                continue
            found  |= ids
            result  = hunker.apply(base, work, hunks, ids)
            if result != work:
                left.add(path)
            if result is None:
                if base is not None:
                    deleted.append(path)
            elif result != base:
                changed.append(path)
                content[path] = result
        missing = sorted(wanted - found)
        if missing:
            raise Vault__Hunk_Selection_Error(
                f'no such hunk: {", ".join(missing)} (the file or HEAD changed since the hunks were listed, '
                f'or the id is not under the named paths); run sgit commit --list-hunks again')
        selection.update(changed=sorted(changed), deleted=sorted(deleted), content=content,
                         left_uncommitted=sorted(left))

    def _hunk_sides(self, directory: str, obj_store, vault_id, read_key, old_entry, path: str, on_disk: bool) -> tuple:
        """(HEAD's bytes or None, the working copy's bytes or None) for one path."""
        base = self._blob_bytes(obj_store, vault_id, read_key, old_entry) if old_entry else None
        work = None
        if on_disk:
            work = Vault__Path_Guard().read_regular(os.path.join(directory, path), path)
        return base, work

    def _blob_bytes(self, obj_store, vault_id, read_key, entry: dict) -> bytes:
        """A HEAD blob's plaintext: from the local store, else fetched from the server and
        accepted only when its content address is the id the tree names."""
        from sgit_ai.storage.Vault__Object_Store import Vault__Object_Missing_Error
        blob_id = str(entry['blob_id'])
        try:
            ciphertext = obj_store.load(blob_id)
        except Vault__Object_Missing_Error:
            ciphertext = self._make_blob_fetcher(vault_id)(blob_id)
            if not ciphertext or obj_store.store(ciphertext) != blob_id:
                raise RuntimeError(f'the committed version of a file is not in this clone and could not be '
                                   f'fetched ({blob_id}); run sgit pull and try again')
        return self.crypto.decrypt(read_key, ciphertext)

    def list_hunks(self, directory: str, paths: list = None, cwd: str = None, split: bool = False):
        """Schema__Hunk_List of the changed files (under `paths` when given): what
        `sgit commit --list-hunks` prints and `--hunk` selects from."""
        from sgit_ai.core.actions.commit.Vault__Hunks import Vault__Hunks
        from sgit_ai.schemas.commit.Schema__Hunk_List import Schema__Hunk_List
        c            = self._init_components(directory)
        local_config = self._read_local_config(directory, c.storage)
        head_id, old_flat = self._head_flat(directory, c, local_config)
        disk         = self._scan_local_directory(directory, warn_links=True)
        changed      = [p for p, e in disk.items() if (old_flat.get(p) or {}).get('content_hash') != e.get('content_hash')]
        selection    = self._select_paths(directory, paths, cwd, old_flat, disk, changed,
                                          bool(local_config.sparse))
        result       = Schema__Hunk_List(base_commit=head_id or None)
        hunker       = Vault__Hunks()
        for path in sorted(selection['changed'] + selection['deleted']):
            base, work = self._hunk_sides(directory, c.obj_store, c.vault_id, c.read_key, old_flat.get(path), path,
                                          path in selection['changed'])
            work_hash  = self.crypto.content_hash(work) if work is not None else ''
            result.files.append(hunker.hunks_of(path, base, work, (old_flat.get(path) or {}).get('content_hash', ''),
                                                work_hash, split=split))
        return result

    def _head_flat(self, directory: str, c, local_config) -> tuple:
        """(head commit id, HEAD's flat map) of this clone's branch, as commit() reads them."""
        branch_index = c.branch_manager.load_branch_index(directory, c.branch_index_file_id, c.read_key)
        branch_meta  = c.branch_manager.get_branch_by_id(branch_index, str(local_config.my_branch_id))
        if not branch_meta:
            raise RuntimeError(f'Branch not found: {local_config.my_branch_id}')
        head_id = c.ref_manager.read_ref(str(branch_meta.head_ref_id), c.read_key)
        if not head_id:
            return '', {}
        commit   = Vault__Commit(crypto=self.crypto, pki=c.pki, object_store=c.obj_store,
                                 ref_manager=c.ref_manager).load_commit(head_id, c.read_key)
        scope    = Vault__Scope().from_local_config(local_config)
        if scope.is_scoped():
            flat, _ = Vault__Scoped_Tree(crypto=self.crypto, obj_store=c.obj_store).flatten(
                str(commit.tree_id), c.read_key, scope)
            return head_id, flat
        return head_id, Vault__Sub_Tree(crypto=self.crypto, obj_store=c.obj_store).flatten(str(commit.tree_id), c.read_key)

    def _unmatched_message(self, directory: str, pathspec, unmatched: list) -> str:
        lines = []
        for typed, pattern in zip(pathspec.typed, pathspec.patterns):
            if str(typed) not in unmatched:
                continue
            full = os.path.join(directory, str(pattern))
            if str(pattern) and not pathspec.is_glob(str(pattern)) and os.path.lexists(full):
                lines.append(f"pathspec '{typed}' is ignored by .gitignore, or is not a file sgit commits")
            else:
                lines.append(f"pathspec '{typed}' did not match any file known to sgit")
        return '; '.join(lines)

    def _read_entry(self, directory: str, rel_path: str, sub_tree, old_entry, read_key) -> dict:
        """The tree entry for one working-copy file, or None to keep the committed one
        (a link, or a path under a link: sgit never follows them)."""
        full_path = os.path.join(directory, rel_path)
        if os.path.islink(full_path) or not os.path.isfile(full_path) or \
                Vault__Path_Guard().has_link_component(os.path.abspath(directory), os.path.abspath(full_path)):
            return None
        content = Vault__Path_Guard().read_regular(full_path, rel_path)   # O_NOFOLLOW (L4); raises if unreadable (B2)
        if content is None:
            return None
        return self._entry_for(rel_path, content, sub_tree, old_entry, read_key)

    def _entry_for(self, rel_path: str, content: bytes, sub_tree, old_entry, read_key) -> dict:
        blob_id, is_large, file_hash = sub_tree.encrypt_or_reuse_blob(content, old_entry, read_key)
        return dict(blob_id      = blob_id,
                    size         = len(content),
                    content_hash = file_hash,
                    content_type = mimetypes.guess_type(rel_path)[0] or 'application/octet-stream',
                    large        = is_large)

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
                   message: str = '', also: dict = None, signing=None) -> dict:
        """Write file content directly to vault HEAD without scanning the working directory.

        `also` is an optional {vault_path: bytes} dict for atomic multi-file writes.
        Returns dict: {blob_id, commit_id, message, paths, unchanged}.
        If content is identical to the existing entry, no new commit is created.
        """
        from sgit_ai.core.Vault__Operation_Guard import Vault__Operation_Guard
        Vault__Operation_Guard().check(directory, 'write')                 # it would commit over a merge in progress
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
        message_limit = Vault__Commit_Message().limit_for(branch_index)
        Vault__Commit_Message().check(message, message_limit)            # before any blob is written

        ref_id    = str(branch_meta.head_ref_id)
        parent_id = ref_manager.read_ref(ref_id, read_key)

        sub_tree = Vault__Sub_Tree(crypto=self.crypto, obj_store=obj_store)
        scope    = Vault__Scope().from_local_config(local_config)

        old_flat = {}
        old_dirs = {}                                                      # unchanged folders keep their ids (F3)
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
                old_dirs = sub_tree.flatten_dirs(str(old_commit.tree_id), read_key)

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

        root_tree_id = sub_tree.build_from_flat(flat, read_key, opaque=opaque,
                                                old_flat_entries=old_flat, old_tree_ids=old_dirs)

        signing_key = self._load_signing_key(key_manager, branch_meta, storage, directory)
        user_signer = self._user_signer(signing)

        vault_commit = Vault__Commit(crypto=self.crypto, pki=pki, object_store=obj_store, ref_manager=ref_manager,
                                     max_message_bytes=message_limit)
        auto_msg  = message or f'write {path}'
        commit_id = vault_commit.create_commit(tree_id     = root_tree_id,
                                               read_key    = read_key,
                                               parent_ids  = [parent_id] if parent_id else [],
                                               message     = auto_msg,
                                               branch_id   = branch_id,
                                               signing_key = signing_key,
                                               author_key_id = str(branch_meta.public_key_id) if (signing_key and branch_meta.public_key_id) else None,
                                               **self._signer_kw(user_signer))
        for file_path, file_content in files_to_write.items():                    # the files first, then the ref: a
            dest = Vault__Path_Guard().safe_join(os.path.abspath(directory), file_path)   # failed write leaves no
            os.makedirs(os.path.dirname(dest), exist_ok=True)                    # commit the working copy does not
            with open(dest, 'wb') as f:                                          # match (review 0a0707d P1)
                f.write(file_content)
        ref_manager.write_ref(ref_id, commit_id, read_key)

        result = dict(blob_id   = result_blobs.get(path),
                      commit_id = commit_id,
                      message   = auto_msg,
                      paths     = result_blobs,
                      unchanged = False)
        if user_signer is not None:
            result['signed_with'] = self._signed_with(user_signer, vault_commit, commit_id, read_key)
        return result

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
        from sgit_ai.storage.Vault__Path_Guard import Vault__Unsafe_Path_Error
        for raw, data in [(path, content)] + list((also or {}).items()):
            norm = posixpath.normpath(str(raw or '').replace(os.sep, '/'))
            if norm in ('.', '') or str(raw).endswith(('/', os.sep)):          # `sgit write .` committed an entry
                raise Vault__Unsafe_Path_Error(                                 # named '.' (review 0a0707d P1)
                    f'refusing {raw!r}: `sgit write` needs a file path, not a folder')
            dest = guard.safe_join(base, raw)
            if os.path.isdir(dest):
                raise Vault__Unsafe_Path_Error(f'refusing {raw!r}: it is a folder in the working copy')
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
