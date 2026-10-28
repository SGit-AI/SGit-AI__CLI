"""Vault__Path_History — one path's entry at a tree, and whether it differs between two
trees, without flattening either (design__04 §5.4).

entry_at walks only the folders on the path (plain-JSON tree reads, memoised by tree
id: ids are content addresses, so the memo never goes stale). same_at stops at the
first equal folder id on the way down. At the file, equal blob ids, or equal
(content_hash, size), mean unchanged: a writer that re-encrypts unchanged content
(the web UI) no longer shows as `modified`."""
from   osbot_utils.type_safe.Type_Safe                 import Type_Safe
from   sgit_ai.storage.Vault__Sub_Tree                 import Vault__Sub_Tree

TREE_MEMO_MAX = 4096


class Vault__Path_History(Type_Safe):
    sub_tree  : Vault__Sub_Tree
    read_key  : bytes
    tree_memo : object = None                            # tree id -> {name: raw entry}

    def entries(self, tree_id: str) -> dict:
        if self.tree_memo is None:
            self.tree_memo = {}
        if tree_id not in self.tree_memo:
            if len(self.tree_memo) >= TREE_MEMO_MAX:
                self.tree_memo.pop(next(iter(self.tree_memo)))
            self.tree_memo[tree_id] = self.sub_tree._entries_by_name(tree_id, self.read_key)
        return self.tree_memo[tree_id]

    def raw_at(self, tree_id: str, path: str):
        """The raw tree entry at `path` (a file's or a folder's), or None."""
        node = {'tree_id': tree_id}
        for name in [p for p in str(path).split('/') if p]:
            if not node or not node.get('tree_id'):
                return None
            node = self.entries(str(node['tree_id'])).get(name)
        return node

    def entry_at(self, tree_id: str, path: str):
        """The file's flat entry (the flatten() shape) at `path` in `tree_id`, or None."""
        if not tree_id:
            return None
        raw = self.raw_at(tree_id, path)
        if not raw or not raw.get('blob_id'):
            return None
        return self.sub_tree._entry_dict(raw, self.read_key)

    def same_at(self, tree_a: str, tree_b: str, path: str) -> bool:
        if tree_a == tree_b:
            return True
        if not tree_a or not tree_b:
            return self.entry_at(tree_a, path) is None and self.entry_at(tree_b, path) is None
        node_a, node_b = {'tree_id': tree_a}, {'tree_id': tree_b}
        for name in [p for p in str(path).split('/') if p]:
            if node_a and node_b and node_a.get('tree_id') and node_a.get('tree_id') == node_b.get('tree_id'):
                return True                                                 # the same folder: the same file below
            node_a = self.entries(str(node_a['tree_id'])).get(name) if node_a and node_a.get('tree_id') else None
            node_b = self.entries(str(node_b['tree_id'])).get(name) if node_b and node_b.get('tree_id') else None
        file_a = node_a if node_a and node_a.get('blob_id') else None
        file_b = node_b if node_b and node_b.get('blob_id') else None
        if file_a is None or file_b is None:
            return file_a is None and file_b is None
        if str(file_a['blob_id']) == str(file_b['blob_id']):
            return True
        a = self.sub_tree._entry_dict(file_a, self.read_key)
        b = self.sub_tree._entry_dict(file_b, self.read_key)
        return bool(a['content_hash']) and (a['content_hash'], a['size']) == (b['content_hash'], b['size'])

    def changed_paths(self, tree_new: str, tree_old: str) -> dict:
        return self.sub_tree.diff_trees(tree_new, tree_old, self.read_key)
