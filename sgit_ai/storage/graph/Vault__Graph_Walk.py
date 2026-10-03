from osbot_utils.type_safe.Type_Safe import Type_Safe


class Vault__Graph_Walk(Type_Safe):
    """BFS tree-graph walk; callers inject on_batch_missing to download before each level."""

    def walk_trees(self, root_ids, load_tree_fn, on_batch_missing=None) -> set:
        """BFS from root_ids; returns set of all tree IDs successfully visited.

        Every tree id is enqueued — and therefore handed to on_batch_missing —
        at most once. A vault's history shares most of its sub-trees between
        commits (an unchanged folder keeps its tree id), so without this the
        next level's queue held one copy of a shared sub-tree PER parent that
        referenced it: a 170-commit vault asked the server for ~10,000 trees
        to visit ~2,200 unique ones, each level a long serial download the
        progress line could not show (it looked hung). `seen` tracks what has
        been queued, `visited` what has actually loaded (an absent or refused
        tree is in `seen`, never retried, and not in `visited`).
        """
        visited = set()
        seen    = set()
        queue   = []
        for tid in root_ids:
            if tid and tid not in seen:
                seen.add(tid)
                queue.append(tid)

        while queue:
            if on_batch_missing:
                on_batch_missing(list(queue))

            next_q = []
            for tid in queue:
                try:
                    tree = load_tree_fn(tid)
                    visited.add(tid)                   # only a tree that actually loaded
                    for entry in tree.entries:
                        sub = str(entry.tree_id) if entry.tree_id else None
                        if sub and sub not in seen:
                            seen.add(sub)
                            next_q.append(sub)
                except Exception:
                    pass

            queue = next_q

        return visited
