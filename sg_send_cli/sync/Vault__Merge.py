import os
from   osbot_utils.type_safe.Type_Safe                import Type_Safe
from   sg_send_cli.crypto.Vault__Crypto               import Vault__Crypto
from   sg_send_cli.objects.Vault__Object_Store        import Vault__Object_Store
from   sg_send_cli.schemas.Schema__Object_Tree        import Schema__Object_Tree
from   sg_send_cli.schemas.Schema__Object_Tree_Entry  import Schema__Object_Tree_Entry

CONFLICT_SUFFIX = '.conflict'


class Vault__Merge(Type_Safe):
    crypto : Vault__Crypto

    def three_way_merge(self, base_tree: Schema__Object_Tree,
                        ours_tree: Schema__Object_Tree,
                        theirs_tree: Schema__Object_Tree) -> dict:
        """Perform a three-way merge of two trees against a common base.

        Returns dict with:
            merged_tree : Schema__Object_Tree  - the merged result
            conflicts   : list[str]            - list of conflicting paths
            added       : list[str]            - paths added
            modified    : list[str]            - paths modified
            deleted     : list[str]            - paths deleted
        """
        base_map   = self._tree_to_map(base_tree)
        ours_map   = self._tree_to_map(ours_tree)
        theirs_map = self._tree_to_map(theirs_tree)

        all_paths = sorted(set(base_map.keys()) | set(ours_map.keys()) | set(theirs_map.keys()))

        merged_entries = []
        conflicts      = []
        added          = []
        modified       = []
        deleted        = []

        for path in all_paths:
            in_base   = path in base_map
            in_ours   = path in ours_map
            in_theirs = path in theirs_map

            base_entry   = base_map.get(path)
            ours_entry   = ours_map.get(path)
            theirs_entry = theirs_map.get(path)

            base_bid   = self._blob_id(base_entry)
            ours_bid   = self._blob_id(ours_entry)
            theirs_bid = self._blob_id(theirs_entry)

            ours_changed   = ours_bid   != base_bid
            theirs_changed = theirs_bid != base_bid

            # Case 1: File in all three, unchanged on both sides
            if in_base and in_ours and in_theirs and not ours_changed and not theirs_changed:
                merged_entries.append(ours_entry)

            # Case 2: Changed only on theirs side
            elif in_base and in_ours and in_theirs and not ours_changed and theirs_changed:
                merged_entries.append(theirs_entry)
                modified.append(path)

            # Case 3: Changed only on ours side
            elif in_base and in_ours and in_theirs and ours_changed and not theirs_changed:
                merged_entries.append(ours_entry)

            # Case 4: Changed on both sides, same result
            elif in_base and in_ours and in_theirs and ours_changed and theirs_changed and ours_bid == theirs_bid:
                merged_entries.append(ours_entry)

            # Case 5: Changed on both sides, different results -> CONFLICT
            elif in_base and in_ours and in_theirs and ours_changed and theirs_changed and ours_bid != theirs_bid:
                merged_entries.append(ours_entry)
                conflicts.append(path)

            # Case 6: Added only on theirs side (not in base, not in ours)
            elif not in_base and not in_ours and in_theirs:
                merged_entries.append(theirs_entry)
                added.append(path)

            # Case 7: Added only on ours side (not in base, not in theirs)
            elif not in_base and in_ours and not in_theirs:
                merged_entries.append(ours_entry)

            # Case 8: Added on both sides, same content
            elif not in_base and in_ours and in_theirs and ours_bid == theirs_bid:
                merged_entries.append(ours_entry)

            # Case 9: Added on both sides, different content -> CONFLICT
            elif not in_base and in_ours and in_theirs and ours_bid != theirs_bid:
                merged_entries.append(ours_entry)
                conflicts.append(path)

            # Case 10: Deleted on theirs side, unchanged on ours
            elif in_base and in_ours and not in_theirs and not ours_changed:
                deleted.append(path)

            # Case 11: Deleted on ours side, unchanged on theirs
            elif in_base and not in_ours and in_theirs and not theirs_changed:
                pass  # already deleted on our side

            # Case 12: Deleted on theirs side, but modified on ours -> CONFLICT
            elif in_base and in_ours and not in_theirs and ours_changed:
                merged_entries.append(ours_entry)
                conflicts.append(path)

            # Case 13: Deleted on ours side, but modified on theirs -> CONFLICT
            elif in_base and not in_ours and in_theirs and theirs_changed:
                merged_entries.append(theirs_entry)
                conflicts.append(path)

            # Case 14: Deleted on both sides
            elif in_base and not in_ours and not in_theirs:
                deleted.append(path)

            # Case 15: Only in base (deleted on both) — already covered above
            else:
                if in_ours:
                    merged_entries.append(ours_entry)
                elif in_theirs:
                    merged_entries.append(theirs_entry)

        merged_tree = Schema__Object_Tree(schema='tree_v1')
        merged_tree.entries = merged_entries

        return dict(merged_tree = merged_tree,
                    conflicts   = conflicts,
                    added       = added,
                    modified    = modified,
                    deleted     = deleted)

    def write_conflict_files(self, directory: str, conflicts: list,
                             ours_tree: Schema__Object_Tree,
                             theirs_tree: Schema__Object_Tree,
                             obj_store: Vault__Object_Store,
                             read_key: bytes) -> list:
        """Write .conflict files for conflicting paths, containing theirs version."""
        theirs_map     = self._tree_to_map(theirs_tree)
        written_files  = []

        for path in conflicts:
            theirs_entry = theirs_map.get(path)
            if not theirs_entry:
                continue
            blob_id = self._blob_id(theirs_entry)
            if not blob_id:
                continue
            try:
                ciphertext = obj_store.load(blob_id)
                plaintext  = self.crypto.decrypt(read_key, ciphertext)
                conflict_path = os.path.join(directory, path + CONFLICT_SUFFIX)
                os.makedirs(os.path.dirname(conflict_path), exist_ok=True)
                with open(conflict_path, 'wb') as f:
                    f.write(plaintext)
                written_files.append(path + CONFLICT_SUFFIX)
            except Exception:
                pass

        return written_files

    def remove_conflict_files(self, directory: str) -> list:
        """Remove all .conflict files from the working directory."""
        removed = []
        for root, dirs, files in os.walk(directory):
            dirs[:] = [d for d in dirs if d != '.sg_vault' and not d.startswith('.')]
            for filename in files:
                if filename.endswith(CONFLICT_SUFFIX):
                    full_path = os.path.join(root, filename)
                    os.remove(full_path)
                    rel_path = os.path.relpath(full_path, directory).replace(os.sep, '/')
                    removed.append(rel_path)
        return removed

    def has_conflicts(self, directory: str) -> bool:
        """Check if there are any .conflict files in the working directory."""
        for root, dirs, files in os.walk(directory):
            dirs[:] = [d for d in dirs if d != '.sg_vault' and not d.startswith('.')]
            for filename in files:
                if filename.endswith(CONFLICT_SUFFIX):
                    return True
        return False

    def _tree_to_map(self, tree: Schema__Object_Tree) -> dict:
        result = {}
        for entry in tree.entries:
            path = str(entry.path) if entry.path else str(entry.name)
            result[path] = entry
        return result

    def _blob_id(self, entry) -> str:
        if entry is None:
            return None
        return str(entry.blob_id) if entry.blob_id else None
