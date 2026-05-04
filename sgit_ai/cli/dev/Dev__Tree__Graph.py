"""Tool 2: sgit dev tree-graph <vault-key>

Visualises the tree DAG without modifying the working copy.  A sparse clone
is made to a temporary directory so we can walk the local object store; the
temp dir is removed before returning.
"""
import json
import shutil
import tempfile
from collections import defaultdict

from osbot_utils.type_safe.Type_Safe                    import Type_Safe
from sgit_ai.cli.dev.Schema__Tree__Graph                import (Schema__Tree__Graph,
                                                                Schema__Tree__Graph__Commit,
                                                                Schema__Tree__Graph__DepthLevel)
from sgit_ai.crypto.Vault__Crypto                       import Vault__Crypto
from sgit_ai.storage.Vault__Commit                      import Vault__Commit
from sgit_ai.storage.Vault__Object_Store                import Vault__Object_Store
from sgit_ai.core.Vault__Sync                           import Vault__Sync


class Dev__Tree__Graph(Type_Safe):
    """Builds a tree-DAG visualisation from vault metadata."""

    crypto : Vault__Crypto
    api    : object = None
    sync   : Vault__Sync

    def setup(self):
        if self.api is None:
            from sgit_ai.network.api.Vault__API import Vault__API
            self.api = Vault__API()
        self.sync = Vault__Sync(crypto=self.crypto, api=self.api)
        return self

    # ------------------------------------------------------------------
    # Core analysis
    # ------------------------------------------------------------------

    def analyse(self, vault_key: str) -> Schema__Tree__Graph:
        """Sparse-clone into a temp dir, walk all objects, return Schema__Tree__Graph."""
        tmp_dir = tempfile.mkdtemp()
        try:
            result = self.sync.clone(vault_key, tmp_dir, sparse=True)
            return self._build_graph(tmp_dir, result)
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def _build_graph(self, directory: str, clone_result: dict) -> Schema__Tree__Graph:
        vault_id  = clone_result.get('vault_id', '')
        sg_dir    = _sg_vault_dir(directory)   # .sg_vault (not .sg_vault/bare)

        obj_store = Vault__Object_Store(vault_path=sg_dir, crypto=self.crypto)
        from sgit_ai.crypto.PKI__Crypto         import PKI__Crypto
        from sgit_ai.storage.Vault__Ref_Manager  import Vault__Ref_Manager
        pki         = PKI__Crypto()
        ref_manager = Vault__Ref_Manager(vault_path=sg_dir, crypto=self.crypto)
        vc          = Vault__Commit(crypto=self.crypto, pki=pki,
                                    object_store=obj_store, ref_manager=ref_manager)

        head_commit_id = clone_result.get('commit_id', '')
        stored_key     = clone_result.get('vault_key', '')
        read_key       = self._derive_read_key(stored_key)

        # Walk commit chain (BFS) to collect all commit IDs in order
        commit_ids = _bfs_commits(vc, head_commit_id, read_key)

        # For each commit, collect all reachable tree IDs (BFS from root tree)
        all_seen_trees : set   = set()
        commit_stats   : list  = []
        depth_counter  : dict  = defaultdict(lambda: defaultdict(set))  # depth → set of tree_ids

        for cid in commit_ids:
            commit_obj   = vc.load_commit(cid, read_key)
            root_tree_id = str(commit_obj.tree_id) if commit_obj.tree_id else ''
            if not root_tree_id:
                commit_stats.append(Schema__Tree__Graph__Commit(
                    commit_id=cid, root_tree_id='', total_trees=0, unique_new=0, dedup_ratio='1.0x'))
                continue

            commit_trees = _bfs_trees_with_depth(vc, root_tree_id, read_key, depth_counter)
            new_trees    = commit_trees - all_seen_trees
            all_seen_trees.update(commit_trees)

            total  = len(commit_trees)
            unique = len(new_trees)
            ratio  = f'{total / max(unique, 1):.1f}x'

            commit_stats.append(Schema__Tree__Graph__Commit(
                commit_id    = cid,
                root_tree_id = root_tree_id,
                total_trees  = total,
                unique_new   = unique,
                dedup_ratio  = ratio,
            ))

        # HEAD-only clone counterfactual
        head_trees = 0
        if commit_ids:
            head_cid     = commit_ids[0]
            head_obj     = vc.load_commit(head_cid, read_key)
            head_root    = str(head_obj.tree_id) if head_obj.tree_id else ''
            head_trees   = len(_bfs_trees_with_depth(vc, head_root, read_key, {})) if head_root else 0

        depth_histogram = []
        for depth in sorted(depth_counter.keys()):
            trees_at_depth = depth_counter[depth]
            total_at_depth = sum(len(v) for v in trees_at_depth.values())
            unique_at_depth = len(set().union(*trees_at_depth.values())) if trees_at_depth else 0
            depth_histogram.append(Schema__Tree__Graph__DepthLevel(
                depth      = depth,
                tree_count = total_at_depth,
                unique     = unique_at_depth,
            ))

        total_tree_refs = sum(c.total_trees for c in commit_stats)

        return Schema__Tree__Graph(
            vault_id        = vault_id,
            n_commits       = len(commit_ids),
            total_trees     = total_tree_refs,
            unique_trees    = len(all_seen_trees),
            head_only_trees = head_trees,
            commits         = commit_stats,
            depth_histogram = depth_histogram,
        )

    def _derive_read_key(self, stored_key: str) -> bytes:
        keys = self.sync._derive_keys_from_stored_key(stored_key)
        return keys['read_key_bytes']

    # ------------------------------------------------------------------
    # CLI entry point
    # ------------------------------------------------------------------

    def cmd_tree_graph(self, args):
        vault_key = args.vault_key
        json_out  = getattr(args, 'json',   False)
        out_file  = getattr(args, 'output', None)
        dot_out   = getattr(args, 'dot',    None)

        self.setup()
        output = self.analyse(vault_key)

        if json_out:
            data = output.json()
            text = json.dumps(data, indent=2)
            if out_file:
                with open(out_file, 'w') as f:
                    f.write(text)
                print(f'Tree graph written to {out_file}')
            else:
                print(text)
        else:
            self._print_text(output)

        if dot_out:
            self._write_dot(output, dot_out)
            print(f'Graphviz DOT written to {dot_out}')

    def _print_text(self, output: Schema__Tree__Graph):
        print(f'Tree DAG: {output.vault_id}')
        print(f'  Commits:        {output.n_commits}')
        print(f'  Total tree refs:{output.total_trees}')
        print(f'  Unique trees:   {output.unique_trees}')
        print(f'  HEAD-only trees:{output.head_only_trees}')
        dedup = output.total_trees / max(output.unique_trees, 1)
        print(f'  Global dedup:   {dedup:.1f}x')
        print()
        print(f'  Depth histogram:')
        for d in output.depth_histogram:
            print(f'    depth {d.depth}: {d.tree_count} refs, {d.unique} unique')
        print()
        print(f'  Per-commit summary (newest first):')
        for c in output.commits[:10]:
            print(f'    {c.commit_id[:12]}  trees={c.total_trees}  new={c.unique_new}  dedup={c.dedup_ratio}')

    def _write_dot(self, output: Schema__Tree__Graph, path: str):
        lines = ['digraph tree_dag {']
        lines.append('  rankdir=LR;')
        for c in output.commits:
            cid = c.commit_id[:8]
            tid = c.root_tree_id[:8] if c.root_tree_id else 'none'
            lines.append(f'  "{cid}" -> "{tid}";')
        lines.append('}')
        with open(path, 'w') as f:
            f.write('\n'.join(lines))


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _sg_vault_dir(directory: str) -> str:
    import os
    return os.path.join(directory, '.sg_vault')


