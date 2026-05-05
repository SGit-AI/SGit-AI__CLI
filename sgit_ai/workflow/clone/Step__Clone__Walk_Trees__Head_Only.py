"""Step 6 (branch variant) — BFS-walk trees rooted at HEAD only (not all historical roots)."""
import time

from sgit_ai.safe_types.Safe_Str__Step_Name               import Safe_Str__Step_Name
from sgit_ai.schemas.workflow.clone.Schema__Clone__State  import Schema__Clone__State
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

        # Only walk the HEAD tree (first entry added by walk-commits = the tip commit's tree,
        # because BFS starts from named_commit_id which is HEAD)
        head_trees = root_tree_ids[:1] if root_tree_ids else []

        if head_trees:
            _t0           = time.monotonic()
            visited_trees = set()
            tree_queue    = list(head_trees)
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
                    workspace.progress('scan', 'Walking HEAD trees', str(len(visited_trees)))
                    tree = workspace.vc.load_tree(tid, read_key)
                    for entry in tree.entries:
                        sub_tid = str(entry.tree_id) if entry.tree_id else None
                        if sub_tid and sub_tid not in visited_trees:
                            next_trees.append(sub_tid)
                tree_queue = next_trees

            n_trees    = len(visited_trees)
            t_trees_ms = int((time.monotonic() - _t0) * 1000)
            workspace.progress('scan_done', 'Walking HEAD trees', f'{n_trees} trees')

        data               = input.json()
        data['n_trees']    = n_trees
        data['t_trees_ms'] = t_trees_ms
        return Schema__Clone__State.from_json(data)
