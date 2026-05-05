from osbot_utils.type_safe.Type_Safe import Type_Safe


class Vault__Graph_Walk(Type_Safe):
    """BFS tree-graph walk extracted from the three walk-trees call sites.

    Keeps network I/O out of this class — callers inject an optional
    ``on_batch_missing`` callback that is invoked once per BFS level with
    the list of unvisited tree IDs so callers can download them before the
    walk tries to load them.
    """

    def walk_trees(self, root_ids, load_tree_fn, on_batch_missing=None) -> set:
        """BFS-walk tree objects reachable from *root_ids*.

        Args:
            root_ids:          Iterable of tree object IDs to start from.
            load_tree_fn:      Callable(tree_id: str) -> tree with .entries.
                               May raise; failed loads are silently skipped.
            on_batch_missing:  Optional callable(ids: list[str]).  Called
                               before each BFS level with IDs not yet visited,
                               giving the caller a chance to download them.

        Returns:
            set of all tree IDs successfully visited.
        """
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
