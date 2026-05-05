"""Step 6 (branch variant) — BFS-walk trees rooted at HEAD only (not all historical roots)."""
import time

from sgit_ai.safe_types.Safe_Str__Step_Name               import Safe_Str__Step_Name
from sgit_ai.schemas.workflow.clone.Schema__Clone__State  import Schema__Clone__State
from sgit_ai.storage.graph.Vault__Graph_Walk              import Vault__Graph_Walk
from sgit_ai.workflow.Step                                import Step


class Step__Clone__Walk_Trees__Head_Only(Step):
    name          = Safe_Str__Step_Name('walk-trees-head-only')
    input_schema  = Schema__Clone__State
    output_schema = Schema__Clone__State

    def execute(self, input: Schema__Clone__State, workspace) -> Schema__Clone__State:
        vault_id      = str(input.vault_id)
        sg_dir        = str(input.sg_dir)
        read_key      = bytes.fromhex(str(input.read_key_hex))
        root_tree_ids = [str(t) for t in input.root_tree_ids]

        workspace.ensure_managers(sg_dir)

        n_trees    = 0
        t_trees_ms = 0

        # Only walk the HEAD tree (first entry = tip commit's tree, BFS starts from HEAD)
        head_trees = root_tree_ids[:1] if root_tree_ids else []

        if head_trees:
            _t0        = time.monotonic()
            graph_walk = Vault__Graph_Walk()

            def on_batch_missing(ids):
                to_dl = [f'bare/data/{tid}' for tid in ids]
                for fid, blob in workspace.sync_client.api.batch_read(vault_id, to_dl).items():
                    if blob:
                        workspace.save_file(sg_dir, fid, blob)

            def load_tree(tid):
                tree = workspace.vc.load_tree(tid, read_key)
                workspace.progress('scan', 'Walking HEAD trees', str(tid))
                return tree

            visited_trees = graph_walk.walk_trees(head_trees, load_tree, on_batch_missing)
            n_trees    = len(visited_trees)
            t_trees_ms = int((time.monotonic() - _t0) * 1000)
            workspace.progress('scan_done', 'Walking HEAD trees', f'{n_trees} trees')

        data               = input.json()
        data['n_trees']    = n_trees
        data['t_trees_ms'] = t_trees_ms
        return Schema__Clone__State.from_json(data)
