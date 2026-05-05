"""Tests for Vault__Graph_Walk — BFS tree-graph walk."""
from sgit_ai.storage.graph.Vault__Graph_Walk import Vault__Graph_Walk


# ---------------------------------------------------------------------------
# Minimal tree stub
# ---------------------------------------------------------------------------

class _Entry:
    def __init__(self, tree_id=None, blob_id=None):
        self.tree_id = tree_id
        self.blob_id = blob_id

class _Tree:
    def __init__(self, *child_ids):
        self.entries = [_Entry(tree_id=c) for c in child_ids]

def _forest(mapping: dict):
    """Build a load_tree_fn from {tree_id: [child_ids]} mapping."""
    def load_tree(tid):
        if tid not in mapping:
            raise KeyError(f'unknown tree: {tid}')
        return _Tree(*mapping[tid])
    return load_tree


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class Test_Vault__Graph_Walk:

    def setup_method(self):
        self.gw = Vault__Graph_Walk()

    # --- instantiation ---

    def test_instantiation(self):
        assert isinstance(self.gw, Vault__Graph_Walk)

    # --- empty input ---

    def test_empty_root_ids(self):
        visited = self.gw.walk_trees([], lambda tid: _Tree())
        assert visited == set()

    def test_none_filtered_from_roots(self):
        visited = self.gw.walk_trees([None, '', None], _forest({}))
        assert visited == set()

    # --- single tree ---

    def test_single_leaf_tree(self):
        load = _forest({'t1': []})
        visited = self.gw.walk_trees(['t1'], load)
        assert visited == {'t1'}

    # --- linear chain ---

    def test_linear_chain(self):
        load = _forest({'t1': ['t2'], 't2': ['t3'], 't3': []})
        visited = self.gw.walk_trees(['t1'], load)
        assert visited == {'t1', 't2', 't3'}

    # --- diamond (shared subtree) ---

    def test_diamond_no_double_visit(self):
        # t1 -> t2, t3;  t2 -> t4;  t3 -> t4
        load    = _forest({'t1': ['t2', 't3'], 't2': ['t4'], 't3': ['t4'], 't4': []})
        visited = self.gw.walk_trees(['t1'], load)
        assert visited == {'t1', 't2', 't3', 't4'}

    # --- multiple roots ---

    def test_multiple_roots(self):
        load    = _forest({'a': ['c'], 'b': ['c'], 'c': []})
        visited = self.gw.walk_trees(['a', 'b'], load)
        assert visited == {'a', 'b', 'c'}

    # --- failed load silently skipped ---

    def test_failed_load_skipped(self):
        def bad_load(tid):
            if tid == 'broken':
                raise RuntimeError('download failed')
            return _Tree()
        visited = self.gw.walk_trees(['good', 'broken'], bad_load)
        assert 'good' in visited
        assert 'broken' in visited   # added to visited before load attempt? No — visited AFTER load
        # Actually: broken is added to visited set before load_tree is called, so it IS in visited
        # regardless of load failure. This prevents infinite retry loops.

    # --- on_batch_missing callback ---

    def test_on_batch_missing_called_with_unvisited_ids(self):
        calls = []
        load  = _forest({'r': ['c1', 'c2'], 'c1': [], 'c2': []})

        def capture(ids):
            calls.append(list(ids))

        self.gw.walk_trees(['r'], load, capture)
        # First call: ['r'], second call: ['c1', 'c2'] (or subset)
        assert len(calls) >= 1
        assert 'r' in calls[0]

    def test_on_batch_missing_not_called_when_empty(self):
        calls = []
        self.gw.walk_trees([], lambda t: _Tree(), lambda ids: calls.append(ids))
        assert calls == []

    # --- on_batch_missing can inject data ---

    def test_callback_can_mutate_store(self):
        store = {}
        load  = _forest({'root': ['child'], 'child': []})

        def download(ids):
            for tid in ids:
                store[tid] = True

        self.gw.walk_trees(['root'], load, download)
        assert 'root' in store
        assert 'child' in store

    # --- head-only subset (caller slices root_ids[:1]) ---

    def test_head_only_walk(self):
        # Full history has two roots; head-only gives only first
        load = _forest({'t_head': ['t_sub'], 't_sub': [], 't_old': ['t_other'], 't_other': []})
        root_ids  = ['t_head', 't_old']
        head_only = root_ids[:1]
        visited   = self.gw.walk_trees(head_only, load)
        assert visited == {'t_head', 't_sub'}
        assert 't_old' not in visited
