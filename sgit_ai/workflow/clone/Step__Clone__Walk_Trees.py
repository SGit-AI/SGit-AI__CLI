"""Step 6 — BFS-walk all tree objects reachable from root_tree_ids."""
import time

from sgit_ai.safe_types.Safe_Str__Step_Name               import Safe_Str__Step_Name
from sgit_ai.schemas.workflow.clone.Schema__Clone__State  import Schema__Clone__State
from sgit_ai.workflow.Step                                import Step


class Step__Clone__Walk_Trees(Step):
    name          = Safe_Str__Step_Name('walk-trees')
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

        if root_tree_ids:
            _t0           = time.monotonic()
            visited_trees = set()
            tree_queue    = list(root_tree_ids)
            while tree_queue:
                to_dl = [f'bare/data/{tid}' for tid in tree_queue
                         if tid not in visited_trees]
                if to_dl:
                    for fid, blob in workspace.sync_client.api.batch_read(vault_id, to_dl).items():
                        if blob:
                            workspace.save_file(sg_dir, fid, blob)
                next_trees = []
                for tid in tree_queue:
                    if tid in visited_trees:
                        continue
                    visited_trees.add(tid)
                    workspace.progress('scan', 'Walking trees', str(len(visited_trees)))
                    tree = workspace.vc.load_tree(tid, read_key)
                    for entry in tree.entries:
                        sub_tid = str(entry.tree_id) if entry.tree_id else None
                        if sub_tid and sub_tid not in visited_trees:
                            next_trees.append(sub_tid)
                tree_queue = next_trees

            n_trees    = len(visited_trees)
            t_trees_ms = int((time.monotonic() - _t0) * 1000)
            workspace.progress('scan_done', 'Walking trees', f'{n_trees} trees')

        data               = input.json()
        data['n_trees']    = n_trees
        data['t_trees_ms'] = t_trees_ms
        return Schema__Clone__State.from_json(data)