def _bfs_commits(vc: Vault__Commit, head_id: str, read_key: bytes) -> list:
    """Return all commit IDs in BFS order (head first)."""
    if not head_id:
        return []
    visited = set()
    queue   = [head_id]
    result  = []
    while queue:
        nxt = []
        for cid in queue:
            if cid in visited:
                continue
            visited.add(cid)
            result.append(cid)
            try:
                commit = vc.load_commit(cid, read_key)
                for pid in (commit.parents or []):
                    pid_str = str(pid)
                    if pid_str and pid_str not in visited:
                        nxt.append(pid_str)
            except Exception:
                pass
        queue = nxt
    return result


def _bfs_trees_with_depth(vc: Vault__Commit, root_id: str, read_key: bytes,
                           depth_counter: dict) -> set:
    """BFS walk all tree IDs from root; update depth_counter in-place."""
    if not root_id:
        return set()
    visited = set()
    queue   = [(root_id, 0)]
    while queue:
        nxt = []
        for tid, depth in queue:
            if tid in visited:
                continue
            visited.add(tid)
            if isinstance(depth_counter, dict):
                if depth not in depth_counter:
                    depth_counter[depth] = defaultdict(set)
                depth_counter[depth][tid].add(tid)
            try:
                tree = vc.load_tree(tid, read_key)
                for entry in tree.entries:
                    sub = str(entry.tree_id) if entry.tree_id else None
                    if sub and sub not in visited:
                        nxt.append((sub, depth + 1))
            except Exception:
                pass
        queue = nxt
    return visited
