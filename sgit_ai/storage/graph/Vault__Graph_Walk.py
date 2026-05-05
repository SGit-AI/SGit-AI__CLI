from osbot_utils.type_safe.Type_Safe import Type_Safe


class Vault__Graph_Walk(Type_Safe):
    """BFS tree-graph walk; callers inject on_batch_missing to download before each level."""

    def walk_trees(self, root_ids, load_tree_fn, on_batch_missing=None) -> set:
        """BFS from root_ids; returns set of all tree IDs successfully visited."""
        visited = set()
        queue   = [t for t in root_ids if t]

        while queue:
            unvisited = [t for t in queue if t not in visited]
            if on_batch_missing and unvisited:
                on_batch_missing(unvisited)

            next_q = []
            for tid in queue:
                if tid in visited:
                    continue
                visited.add(tid)
                try:
                    tree = load_tree_fn(tid)
                    for entry in tree.entries:
                        sub = str(entry.tree_id) if entry.tree_id else None
                        if sub and sub not in visited:
                            next_q.append(sub)
                except Exception:
                    pass

            queue = next_q

        return visited
