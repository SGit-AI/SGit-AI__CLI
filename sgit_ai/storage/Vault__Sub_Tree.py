import json
import re
import mimetypes
import os
from   osbot_utils.type_safe.Type_Safe                import Type_Safe
from   sgit_ai.crypto.Vault__Crypto               import Vault__Crypto
from   sgit_ai.storage.Vault__Path_Guard            import Vault__Path_Guard

LARGE_BLOB_THRESHOLD = 4 * 1024 * 1024  # 4 MB — safe margin under Lambda base64 limit
OBJECT_ID_RE         = re.compile(r'obj-cas-imm-(?:[0-9a-f]{12}|[0-9a-f]{32})')
FLAT_CACHE           = {}               # tree id -> flat map, this process; a tree id is a content address
FLAT_CACHE_MAX       = 4
FLAT_CACHE_ON_DISK   = 2                # .sg_vault/local/flat-cache/<tree id>.json: the newest heads
FLAT_CACHE_VERSION   = 2                # the file's format; 0.24.1 (dev only) wrote none: discarded
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
              old_flat_entries: dict = None, opaque: dict = None, old_tree_ids: dict = None) -> str:
        """Build sub-tree objects bottom-up from working directory files.

        `opaque` — {dir_path: [Schema__Object_Tree_Entry, …]} entries carried
        into those folders verbatim (a scoped clone's out-of-scope siblings,
        known only by id). None/empty for a full clone: identical behaviour.

        `old_tree_ids` — {dir path: tree id} of the previous head (flatten_dirs).
        A file whose scanned size and content hash are what the head recorded
        keeps its committed entry without being read again, and a folder whose
        files and sub-folders are all unchanged keeps its tree id without being
        rebuilt: the cost of a commit follows the change, not the vault (a
        one-file commit on the 38,474-folder newsroom vault rebuilt and re-encrypted
        every tree, four minutes whatever the change — report of 26 Oct).

        Returns root tree object ID (obj-cas-imm-{hash}).
        """
        if old_flat_entries is None:
            old_flat_entries = {}
        dir_contents, all_dirs = (self._populate_dir_contents(file_map.keys(), extra_dirs=opaque.keys()) if opaque
                                  else self._populate_dir_contents(file_map.keys()))

        guard    = Vault__Path_Guard()
        base_abs = os.path.abspath(directory)

        def unchanged(rel_path):                                    # the scan's verdict equals the head's record
            old     = old_flat_entries.get(rel_path)
            scanned = file_map.get(rel_path)                        # {size, content_hash} from the scan (callers
            return bool(old and isinstance(scanned, dict) and old.get('blob_id')   # may pass any truthy value)
                        and scanned.get('content_hash') and scanned.get('content_hash') == old.get('content_hash')
                        and scanned.get('size') == old.get('size'))

        def make_entry(filename, rel_path):
            if rel_path not in file_map:
                return None
            if unchanged(rel_path):
                return self._entry_from_flat(filename, old_flat_entries[rel_path], read_key)
            local_file = os.path.join(directory, rel_path)
            if guard.has_link_component(base_abs, os.path.abspath(local_file)):    # never read through a link:
                old = old_flat_entries.get(rel_path)                               # a tracked path keeps its committed entry
                return self._entry_from_flat(filename, old, read_key) if old and old.get('blob_id') else None
            content = guard.read_regular(local_file, rel_path)      # O_NOFOLLOW: no link swapped in (L4); raises
            if content is None:                                     # when it cannot be opened (B2)
                old = old_flat_entries.get(rel_path)                # swapped for a link/FIFO since the scan: keep
                return self._entry_from_flat(filename, old, read_key) if old and old.get('blob_id') else None
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

        return self._build_tree_from_dir_contents(dir_contents, all_dirs, make_entry, read_key, opaque,
                                                  old_tree_ids=old_tree_ids, old_flat_entries=old_flat_entries,
                                                  file_unchanged=unchanged)

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

    def build_from_flat(self, flat_map: dict, read_key: bytes, opaque: dict = None,
                        old_flat_entries: dict = None, old_tree_ids: dict = None) -> str:
        """Build sub-tree objects from a flat {path: dict} map.

        Used after merge — blobs already exist in the object store,
        we just need to construct the tree structure with encrypted metadata.
        `opaque` as in build().

        `old_flat_entries` / `old_tree_ids`: a previous head's flatten() and
        flatten_dirs(). A folder whose entries are all exactly the old ones keeps its
        old tree id, as build() does for a commit: a merge, a `sgit write` of one file
        or a replayed commit builds and encrypts the folders on the changed paths, not
        every folder (design__00 F3/B7). The ids are the ones a full build gives.

        Returns root tree object ID.
        """
        dir_contents, all_dirs = (self._populate_dir_contents(flat_map.keys(), extra_dirs=opaque.keys()) if opaque
                                  else self._populate_dir_contents(flat_map.keys()))

        def make_entry(filename, rel_path):
            entry_data = flat_map.get(rel_path)
            if not entry_data:
                return None
            content_type = self._content_type_of(filename, entry_data)
            return Schema__Object_Tree_Entry(
                blob_id          = entry_data['blob_id'],
                name_enc         = self.crypto.encrypt_metadata_deterministic(read_key, filename),
                size_enc         = self.crypto.encrypt_metadata_deterministic(read_key, str(entry_data.get('size', 0))),
                content_hash_enc = self.crypto.encrypt_metadata_deterministic(read_key, entry_data.get('content_hash', '')),
                content_type_enc = self.crypto.encrypt_metadata_deterministic(read_key, content_type),
                large            = entry_data.get('large', False),
            )

        file_unchanged = None
        if old_tree_ids and old_flat_entries is not None:
            def file_unchanged(rel_path):                           # the entry make_entry would write is the old one
                new, old = flat_map.get(rel_path), old_flat_entries.get(rel_path)
                if not new or not old or not new.get('blob_id'):
                    return False
                filename = rel_path.rsplit('/', 1)[-1]
                return (new.get('blob_id')            == old.get('blob_id')
                        and str(new.get('size', 0))   == str(old.get('size', 0))
                        and new.get('content_hash', '') == old.get('content_hash', '')
                        and self._content_type_of(filename, new) == self._content_type_of(filename, old)
                        and bool(new.get('large', False)) == bool(old.get('large', False)))

        return self._build_tree_from_dir_contents(dir_contents, all_dirs, make_entry, read_key, opaque,
                                                  old_tree_ids=old_tree_ids if file_unchanged else None,
                                                  old_flat_entries=old_flat_entries, file_unchanged=file_unchanged)

    def _content_type_of(self, filename: str, entry: dict) -> str:
        return entry.get('content_type', '') or mimetypes.guess_type(filename)[0] or 'application/octet-stream'

    def apply_changes(self, tree_id: str, changes: dict, read_key: bytes) -> str:
        """The tree id of `tree_id` with `changes` applied: {path: flat entry} adds or
        replaces a file, {path: None} deletes it. Unchanged folders keep their ids, so
        the cost follows the change (design__07 replays, design__01 picks); the result
        is exactly what build_from_flat gives for the whole new map."""
        old_flat = self.flatten(tree_id, read_key) if tree_id else {}
        old_dirs = self.flatten_dirs(tree_id, read_key) if tree_id else {}
        new_flat = dict(old_flat)
        for path, entry in changes.items():
            if entry is None:
                new_flat.pop(path, None)
            else:
                new_flat[path] = entry
        return self.build_from_flat(new_flat, read_key, old_flat_entries=old_flat, old_tree_ids=old_dirs)

    def flatten(self, tree_id: str, read_key: bytes, prefix: str = '') -> dict:
        """Walk sub-trees recursively, return flat {path: dict} map.

        Returns {path: {'blob_id': str, 'size': int, 'content_hash': str, 'content_type': str}}

        The result is a pure function of the tree id (a content address under the
        read key), so it is kept: once per process in FLAT_CACHE, and on disk under
        .sg_vault/local/flat-cache/<tree id>.json, so a status, a commit, a push and
        a pull on the same head rebuild nothing. Trees are read as the JSON they are
        (`_load_tree_entries`), not through the schema's Type_Safe construction,
        which cost ~3 ms per tree: on the newsroom's 38,474-folder vault that was two
        minutes per flatten, and a status flattened twice (report of 26 Oct).
        """
        if prefix == '':
            return self._flat_full(tree_id, read_key)[0]
        return self._flatten_walk(tree_id, read_key, prefix)

    def flatten_dirs(self, tree_id: str, read_key: bytes) -> dict:
        """{dir path: tree id} for every folder under tree_id ('' is the root): the
        companion of flatten(), kept in the same caches. build() uses it to keep an
        unchanged folder's tree id instead of rebuilding it."""
        return self._flat_full(tree_id, read_key)[1]

    def _flat_full(self, tree_id: str, read_key: bytes) -> tuple:
        cached = self._flat_cached(tree_id, read_key)
        if cached is not None:
            return cached
        dirs = {}
        base = self._flat_any_cached(read_key)
        if base is not None:                                                  # another head's map is here: walk only
            result = self._flatten_incremental(tree_id, read_key, base, dirs)   # where the folder ids differ (a pull's
        else:                                                                 # new head shares nearly every folder)
            result = self._flatten_walk(tree_id, read_key, '', dirs=dirs)
        self._flat_remember(tree_id, result, dirs)
        return {path: dict(entry) for path, entry in result.items()}, dict(dirs)

    def _flat_any_cached(self, read_key: bytes):
        """(tree id, flat, dirs) of any head this process or this vault has cached, newest
        first on disk, or None. Any base is exact: an unrelated one just prunes nothing."""
        for tid, hit in reversed(list(FLAT_CACHE.items())):
            return tid, hit[0], hit[1]
        try:
            cache_dir = self._flat_cache_dir()
            names = sorted((os.path.getmtime(os.path.join(cache_dir, n)), n) for n in os.listdir(cache_dir) if n.endswith('.json'))
        except OSError:
            return None
        for _, name in reversed(names):
            tid = name[:-len('.json')]
            hit = self._flat_cached(tid, read_key)
            if hit is not None:
                return tid, hit[0], hit[1]
        return None

    def _flatten_incremental(self, tree_id: str, read_key: bytes, base: tuple, dirs: dict) -> dict:
        """flatten(tree_id) built from a cached base map: a folder whose tree id is the
        base's at the same path is copied from the base (ids are content addresses, and a
        folder's flattening depends only on its id and its path); every other folder is
        read. The result is exactly the full walk's; the cost follows the difference."""
        base_id, base_flat, base_dirs = base
        files_under = {}                                                  # base folder -> its file paths
        for path in base_flat:
            files_under.setdefault(path.rpartition('/')[0], []).append(path)
        dirs_under  = {}                                                  # base folder -> its folder paths (self incl.)
        for path in base_dirs:
            parent = path
            while True:
                dirs_under.setdefault(parent, []).append(path)
                if not parent:
                    break
                parent = parent.rpartition('/')[0]
        result = {}
        stack  = [(tree_id, base_id, '')]
        while stack:
            nid, oid, prefix = stack.pop()
            if nid == oid and base_dirs.get(prefix) == oid:                # the same folder at the same path:
                for sub in dirs_under.get(prefix, []):                     # copy its whole subtree from the base
                    dirs[sub] = base_dirs[sub]
                    for path in files_under.get(sub, []):
                        result[path] = base_flat[path]
                continue
            dirs[prefix] = nid
            old_by_name = {}
            if oid and oid != nid and self.obj_store.exists(oid):         # the base may be another vault's, or
                try:                                                      # another key's (a rekey): an old side
                    old_by_name = self._entries_by_name(oid, read_key)    # that does not decrypt is no old side
                except Exception:
                    old_by_name = {}
            for entry in self._load_tree_entries(nid, read_key):
                name_enc = entry.get('name_enc')
                name     = self.crypto.decrypt_metadata(read_key, str(name_enc)) if name_enc else ''
                if not name:
                    continue
                full_path = f'{prefix}/{name}' if prefix else name
                if entry.get('blob_id'):
                    result[full_path] = self._entry_dict(entry, read_key)
                elif entry.get('tree_id'):
                    old = old_by_name.get(name)
                    stack.append((str(entry['tree_id']), str(old['tree_id']) if old and old.get('tree_id') else None, full_path))
        return result

    def _flatten_walk(self, tree_id: str, read_key: bytes, prefix: str, dirs: dict = None) -> dict:
        result = {}
        stack  = [(tree_id, prefix)]
        while stack:
            tid, pre = stack.pop()
            if dirs is not None:
                dirs[pre] = tid
            for entry in self._load_tree_entries(tid, read_key):
                name_enc = entry.get('name_enc')
                name     = self.crypto.decrypt_metadata(read_key, str(name_enc)) if name_enc else ''
                if not name:
                    continue
                full_path = f'{pre}/{name}' if pre else name
                if entry.get('blob_id'):
                    size_enc = entry.get('size_enc'); hash_enc = entry.get('content_hash_enc'); type_enc = entry.get('content_type_enc')
                    result[full_path] = dict(
                        blob_id      = str(entry['blob_id']),
                        size         = int(self.crypto.decrypt_metadata(read_key, str(size_enc))) if size_enc else 0,
                        content_hash = self.crypto.decrypt_metadata(read_key, str(hash_enc)) if hash_enc else '',
                        content_type = self.crypto.decrypt_metadata(read_key, str(type_enc)) if type_enc else '',
                        large        = bool(entry.get('large', False)),
                    )
                elif entry.get('tree_id'):
                    stack.append((str(entry['tree_id']), full_path))
        return result

    def diff_trees(self, new_tree_id: str, old_tree_id: str, read_key: bytes) -> dict:
        """What changed between two trees, by walking only where they differ: a folder
        whose tree id is the same on both sides is never opened (ids are content
        addresses). Returns {'added': {path: entry}, 'deleted': {path: entry},
        'modified': {path: (new entry, old entry)}, 'new_dirs': n} with the entries
        as flatten() gives them. Either side may be None (nothing there). Cost follows
        the change, not the vault: `sgit history log` used to flatten every commit in
        full, eight minutes on a 38,474-folder vault (report of 26 Oct)."""
        added, deleted, modified = {}, {}, {}
        new_dirs = 0
        stack    = [(new_tree_id or None, old_tree_id or None, '')]
        while stack:
            nid, oid, prefix = stack.pop()
            if nid == oid:
                continue
            if nid and not oid and prefix:
                new_dirs += 1
            new_by_name = self._entries_by_name(nid, read_key)              # by decrypted name: a writer that
            old_by_name = self._entries_by_name(oid, read_key)              # encrypts names with a random IV
            for name, e in new_by_name.items():                             # (QA review of 26 Oct, finding 4)
                o = old_by_name.get(name)
                def at():
                    return f'{prefix}/{name}' if prefix else name
                if e.get('blob_id'):
                    if o is None or not o.get('blob_id'):
                        added[at()] = self._entry_dict(e, read_key)
                        if o is not None and o.get('tree_id'):              # a folder became a file
                            stack.append((None, str(o['tree_id']), at()))
                    elif str(o['blob_id']) != str(e['blob_id']):
                        modified[at()] = (self._entry_dict(e, read_key), self._entry_dict(o, read_key))
                elif e.get('tree_id'):
                    if o is None or not o.get('tree_id'):
                        stack.append((str(e['tree_id']), None, at()))
                        if o is not None and o.get('blob_id'):              # a file became a folder
                            deleted[at()] = self._entry_dict(o, read_key)
                    elif str(o['tree_id']) != str(e['tree_id']):
                        stack.append((str(e['tree_id']), str(o['tree_id']), at()))
            for name, o in old_by_name.items():
                if name in new_by_name:
                    continue
                path = f'{prefix}/{name}' if prefix else name
                if o.get('blob_id'):
                    deleted[path] = self._entry_dict(o, read_key)
                elif o.get('tree_id'):
                    stack.append((None, str(o['tree_id']), path))
        return dict(added=added, deleted=deleted, modified=modified, new_dirs=new_dirs)

    def _entries_by_name(self, tree_id, read_key: bytes) -> dict:
        """{decrypted name: entry} of a tree (empty for None); a nameless entry is skipped."""
        out = {}
        for e in (self._load_tree_entries(tree_id, read_key) if tree_id else []):
            name_enc = e.get('name_enc')
            if not name_enc:
                continue
            name = self.crypto.decrypt_metadata(read_key, str(name_enc))
            if name:
                out[name] = e
        return out

    def _entry_dict(self, entry: dict, read_key: bytes) -> dict:
        size_enc = entry.get('size_enc'); hash_enc = entry.get('content_hash_enc'); type_enc = entry.get('content_type_enc')
        return dict(blob_id      = str(entry.get('blob_id') or ''),
                    size         = int(self.crypto.decrypt_metadata(read_key, str(size_enc))) if size_enc else 0,
                    content_hash = self.crypto.decrypt_metadata(read_key, str(hash_enc)) if hash_enc else '',
                    content_type = self.crypto.decrypt_metadata(read_key, str(type_enc)) if type_enc else '',
                    large        = bool(entry.get('large', False)))

    def _load_tree_entries(self, tree_id: str, read_key: bytes) -> list:
        """A tree's entries as the plain dicts stored in its JSON. Every blob_id and
        tree_id is checked against the object-id form, as Schema__Object_Tree_Entry
        would check it, before a caller can use it as a path."""
        data    = json.loads(self.crypto.decrypt(read_key, self.obj_store.load(tree_id)))
        entries = data.get('entries') if isinstance(data, dict) else None
        if not isinstance(entries, list):
            raise ValueError(f'tree {tree_id}: no entries list')
        for entry in entries:
            if not isinstance(entry, dict):
                raise ValueError(f'tree {tree_id}: an entry is not an object')
            for field in ('blob_id', 'tree_id'):
                value = entry.get(field)
                if value and not OBJECT_ID_RE.fullmatch(str(value)):
                    raise ValueError(f'tree {tree_id}: {field} {str(value)[:40]!r} is not an object id')
        return entries

    # --- the flatten caches: one per process, one per tree id on disk --------------
    def _flat_cache_dir(self) -> str:
        return os.path.join(str(self.obj_store.vault_path), 'local', 'flat-cache')

    def _flat_cached(self, tree_id: str, read_key: bytes):
        """(flat, dirs) copies from the process cache or the on-disk one, else None. A
        file of another format version, a malformed one, or one whose ids are not
        object ids is a miss (never a crash, never a path): the cache is rebuilt from
        the trees and overwritten (QA review of 26 Oct, finding 5)."""
        hit  = FLAT_CACHE.get(tree_id)
        path = os.path.join(self._flat_cache_dir(), tree_id + '.json')
        if hit is not None and not os.path.isfile(path):
            self._flat_remember(tree_id, hit[0], hit[1])                  # known to this process, not yet to this
        if hit is None:                                                   # vault on disk (a clone made here)
            try:
                with open(path) as f:
                    saved = json.load(f)
                hit = self._flat_cache_check(tree_id, saved)
                if hit is not None and not self._flat_cache_matches_root(tree_id, read_key, hit[0], hit[1]):
                    hit = None
                if hit is not None:
                    self._flat_remember(tree_id, hit[0], hit[1], write=False)
            except Exception:
                hit = None
        if hit is None:
            return None
        flat, dirs = hit
        return {path: dict(entry) for path, entry in flat.items()}, dict(dirs)

    def _flat_cache_matches_root(self, tree_id: str, read_key: bytes, flat: dict, dirs: dict) -> bool:
        """One tree read: every file the root tree names is in `flat` with that blob id
        and every folder is in `dirs` with that tree id, and nothing at the root is
        extra. An emptied or truncated cache file is a miss; a cache edited below the
        root is not caught (its folder is the key's folder: TM-R41)."""
        try:
            files, folders = {}, {}
            for e in self._load_tree_entries(tree_id, read_key):
                name = self.crypto.decrypt_metadata(read_key, str(e['name_enc'])) if e.get('name_enc') else ''
                if not name:
                    continue
                if e.get('blob_id'):
                    files[name] = str(e['blob_id'])
                elif e.get('tree_id'):
                    folders[name] = str(e['tree_id'])
            root_files   = {p: v.get('blob_id') for p, v in flat.items() if '/' not in p}
            root_folders = {p: v for p, v in dirs.items() if p and '/' not in p}
            return root_files == files and root_folders == folders
        except Exception:
            return False

    def _flat_cache_check(self, tree_id: str, saved) -> tuple:
        """The (flat, dirs) of a saved cache file, or None unless every part has the
        form flatten() produces and every id is an object id."""
        if not isinstance(saved, dict) or saved.get('version') != FLAT_CACHE_VERSION or saved.get('tree_id') != tree_id:
            return None
        flat, dirs = saved.get('flat'), saved.get('dirs')
        if not isinstance(flat, dict) or not isinstance(dirs, dict) or dirs.get('') != tree_id:
            return None
        for path, entry in flat.items():
            if (not isinstance(path, str) or not isinstance(entry, dict)
                    or not OBJECT_ID_RE.fullmatch(str(entry.get('blob_id') or ''))
                    or not isinstance(entry.get('size'), int) or isinstance(entry.get('size'), bool)
                    or not isinstance(entry.get('content_hash'), str) or not isinstance(entry.get('content_type'), str)
                    or not isinstance(entry.get('large'), bool)):
                return None
        for path, tid in dirs.items():
            if not isinstance(path, str) or not OBJECT_ID_RE.fullmatch(str(tid)):
                return None
        return flat, dirs

    def _flat_remember(self, tree_id: str, flat: dict, dirs: dict, write: bool = True) -> None:
        FLAT_CACHE[tree_id] = (flat, dirs)
        while len(FLAT_CACHE) > FLAT_CACHE_MAX:
            FLAT_CACHE.pop(next(iter(FLAT_CACHE)))
        if not write:
            return
        try:
            cache_dir = self._flat_cache_dir()
            os.makedirs(cache_dir, mode=0o700, exist_ok=True)
            tmp = os.path.join(cache_dir, tree_id + '.tmp')
            fd  = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, 'w') as f:
                f.write(json.dumps(dict(version=FLAT_CACHE_VERSION, tree_id=tree_id, flat=flat, dirs=dirs), separators=(',', ':')))
            os.replace(tmp, os.path.join(cache_dir, tree_id + '.json'))
            names = os.listdir(cache_dir)
            kept  = sorted((os.path.getmtime(os.path.join(cache_dir, n)), n) for n in names if n.endswith('.json'))
            for _, name in kept[:-FLAT_CACHE_ON_DISK]:                        # the newest few heads only
                os.remove(os.path.join(cache_dir, name))
            for name in names:                                                # a .tmp a crash left behind
                if name.endswith('.tmp') and os.path.join(cache_dir, name) != tmp:
                    os.remove(os.path.join(cache_dir, name))
        except OSError:
            pass                                                              # a cache: never a failure

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
        encrypted = self.crypto.encrypt(read_key, content, deflate=True)    # a blob: deflated on a 'blob-deflate' vault
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
                                      opaque: dict = None, old_tree_ids: dict = None,
                                      old_flat_entries: dict = None, file_unchanged: callable = None) -> str:
        """Shared tree-assembly core used by build() and build_from_flat().

        make_entry(filename, rel_path) -> Schema__Object_Tree_Entry | None
        opaque: {dir_path: [entries]} appended verbatim to that folder — the
        siblings a scoped clone never fetched, carried by id. Entries are
        sorted by their (deterministically encrypted) name so the same folder
        contents always yield the same tree id, however they were assembled.
        old_tree_ids / old_flat_entries / file_unchanged: the previous head's
        {dir: tree id}, its flat entries and a predicate on a file path; a folder
        with the same file names (all unchanged) and the same sub-folders (all
        reused), nothing carried, and its old tree still in the store, keeps its
        old tree id — nothing is built, encrypted or stored for it.
        Returns root tree object ID.
        """
        tree_ids    = {}
        sorted_dirs = sorted(dir_contents.keys(), key=lambda p: (-p.count('/') if p else 1, p))
        opaque      = opaque or {}
        children    = {}                                   # parent -> [(folder name, child dir)], built once:
        for child_dir in all_dirs:                         # the old scan of every folder for each folder was
            parent, _, folder_name = child_dir.rpartition('/')   # quadratic (38k folders: a 4-minute commit)
            children.setdefault(parent, []).append((folder_name, child_dir))

        old_tree_ids = old_tree_ids or {}
        old_files    = {}                                  # old dir -> {file names}, from the old flat entries
        old_folders  = {}                                  # old dir -> {folder names}, from the old tree ids
        reused_dirs  = set()
        if old_tree_ids and file_unchanged is not None:
            for path in (old_flat_entries or {}):
                parent, _, name = path.rpartition('/')
                old_files.setdefault(parent, set()).add(name)
            for path in old_tree_ids:
                if path:
                    parent, _, name = path.rpartition('/')
                    old_folders.setdefault(parent, set()).add(name)

        for dir_path in sorted_dirs:
            old_id = old_tree_ids.get(dir_path)
            if old_id and not opaque.get(dir_path):
                here_files   = dir_contents[dir_path]
                here_folders = [(n, d) for n, d in children.get(dir_path, []) if d in tree_ids]
                if ({n for n, _ in here_files} == old_files.get(dir_path, set())
                        and {n for n, _ in here_folders} == old_folders.get(dir_path, set())
                        and all(d in reused_dirs for _, d in here_folders)
                        and all(file_unchanged(rel_path) for _, rel_path in here_files)
                        and self.obj_store.exists(old_id)):
                    tree_ids[dir_path] = old_id
                    reused_dirs.add(dir_path)
                    continue
            entries = []

            for filename, rel_path in sorted(dir_contents[dir_path], key=lambda x: x[0]):
                entry = make_entry(filename, rel_path)
                if entry is not None:
                    entries.append(entry)

            carried = list(opaque.get(dir_path, []))

            for folder_name, child_dir in sorted(children.get(dir_path, [])):   # the same order as before:
                if child_dir in tree_ids:                                        # by full path within one parent
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
