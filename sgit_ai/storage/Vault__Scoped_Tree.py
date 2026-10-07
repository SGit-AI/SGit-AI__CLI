"""Vault__Scoped_Tree — read, fetch and rebuild only the folders a clone holds.

Three operations over a Merkle tree and a Vault__Scope:

  flatten(tree_id)   → (flat, opaque): the held folders' files as the usual
                       {path: entry-dict} map, plus, per folder on the spine,
                       the raw entries of the siblings that are NOT held
                       (known by id only). flat + opaque is enough to rebuild
                       the whole root tree with Vault__Sub_Tree.build(…, opaque=).
  walk_fetch(root)   → the same descent, but fetching each level's missing
                       tree objects first (one batch per level) and only
                       descending into held and spine folders. Returns the
                       held folders' blob ids (small / large) and the trees
                       visited — exactly what a scoped clone must download.
  held_paths(flat)   → convenience filter.

For a whole-vault scope flatten() degenerates to Vault__Sub_Tree.flatten with
an empty opaque map; the clone/commit/pull code paths for full clones do not
call this class at all.
"""
from osbot_utils.type_safe.Type_Safe          import Type_Safe
from sgit_ai.crypto.Vault__Crypto             import Vault__Crypto
from sgit_ai.storage.Vault__Object_Store      import Vault__Object_Store
from sgit_ai.storage.Vault__Sub_Tree          import Vault__Sub_Tree
from sgit_ai.storage.Vault__Scope             import Vault__Scope


class Vault__Scoped_Tree(Type_Safe):
    crypto    : Vault__Crypto
    obj_store : Vault__Object_Store
    sub_tree  : Vault__Sub_Tree = None

    def setup(self):
        if self.sub_tree is None:
            self.sub_tree = Vault__Sub_Tree(crypto=self.crypto, obj_store=self.obj_store)
        return self

    # ------------------------------------------------------------------ read
    def flatten(self, tree_id: str, read_key: bytes, scope: Vault__Scope) -> tuple:
        """(flat, opaque) — see module docstring. Raises FileNotFoundError when a
        tree the scope needs is not local (a held or spine folder's tree)."""
        self.setup()
        if scope.is_whole():
            return self.sub_tree.flatten(tree_id, read_key), {}
        flat   = {}
        opaque = {}
        self._descend(tree_id, '', read_key, scope, flat, opaque)
        return flat, opaque

    def _descend(self, tree_id: str, dir_path: str, read_key: bytes, scope: Vault__Scope,
                 flat: dict, opaque: dict) -> None:
        tree = self.sub_tree._load_tree(tree_id, read_key)
        for entry in tree.entries:
            name = self.sub_tree._decrypt_name(entry, read_key)
            if not name:
                continue
            path = f'{dir_path}/{name}' if dir_path else name
            if entry.blob_id:
                if scope.contains_path(path):
                    flat[path] = self._entry_dict(entry, read_key)
                else:
                    opaque.setdefault(dir_path, []).append(entry)
            elif entry.tree_id:
                if scope.contains_path(path):                           # held: everything under it
                    flat.update(self.sub_tree.flatten(str(entry.tree_id), read_key, path))
                elif scope.is_spine_dir(path):                          # on the way down: open it
                    self._descend(str(entry.tree_id), path, read_key, scope, flat, opaque)
                else:                                                   # a sibling: carry by id
                    opaque.setdefault(dir_path, []).append(entry)

    def _entry_dict(self, entry, read_key: bytes) -> dict:
        return dict(blob_id      = str(entry.blob_id),
                    size         = self.sub_tree._decrypt_size(entry, read_key),
                    content_hash = self.sub_tree._decrypt_content_hash(entry, read_key),
                    content_type = self.sub_tree._decrypt_content_type(entry, read_key),
                    large        = entry.large)

    # ----------------------------------------------------------------- fetch
    def walk_fetch(self, root_tree_ids: list, read_key: bytes, scope: Vault__Scope,
                   on_batch_missing=None, on_tree=None) -> dict:
        """Level-by-level descent that fetches before it reads. on_batch_missing
        receives the tree ids of a level that are not local (it downloads them).
        Returns {'trees': set, 'small_blobs': set, 'large_blobs': set}."""
        self.setup()
        visited     = set()
        small, large = set(), set()
        level       = [(str(t), '') for t in root_tree_ids if t]
        seen        = {t for t, _ in level}
        while level:
            missing = [t for t, _ in level if not self.obj_store.exists(t)]
            if missing and on_batch_missing:
                on_batch_missing(missing)
            next_level = []
            for tree_id, dir_path in level:
                if not self.obj_store.exists(tree_id):
                    continue                                            # absent on the host: skipped
                try:
                    tree = self.sub_tree._load_tree(tree_id, read_key)
                except Exception:
                    continue
                visited.add(tree_id)
                if on_tree:
                    on_tree(tree_id)
                for entry in tree.entries:
                    name = self.sub_tree._decrypt_name(entry, read_key)
                    if not name:
                        continue
                    path = f'{dir_path}/{name}' if dir_path else name
                    if entry.blob_id:
                        if scope.contains_path(path):
                            (large if entry.large else small).add(str(entry.blob_id))
                    elif entry.tree_id and scope.descends_into(path):
                        sub = str(entry.tree_id)
                        if sub not in seen:
                            seen.add(sub)
                            next_level.append((sub, path))
            level = next_level
        return dict(trees=visited, small_blobs=small, large_blobs=large)

    # ---------------------------------------------------------------- build
    def build(self, directory: str, file_map: dict, read_key: bytes,
              old_flat: dict, opaque: dict) -> str:
        self.setup()
        return self.sub_tree.build(directory, file_map, read_key, old_flat_entries=old_flat, opaque=opaque)

    def build_from_flat(self, flat_map: dict, read_key: bytes, opaque: dict) -> str:
        self.setup()
        return self.sub_tree.build_from_flat(flat_map, read_key, opaque=opaque)
