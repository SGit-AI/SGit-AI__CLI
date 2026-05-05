"""Step 5 (range variant) — BFS-walk commits from range_to back to range_from (exclusive)."""
import time

from sgit_ai.safe_types.Safe_Str__Step_Name               import Safe_Str__Step_Name
from sgit_ai.schemas.workflow.clone.Schema__Clone__State  import Schema__Clone__State
from sgit_ai.workflow.Step                                import Step


class Step__Clone__Walk_Commits__Range(Step):
    """Walk commits from named_commit_id (= range_to) until range_from is reached.

    If range_from is empty, walks only the single tip commit (HEAD-only range).
    range_from is treated as a stop-before sentinel — its commit object is NOT downloaded.
    """
    name          = Safe_Str__Step_Name('walk-commits-range')
    input_schema  = Schema__Clone__State
    output_schema = Schema__Clone__State

    def execute(self, input: Schema__Clone__State, workspace) -> Schema__Clone__State:
        vault_id        = str(input.vault_id)
        sg_dir          = str(input.sg_dir)
        read_key        = bytes.fromhex(str(input.read_key_hex))
        named_commit_id = str(input.named_commit_id) if input.named_commit_id else ''
        range_from      = str(input.range_from) if input.range_from else ''

        workspace.ensure_managers(sg_dir)

        root_tree_ids = []
        n_commits     = 0
        t_commits_ms  = 0

        if named_commit_id:
            _t0             = time.monotonic()
            visited_commits = set()
            stop_at         = {range_from} if range_from else set()
            commit_queue    = [named_commit_id]

            while commit_queue:
                to_dl = [f'bare/data/{cid}' for cid in commit_queue
                         if cid not in visited_commits and cid not in stop_at]
                if to_dl:
                    for fid, blob in workspace.sync_client.api.batch_read(vault_id, to_dl).items():
                        if blob:
                            workspace.save_file(sg_dir, fid, blob)
                next_commits = []
                for cid in commit_queue:
                    if cid in visited_commits or cid in stop_at:
                        continue
                    visited_commits.add(cid)
                    workspace.progress('scan', 'Walking commits (range)', str(len(visited_commits)))
                    commit  = workspace.vc.load_commit(cid, read_key)
                    tree_id = str(commit.tree_id)
                    if tree_id:
                        root_tree_ids.append(tree_id)
                    for pid in (commit.parents or []):
                        pid_str = str(pid)
                        if pid_str and pid_str not in visited_commits and pid_str not in stop_at:
                            next_commits.append(pid_str)
                commit_queue = next_commits

            n_commits    = len(visited_commits)
            t_commits_ms = int((time.monotonic() - _t0) * 1000)
            workspace.progress('scan_done', 'Walking commits (range)', f'{n_commits} commits')

        data                  = input.json()
        data['n_commits']     = n_commits
        data['root_tree_ids'] = root_tree_ids
        data['t_commits_ms']  = t_commits_ms
        return Schema__Clone__State.from_json(data)
