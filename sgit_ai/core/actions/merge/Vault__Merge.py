import os
from   osbot_utils.type_safe.Type_Safe                import Type_Safe
from   sgit_ai.crypto.Vault__Crypto               import Vault__Crypto
from   sgit_ai.storage.Vault__Object_Store        import Vault__Object_Store
from   sgit_ai.storage.Vault__Path_Guard          import Vault__Path_Guard, Vault__Unsafe_Path_Error
from   sgit_ai.core.Vault__Ignore                 import Vault__Ignore

CONFLICT_SUFFIX = '.conflict'


class Vault__Merge(Type_Safe):
    crypto : Vault__Crypto

    def three_way_merge(self, base_map: dict, ours_map: dict, theirs_map: dict,
                        obj_store: Vault__Object_Store = None, read_key: bytes = None,
                        content_merger=None) -> dict:
        """Perform a three-way merge of two flat file maps against a common base.

        All three args are {path: {'blob_id': str, ...}} dicts from sub_tree.flatten().

        Two entries are the same file when their blob ids are equal or, given the store
        and the read key, when they hold the same bytes: blobs are encrypted with a
        random IV, so two clones writing the same content get different ids, and that
        used to be a conflict (design__00 F4/B3). Equal content_hash and size select the
        candidates; the decrypted bytes decide.

        `content_merger` (a Vault__Content_Merger, the `lines` style): a file both sides
        changed differently is merged line by line. Clean → a new entry (in `modified`
        and `line_merged`); conflict → ours' entry stays and the marker bytes go to
        `marker_conflicts`; anything else → today's whole-file conflict, the reason in
        `fallbacks`. Without it, nothing changes.
        """
        same_cache       = {}
        line_merged      = []
        marker_conflicts = {}                            # path -> (marker bytes, hunks)
        fallbacks        = {}                            # path -> why it is a whole-file conflict

        def content_conflict(path, base_entry, ours_entry, theirs_entry):
            """Both sides changed `path` differently: line-merge it when asked, else (or
            when it cannot be) a whole-file conflict keeping ours."""
            merged_map[path] = ours_entry
            if content_merger is None:
                conflicts.append(path)
                return
            result = content_merger.merge_entry(path, base_entry, ours_entry, theirs_entry, read_key)
            outcome = result['outcome'].value
            if outcome == 'clean':
                merged_map[path] = result['entry']
                modified.append(path)
                line_merged.append(path)
            elif outcome == 'conflict':
                conflicts.append(path)
                marker_conflicts[path] = (result['markers'], result['hunks'])
            else:
                conflicts.append(path)
                fallbacks[path] = result.get('reason') or outcome

        def same(a: dict, b: dict) -> bool:
            if a is None or b is None:
                return False
            a_bid, b_bid = a.get('blob_id'), b.get('blob_id')
            if a_bid == b_bid:
                return True
            if obj_store is None or read_key is None or not a_bid or not b_bid:
                return False
            if not a.get('content_hash') or a.get('content_hash') != b.get('content_hash'):
                return False
            if a.get('size') is not None and b.get('size') is not None and a.get('size') != b.get('size'):
                return False
            key = (a_bid, b_bid) if a_bid < b_bid else (b_bid, a_bid)
            if key not in same_cache:
                same_cache[key] = self.same_content(obj_store, read_key, a_bid, b_bid)
            return same_cache[key]

        all_paths = sorted(set(base_map) | set(ours_map) | set(theirs_map))

        merged_map = {}
        conflicts  = []
        added      = []
        modified   = []
        deleted    = []

        for path in all_paths:
            in_base   = path in base_map
            in_ours   = path in ours_map
            in_theirs = path in theirs_map

            base_entry, ours_entry, theirs_entry = base_map.get(path), ours_map.get(path), theirs_map.get(path)

            ours_changed   = not same(ours_entry,   base_entry)
            theirs_changed = not same(theirs_entry, base_entry)
            ours_is_theirs = same(ours_entry, theirs_entry)

            if in_base and in_ours and in_theirs and not ours_changed and not theirs_changed:
                merged_map[path] = ours_map[path]
            elif in_base and in_ours and in_theirs and not ours_changed and theirs_changed:
                merged_map[path] = theirs_map[path]
                modified.append(path)
            elif in_base and in_ours and in_theirs and ours_changed and not theirs_changed:
                merged_map[path] = ours_map[path]
            elif in_base and in_ours and in_theirs and ours_changed and theirs_changed and ours_is_theirs:
                merged_map[path] = ours_map[path]
            elif in_base and in_ours and in_theirs and ours_changed and theirs_changed and not ours_is_theirs:
                content_conflict(path, base_entry, ours_entry, theirs_entry)
            elif not in_base and not in_ours and in_theirs:
                merged_map[path] = theirs_map[path]
                added.append(path)
            elif not in_base and in_ours and not in_theirs:
                merged_map[path] = ours_map[path]
            elif not in_base and in_ours and in_theirs and ours_is_theirs:
                merged_map[path] = ours_map[path]
            elif not in_base and in_ours and in_theirs and not ours_is_theirs:
                content_conflict(path, None, ours_entry, theirs_entry)                 # add/add: an empty base
            elif in_base and in_ours and not in_theirs and not ours_changed:
                deleted.append(path)
            elif in_base and not in_ours and in_theirs and not theirs_changed:
                pass
            elif in_base and in_ours and not in_theirs and ours_changed:
                merged_map[path] = ours_map[path]
                conflicts.append(path)
            elif in_base and not in_ours and in_theirs and theirs_changed:
                merged_map[path] = theirs_map[path]
                conflicts.append(path)
            elif in_base and not in_ours and not in_theirs:
                deleted.append(path)
            else:
                if in_ours:
                    merged_map[path] = ours_map[path]
                elif in_theirs:
                    merged_map[path] = theirs_map[path]

        return dict(merged_map=merged_map, conflicts=conflicts,
                    added=added, modified=modified, deleted=deleted,
                    line_merged=line_merged, marker_conflicts=marker_conflicts, fallbacks=fallbacks)

    def write_conflict_files(self, directory: str, conflicts: list[str],
                             theirs_map: dict,
                             obj_store: Vault__Object_Store,
                             read_key: bytes, skip: set = None) -> list[str]:
        """Write .conflict files for conflicting paths (not those in `skip`: a line-merge
        conflict has its markers in the file itself)."""
        written_files = []
        for path in conflicts:
            if skip and path in skip:
                continue
            entry = theirs_map.get(path)
            if not entry:
                continue
            blob_id = entry.get('blob_id')
            if not blob_id:
                continue
            try:
                # path is decrypted vault data — contain it before writing.
                conflict_path = Vault__Path_Guard().safe_join(directory, path + CONFLICT_SUFFIX)
                ciphertext    = obj_store.load(blob_id)
                plaintext     = self.crypto.decrypt(read_key, ciphertext)
                os.makedirs(os.path.dirname(conflict_path), exist_ok=True)
                with open(conflict_path, 'wb') as f:
                    f.write(plaintext)
                written_files.append(path + CONFLICT_SUFFIX)
            except Exception:
                pass
        return written_files

    def same_content(self, obj_store: Vault__Object_Store, read_key: bytes, blob_a: str, blob_b: str) -> bool:
        """True when both blobs decrypt to the same bytes; False when either cannot be read."""
        try:
            return (self.crypto.decrypt(read_key, obj_store.load(blob_a)) ==
                    self.crypto.decrypt(read_key, obj_store.load(blob_b)))
        except Exception:
            return False

    def unresolved(self, directory: str, merge_state) -> list[str]:
        """The merge's conflict paths not yet resolved. A whole-file conflict is resolved
        when its `<path>.conflict` is gone (deleted by hand, or by sgit resolve); a
        line-merge conflict when its file no longer holds a complete marker block (edited
        by hand, or sgit resolve), as an agent's "edit, then commit" loop expects."""
        paths   = []
        markers = {str(p) for p in (getattr(merge_state, 'marker_paths', None) or [])}
        for path in [str(p) for p in (merge_state.conflict_paths or [])]:
            if path in markers:
                if self.has_marker_block(directory, path):
                    paths.append(path)
                continue
            try:
                conflict_path = Vault__Path_Guard().safe_join(directory, path + CONFLICT_SUFFIX)
            except Vault__Unsafe_Path_Error:                  # never a file of this working copy
                conflict_path = None
            if conflict_path and os.path.lexists(conflict_path):
                paths.append(path)
        return sorted(paths)

    def has_marker_block(self, directory: str, path: str) -> bool:
        """A `<<<<<<<` line, then a `=======` line, then a `>>>>>>>` line, in that order
        (a lone `=======`, a reStructuredText underline, is not a block)."""
        try:
            content = Vault__Path_Guard().read_regular(Vault__Path_Guard().safe_join(directory, path), path)
        except Exception:                                    # unreadable: the commit's scan names it
            return False
        stage = 0
        for line in (content or b'').split(b'\n'):
            line = line.rstrip(b'\r')
            if stage == 0 and (line == b'<' * 7 or line.startswith(b'<' * 7 + b' ')):
                stage = 1
            elif stage == 1 and line == b'=' * 7:
                stage = 2
            elif stage == 2 and (line == b'>' * 7 or line.startswith(b'>' * 7 + b' ')):
                return True
        return False

    def write_marker_files(self, directory: str, marker_conflicts: dict) -> list[str]:
        """Write each line-merge conflict's marked-up content over its working file
        (the pull guard has already refused an uncommitted edit there). Paths come from
        vault data: contained like every other merge write."""
        written = []
        for path, (content, _hunks) in sorted(marker_conflicts.items()):
            if not Vault__Path_Guard().is_writable(directory, path):
                continue
            full_path = Vault__Path_Guard().safe_join(directory, path)
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            with open(full_path, 'wb') as f:
                f.write(content)
            written.append(path)
        return written

    def remove_conflict_files(self, directory: str) -> list[str]:
        ignore  = Vault__Ignore().load_gitignore(directory).load_tracked_from_vault(directory, crypto=self.crypto)
        removed = []
        for root, dirs, files in os.walk(directory):
            rel_root = os.path.relpath(root, directory).replace(os.sep, '/')
            if rel_root == '.':
                rel_root = ''
            dirs[:] = [d for d in dirs
                       if d != '.sg_vault'
                       and not ignore.should_ignore_dir(f'{rel_root}/{d}' if rel_root else d)]
            for filename in files:
                if filename.endswith(CONFLICT_SUFFIX):
                    full_path = os.path.join(root, filename)
                    os.remove(full_path)
                    rel_path = os.path.relpath(full_path, directory).replace(os.sep, '/')
                    removed.append(rel_path)
        return removed

    def has_conflicts(self, directory: str, seen: list = None) -> bool:
        """`seen`: the conflict files a scan of this directory just listed (its walk
        prunes the same folders), so a commit does not walk the working tree twice."""
        if seen is not None:
            return bool(seen)
        ignore = Vault__Ignore().load_gitignore(directory).load_tracked_from_vault(directory, crypto=self.crypto)
        for root, dirs, files in os.walk(directory):
            rel_root = os.path.relpath(root, directory).replace(os.sep, '/')
            if rel_root == '.':
                rel_root = ''
            dirs[:] = [d for d in dirs
                       if d != '.sg_vault'
                       and not ignore.should_ignore_dir(f'{rel_root}/{d}' if rel_root else d)]
            for filename in files:
                if filename.endswith(CONFLICT_SUFFIX):
                    return True
        return False
