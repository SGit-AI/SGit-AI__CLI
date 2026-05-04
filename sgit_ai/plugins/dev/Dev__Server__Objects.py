"""Tool 3: sgit dev server-objects <vault-key>

Inventories remote objects by type using the list_files API endpoint.
Performs a sparse clone to count HEAD-reachable vs history-only objects,
then removes the temp directory.
"""
import json
import shutil
import tempfile
from collections import Counter, defaultdict

from osbot_utils.type_safe.Type_Safe                   import Type_Safe
from sgit_ai.plugins.dev.Dev__Tree__Graph                  import _sg_vault_dir, _bfs_commits, _bfs_trees_with_depth
from sgit_ai.plugins.dev.Schema__Server__Objects           import (Schema__Server__Objects,
                                                               Schema__Server__Objects__TypeCount)
from sgit_ai.crypto.Vault__Crypto                      import Vault__Crypto
from sgit_ai.storage.Vault__Commit                     import Vault__Commit
from sgit_ai.storage.Vault__Object_Store               import Vault__Object_Store
from sgit_ai.storage.Vault__Ref_Manager                import Vault__Ref_Manager
from sgit_ai.crypto.PKI__Crypto                        import PKI__Crypto
from sgit_ai.core.Vault__Sync                          import Vault__Sync


_TYPE_MAP = {
    'bare/data/obj-cas-imm-' : 'data',
    'bare/refs/'             : 'ref',
    'bare/keys/'             : 'key',
    'bare/indexes/'          : 'index',
    'bare/branches/'         : 'branch',
    'bare/pending/'          : 'pending',
}

TOP_N_HOT = 5


class Dev__Server__Objects(Type_Safe):
    """Inventories remote objects without modifying the local working copy."""

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

    def analyse(self, vault_key: str) -> Schema__Server__Objects:
        keys     = self.sync._derive_keys_from_stored_key(vault_key)
        vault_id = keys['vault_id']
        read_key = keys['read_key_bytes']

        all_files = self.api.list_files(vault_id)
        type_counter = Counter()
        for fid in all_files:
            type_counter[_classify(fid)] += 1

        by_type = [
            Schema__Server__Objects__TypeCount(obj_type=t, count=c)
            for t, c in sorted(type_counter.items())
        ]

        # Sparse clone into temp dir for reachability analysis
        head_ids, hist_ids, hot_trees = self._reachability(vault_key, vault_id, read_key)

        return Schema__Server__Objects(
            vault_id       = vault_id,
            total_objects  = len(all_files),
            by_type        = by_type,
            head_reachable = len(head_ids),
            history_only   = len(hist_ids - head_ids),
            hot_tree_ids   = list(hot_trees),
        )

    def _reachability(self, vault_key: str, vault_id: str, read_key: bytes):
        """Sparse-clone, walk commit graph, return (head_ids, all_ids, hot_trees)."""
        tmp_dir = tempfile.mkdtemp()
        try:
            result = self.sync.clone(vault_key, tmp_dir, sparse=True)
            sg_dir = _sg_vault_dir(tmp_dir)

            obj_store   = Vault__Object_Store(vault_path=sg_dir, crypto=self.crypto)
            pki         = PKI__Crypto()
            ref_manager = Vault__Ref_Manager(vault_path=sg_dir, crypto=self.crypto)
            vc          = Vault__Commit(crypto=self.crypto, pki=pki,
                                        object_store=obj_store, ref_manager=ref_manager)

            head_commit = result.get('commit_id', '')
            all_commits = _bfs_commits(vc, head_commit, read_key)

            # HEAD-only object set (just the first commit's tree subtree)
            head_ids = set()
            if all_commits:
                head_obj  = vc.load_commit(all_commits[0], read_key)
                head_root = str(head_obj.tree_id) if head_obj.tree_id else ''
                head_ids  = _bfs_trees_with_depth(vc, head_root, read_key, {})
                head_ids.add(head_root)
                head_ids.add(all_commits[0])

            # All reachable from full history
            all_ids        = set(all_commits)
            tree_ref_count = Counter()
            for cid in all_commits:
                try:
                    commit_obj = vc.load_commit(cid, read_key)
                    root       = str(commit_obj.tree_id) if commit_obj.tree_id else ''
                    if root:
                        all_ids.add(root)
                        tree_ref_count[root] += 1
                        sub_trees = _bfs_trees_with_depth(vc, root, read_key, {})
                        all_ids.update(sub_trees)
                        for tid in sub_trees:
                            tree_ref_count[tid] += 1
                except Exception:
                    pass

            hot_trees = [tid for tid, _ in tree_ref_count.most_common(TOP_N_HOT) if _ > 1]
            return head_ids, all_ids, hot_trees

        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    # ------------------------------------------------------------------
    # CLI entry point
    # ------------------------------------------------------------------

    def cmd_server_objects(self, args):
        vault_key = args.vault_key
        json_out  = getattr(args, 'json',   False)
        out_file  = getattr(args, 'output', None)

        self.setup()
        output = self.analyse(vault_key)

        if json_out:
            data = output.json()
            text = json.dumps(data, indent=2)
            if out_file:
                with open(out_file, 'w') as f:
                    f.write(text)
                print(f'Object inventory written to {out_file}')
            else:
                print(text)
        else:
            self._print_text(output)

    def _print_text(self, output: Schema__Server__Objects):
        print(f'Server objects: {output.vault_id}')
        print(f'  Total:          {output.total_objects}')
        print(f'  HEAD-reachable: {output.head_reachable}')
        print(f'  History-only:   {output.history_only}')
        print()
        print('  By type:')
        for t in output.by_type:
            print(f'    {t.obj_type:<12}  {t.count}')
        if output.hot_tree_ids:
            print()
            print('  Hot tree IDs (referenced from multiple commits):')
            for tid in output.hot_tree_ids:
                print(f'    {tid}')


def _classify(file_id: str) -> str:
    for prefix, label in _TYPE_MAP.items():
        if file_id.startswith(prefix):
            return label
    return 'other'
