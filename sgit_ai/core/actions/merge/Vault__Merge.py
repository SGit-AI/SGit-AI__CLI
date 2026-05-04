import os
from   osbot_utils.type_safe.Type_Safe                import Type_Safe
from   sgit_ai.crypto.Vault__Crypto               import Vault__Crypto
from   sgit_ai.storage.Vault__Object_Store        import Vault__Object_Store

CONFLICT_SUFFIX = '.conflict'


class Vault__Merge(Type_Safe):
    crypto : Vault__Crypto

    def three_way_merge(self, base_map: dict, ours_map: dict, theirs_map: dict) -> dict:
        """Perform a three-way merge of two flat file maps against a common base.

        All three args are {path: {'blob_id': str, ...}} dicts from sub_tree.flatten().
        """
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

            base_bid   = base_map.get(path, {}).get('blob_id')
            ours_bid   = ours_map.get(path, {}).get('blob_id')
            theirs_bid = theirs_map.get(path, {}).get('blob_id')

            ours_changed   = ours_bid   != base_bid
            theirs_changed = theirs_bid != base_bid

            if in_base and in_ours and in_theirs and not ours_changed and not theirs_changed:
                merged_map[path] = ours_map[path]
            elif in_base and in_ours and in_theirs and not ours_changed and theirs_changed:
                merged_map[path] = theirs_map[path]
                modified.append(path)
            elif in_base and in_ours and in_theirs and ours_changed and not theirs_changed:
                merged_map[path] = ours_map[path]
            elif in_base and in_ours and in_theirs and ours_changed and theirs_changed and ours_bid == theirs_bid:
                merged_map[path] = ours_map[path]
            elif in_base and in_ours and in_theirs and ours_changed and theirs_changed and ours_bid != theirs_bid:
                merged_map[path] = ours_map[path]
                conflicts.append(path)
            elif not in_base and not in_ours and in_theirs:
                merged_map[path] = theirs_map[path]
                added.append(path)
            elif not in_base and in_ours and not in_theirs:
                merged_map[path] = ours_map[path]
            elif not in_base and in_ours and in_theirs and ours_bid == theirs_bid:
                merged_map[path] = ours_map[path]
            elif not in_base and in_ours and in_theirs and ours_bid != theirs_bid:
                merged_map[path] = ours_map[path]
                conflicts.append(path)
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
                    added=added, modified=modified, deleted=deleted)

    def write_conflict_files(self, directory: str, conflicts: list[str],
                             theirs_map: dict,
                             obj_store: Vault__Object_Store,
                             read_key: bytes) -> list[str]:
        """Write .conflict files for conflicting paths."""
        written_files = []
        for path in conflicts:
            entry = theirs_map.get(path)
            if not entry:
                continue
            blob_id = entry.get('blob_id')
            if not blob_id:
                continue
            try:
                ciphertext    = obj_store.load(blob_id)
                plaintext     = self.crypto.decrypt(read_key, ciphertext)
                conflict_path = os.path.join(directory, path + CONFLICT_SUFFIX)
                os.makedirs(os.path.dirname(conflict_path), exist_ok=True)
                with open(conflict_path, 'wb') as f:
                    f.write(plaintext)
                written_files.append(path + CONFLICT_SUFFIX)
            except Exception:
                pass
        return written_files

    def remove_conflict_files(self, directory: str) -> list[str]:
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
        for root, dirs, files in os.walk(directory):
            dirs[:] = [d for d in dirs if d != '.sg_vault' and not d.startswith('.')]
            for filename in files:
                if filename.endswith(CONFLICT_SUFFIX):
                    return True
        return False
