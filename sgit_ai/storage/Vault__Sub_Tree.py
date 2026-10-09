import json
import mimetypes
import os
from   osbot_utils.type_safe.Type_Safe                import Type_Safe
from   sgit_ai.crypto.Vault__Crypto               import Vault__Crypto
from   sgit_ai.storage.Vault__Path_Guard            import Vault__Path_Guard

LARGE_BLOB_THRESHOLD = 4 * 1024 * 1024  # 4 MB — safe margin under Lambda base64 limit
from   sgit_ai.storage.Vault__Object_Store        import Vault__Object_Store
from   sgit_ai.schemas.Schema__Object_Tree        import Schema__Object_Tree
from   sgit_ai.schemas.Schema__Object_Tree_Entry  import Schema__Object_Tree_Entry


class Vault__Sub_Tree(Type_Safe):
    """Build and traverse sub-tree structures.

    Stored tree entries contain ONLY encrypted metadata:
      blob_id/tree_id + name_enc + size_enc + content_hash_enc + content_type_enc

    Plaintext values (path, name, size, content_hash, content_type) exist only
    in-memory as dicts returned by flatten() — never serialized.
    """
    crypto    : Vault__Crypto
    obj_store : Vault__Object_Store

    def build(self, directory: str, file_map: dict, read_key: bytes,
              old_flat_entries: dict = None, opaque: dict = None) -> str:
        """Build sub-tree objects bottom-up from working directory files.

        `opaque` — {dir_path: [Schema__Object_Tree_Entry, …]} entries carried
        into those folders verbatim (a scoped clone's out-of-scope siblings,
        known only by id). None/empty for a full clone: identical behaviour.

        Returns root tree object ID (obj-cas-imm-{hash}).
        """
        if old_flat_entries is None:
            old_flat_entries = {}
        dir_contents, all_dirs = (self._populate_dir_contents(file_map.keys(), extra_dirs=opaque.keys()) if opaque
                                  else self._populate_dir_contents(file_map.keys()))

        guard    = Vault__Path_Guard()
        base_abs = os.path.abspath(directory)

        def make_entry(filename, rel_path):
            if rel_path not in file_map:
                return None
            local_file = os.path.join(directory, rel_path)
            if guard.has_link_component(base_abs, os.path.abspath(local_file)):    # never read through a link:
                old = old_flat_entries.get(rel_path)                               # a tracked path keeps its committed entry
                return self._entry_from_flat(filename, old, read_key) if old and old.get('blob_id') else None
            if not os.path.isfile(local_file):
                return None
            with open(local_file, 'rb') as f:
                content = f.read()
            blob_id, is_large, file_hash = self.encrypt_or_reuse_blob(
                content, old_flat_entries.get(rel_path), read_key)
            content_type = mimetypes.guess_type(filename)[0] or 'application/octet-stream'
            return Schema__Object_Tree_Entry(
                blob_id          = blob_id,
                name_enc         = self.crypto.encrypt_metadata_deterministic(read_key, filename),
                size_enc         = self.crypto.encrypt_metadata_deterministic(read_key, str(len(content))),
                content_hash_enc = self.crypto.encrypt_metadata_deterministic(read_key, file_hash),
                content_type_enc = self.crypto.encrypt_metadata_deterministic(read_key, content_type),
                large            = is_large,
            )

        return self._build_tree_from_dir_contents(dir_contents, all_dirs, make_entry, read_key, opaque)

    def _entry_from_flat(self, filename: str, entry: dict, read_key: bytes):
        content_type = entry.get('content_type') or mimetypes.guess_type(filename)[0] or 'application/octet-stream'
        return Schema__Object_Tree_Entry(
            blob_id          = entry['blob_id'],
            name_enc         = self.crypto.encrypt_metadata_deterministic(read_key, filename),
            size_enc         = self.crypto.encrypt_metadata_deterministic(read_key, str(entry.get('size', 0))),
            content_hash_enc = self.crypto.encrypt_metadata_deterministic(read_key, str(entry.get('content_hash', ''))),
            content_type_enc = self.crypto.encrypt_metadata_deterministic(read_key, content_type),
            large            = bool(entry.get('large', False)),
        )

    def build_from_flat(self, flat_map: dict, read_key: bytes, opaque: dict = None) -> str:
        """Build sub-tree objects from a flat {path: dict} map.

        Used after merge — blobs already exist in the object store,
        we just need to construct the tree structure with encrypted metadata.
        `opaque` as in build().

        Returns root tree object ID.
        """
        dir_contents, all_dirs = (self._populate_dir_contents(flat_map.keys(), extra_dirs=opaque.keys()) if opaque
                                  else self._populate_dir_contents(flat_map.keys()))

        def make_entry(filename, rel_path):
            entry_data = flat_map.get(rel_path)
            if not entry_data:
                return None
            content_type = entry_data.get('content_type', '') or mimetypes.guess_type(filename)[0] or 'application/octet-stream'
            return Schema__Object_Tree_Entry(
                blob_id          = entry_data['blob_id'],
                name_enc         = self.crypto.encrypt_metadata_deterministic(read_key, filename),
                size_enc         = self.crypto.encrypt_metadata_deterministic(read_key, str(entry_data.get('size', 0))),
                content_hash_enc = self.crypto.encrypt_metadata_deterministic(read_key, entry_data.get('content_hash', '')),
                content_type_enc = self.crypto.encrypt_metadata_deterministic(read_key, content_type),
                large            = entry_data.get('large', False),
            )

        return self._build_tree_from_dir_contents(dir_contents, all_dirs, make_entry, read_key, opaque)

    def flatten(self, tree_id: str, read_key: bytes, prefix: str = '') -> dict:
        """Walk sub-trees recursively, return flat {path: dict} map.

        Returns {path: {'blob_id': str, 'size': int, 'content_hash': str, 'content_type': str}}
        """
        result = {}
        tree   = self._load_tree(tree_id, read_key)

        for entry in tree.entries:
            name = self._decrypt_name(entry, read_key)
            if not name:
                continue

            full_path = f'{prefix}/{name}' if prefix else name

            if entry.blob_id:
                result[full_path] = dict(
                    blob_id      = str(entry.blob_id),
                    size         = self._decrypt_size(entry, read_key),
                    content_hash = self._decrypt_content_hash(entry, read_key),
                    content_type = self._decrypt_content_type(entry, read_key),
                    large        = entry.large,
                )
            elif entry.tree_id:
                result.update(self.flatten(str(entry.tree_id), read_key, full_path))

        return result

    def resolve_path_target(self, tree_id: str, path: str, read_key: bytes) -> tuple:
        """Resolve a vault-relative path to (target_kind, object_id).

        Returns ('blob', blob_id) for a file, ('tree', tree_id) for a folder, or
        (None, None) if the path does not exist in this tree. Used by the cache
        layer to build pointer objects, which may target either a file or a
        folder/subtree (the latter is not present in flatten() maps).
        """
        parts   = [p for p in path.split('/') if p]
        if not parts:
            return 'tree', tree_id                       # the root itself
        current = tree_id
        for index, part in enumerate(parts):
            tree  = self._load_tree(current, read_key)
            match = None
            for entry in tree.entries:
                if self._decrypt_name(entry, read_key) == part:
                    match = entry
                    break
            if match is None:
                return None, None
            is_last = (index == len(parts) - 1)
            if match.blob_id:
                return ('blob', str(match.blob_id)) if is_last else (None, None)
            if match.tree_id:
                if is_last:
                    return 'tree', str(match.tree_id)
                current = str(match.tree_id)
            else:
                return None, None
        return None, None

    def checkout(self, directory: str, tree_id: str, read_key: bytes,
                 prefix: str = '', missing: list = None) -> None:
        """Recursively extract files from a tree into the working directory.
        With `missing` (a list) a file whose blob is not in the store is recorded
        there instead of warned about, so the caller can refuse the whole result."""
        tree = self._load_tree(tree_id, read_key)

        for entry in tree.entries:
            name = self._decrypt_name(entry, read_key)
            if not name:
                continue

            full_path = f'{prefix}/{name}' if prefix else name

            if entry.blob_id:
                # Entry names are attacker-influenced (chosen by the vault author);
                # contain the write so a '../' or absolute name cannot escape, and
                # refuse structural paths that stay INSIDE the directory but would
                # write into .git/ or the vault's own internals (A2) — safe_join
                # cannot catch these because they do not escape.
                if Vault__Path_Guard().is_protected(full_path):
                    import sys
                    print(f'  warning: refusing to write structural path from vault '
                          f'data: {full_path}', file=sys.stderr)
                    continue
                file_path = Vault__Path_Guard().safe_join(directory, full_path)
                try:
                    ciphertext = self.obj_store.load(str(entry.blob_id))
                except FileNotFoundError:
                    # A blob refused by the SP-1 verify-before-write (or absent on
                    # the host) is not in the store; skip this file rather than
                    # abort the whole checkout (fail-soft per object, I7).
                    if missing is not None:
                        missing.append(full_path)
                        continue
                    import sys
                    print(f'  warning: blob missing for {full_path} — file skipped',
                          file=sys.stderr)
                    continue
                plaintext = self.crypto.decrypt(read_key, ciphertext)
                os.makedirs(os.path.dirname(file_path), exist_ok=True)
                with open(file_path, 'wb') as f:
                    f.write(plaintext)
            elif entry.tree_id:
                self.checkout(directory, str(entry.tree_id), read_key, full_path, missing=missing)

    # --- internal helpers ---

    def encrypt_or_reuse_blob(self, content: bytes, old_entry: dict,
                               read_key: bytes) -> tuple:
        """Encrypt content or reuse existing blob when content_hash matches.

        Returns (blob_id: str, is_large: bool, content_hash: str).
        Used by build() and by Vault__Sync.write_file().
        """
        content_hash = self.crypto.content_hash(content)
        if old_entry and old_entry.get('content_hash', '') == content_hash and old_entry.get('blob_id'):
            return old_entry['blob_id'], old_entry.get('large', False), content_hash
        encrypted = self.crypto.encrypt(read_key, content)
        blob_id   = self.obj_store.store(encrypted)
        return blob_id, len(encrypted) > LARGE_BLOB_THRESHOLD, content_hash

    def _populate_dir_contents(self, paths, extra_dirs=()) -> tuple:
        """Build dir_contents dict and all_dirs set from flat relative paths.
        `extra_dirs` are folders that must exist even with no files of their
        own (a scoped clone's spine folders, which hold only opaque entries)."""
        dir_contents = {}
        all_dirs     = set()
        for d in extra_dirs:
            parts = [p for p in str(d).split('/') if p]
            for i in range(1, len(parts) + 1):
                all_dirs.add('/'.join(parts[:i]))
        for rel_path in sorted(paths):
            parts = rel_path.split('/')
            if len(parts) == 1:
                dir_contents.setdefault('', []).append((parts[0], rel_path))
            else:
                dir_path = '/'.join(parts[:-1])
                filename = parts[-1]
                dir_contents.setdefault(dir_path, []).append((filename, rel_path))
                for i in range(1, len(parts)):
                    all_dirs.add('/'.join(parts[:i]))
        for d in all_dirs:
            dir_contents.setdefault(d, [])
        dir_contents.setdefault('', [])
        return dir_contents, all_dirs

    def _build_tree_from_dir_contents(self, dir_contents: dict, all_dirs: set,
                                      make_entry: callable, read_key: bytes,
                                      opaque: dict = None) -> str:
        """Shared tree-assembly core used by build() and build_from_flat().

        make_entry(filename, rel_path) -> Schema__Object_Tree_Entry | None
        opaque: {dir_path: [entries]} appended verbatim to that folder — the
        siblings a scoped clone never fetched, carried by id. Entries are
        sorted by their (deterministically encrypted) name so the same folder
        contents always yield the same tree id, however they were assembled.
        Returns root tree object ID.
        """
        tree_ids    = {}
        sorted_dirs = sorted(dir_contents.keys(), key=lambda p: (-p.count('/') if p else 1, p))
        opaque      = opaque or {}

        for dir_path in sorted_dirs:
            entries = []

            for filename, rel_path in sorted(dir_contents[dir_path], key=lambda x: x[0]):
                entry = make_entry(filename, rel_path)
                if entry is not None:
                    entries.append(entry)

            carried = list(opaque.get(dir_path, []))

            for child_dir in sorted(all_dirs):
                if dir_path == '':
                    if '/' not in child_dir:
                        folder_name = child_dir
                    else:
                        continue
                elif child_dir.startswith(dir_path + '/'):
                    remainder = child_dir[len(dir_path) + 1:]
                    if '/' not in remainder:
                        folder_name = remainder
                    else:
                        continue
                else:
                    continue

                if child_dir in tree_ids:
                    entries.append(Schema__Object_Tree_Entry(
                        tree_id  = tree_ids[child_dir],
                        name_enc = self.crypto.encrypt_metadata_deterministic(read_key, folder_name),
                    ))

            if carried:
                # Re-establish the plain builder's order — files by name, then
                # folders by name — so a tree assembled from held files plus
                # carried siblings gets the SAME id the whole-vault builder
                # gives it (the ids are content addresses; order matters). A
                # carried entry whose name collides with a built one is dropped:
                # the built one is this clone's content.
                built_names = {str(e.name_enc) for e in entries}
                extra       = [e for e in carried if str(e.name_enc) not in built_names]
                named       = [(self._decrypt_name(e, read_key), e) for e in entries + extra]
                files       = sorted((n, e) for n, e in named if e.blob_id)
                folders     = sorted((n, e) for n, e in named if e.tree_id)
                entries     = [e for _, e in files] + [e for _, e in folders]

            tree_obj = Schema__Object_Tree(schema='tree_v1', entries=entries)
            tree_id  = self._store_tree(tree_obj, read_key)
            tree_ids[dir_path] = tree_id

        return tree_ids.get('', '')

    def _store_tree(self, tree: Schema__Object_Tree, read_key: bytes) -> str:
        """Encrypt and store a tree object using deterministic IV for CAS deduplication."""
        tree_json      = json.dumps(tree.json()).encode()
        encrypted_tree = self.crypto.encrypt_deterministic(read_key, tree_json)
        return self.obj_store.store(encrypted_tree)

    def _load_tree(self, tree_id: str, read_key: bytes) -> Schema__Object_Tree:
        ciphertext = self.obj_store.load(tree_id)
        tree_data  = self.crypto.decrypt(read_key, ciphertext)
        return Schema__Object_Tree.from_json(json.loads(tree_data))

    def _decrypt_name(self, entry, read_key):
        if entry.name_enc:
            return self.crypto.decrypt_metadata(read_key, str(entry.name_enc))
        return ''

    def _decrypt_size(self, entry, read_key):
        if entry.size_enc:
            return int(self.crypto.decrypt_metadata(read_key, str(entry.size_enc)))
        return 0

    def _decrypt_content_hash(self, entry, read_key):
        if entry.content_hash_enc:
            return self.crypto.decrypt_metadata(read_key, str(entry.content_hash_enc))
        return ''

    def _decrypt_content_type(self, entry, read_key):
        if entry.content_type_enc:
            return self.crypto.decrypt_metadata(read_key, str(entry.content_type_enc))
        return 'application/octet-stream'
