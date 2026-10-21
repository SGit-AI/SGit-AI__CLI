"""Step 5 — BFS-walk the commit chain, collecting root tree IDs."""
import time

from sgit_ai.safe_types.Safe_Str__Step_Name               import Safe_Str__Step_Name
from sgit_ai.schemas.workflow.clone.Schema__Clone__State  import Schema__Clone__State
from sgit_ai.workflow.Step                                import Step


class Step__Clone__Walk_Commits(Step):

    def refuse_pack_vault_without_packs(self, input, workspace, sg_dir: str, read_key: bytes) -> None:
        """A pack vault's host has no loose objects: a workflow that did not take the packs
        (clone-branch, clone-headless, clone-range) would walk into 404s. Say so."""
        if input.pack_vault:
            return
        import os
        from sgit_ai.storage.Vault__Format import Vault__Format, FEATURE_PACKS
        index_id = str(input.index_id or input.branch_index_file_id or '')
        if not index_id:
            return
        try:
            index = workspace.branch_manager.load_branch_index(os.path.dirname(os.path.abspath(sg_dir)), index_id, read_key)
        except Exception:
            return
        if Vault__Format().has_feature(index, FEATURE_PACKS):
            raise RuntimeError('this is a pack vault (objects travel as packs): sgit clone-branch, clone-headless and '
                               'clone-range do not read packs yet. Use `sgit clone`.')

    name          = Safe_Str__Step_Name('walk-commits')
    input_schema  = Schema__Clone__State
    output_schema = Schema__Clone__State

    def execute(self, input: Schema__Clone__State, workspace) -> Schema__Clone__State:
        vault_id        = str(input.vault_id)
        sg_dir          = str(input.sg_dir)
        read_key        = bytes.fromhex(str(input.read_key_hex))
        named_commit_id = str(input.named_commit_id) if input.named_commit_id else ''

        workspace.ensure_managers(sg_dir)
        self.refuse_pack_vault_without_packs(input, workspace, sg_dir, read_key)

        root_tree_ids   = []
        n_commits       = 0
        t_commits_ms    = 0
        depth           = int(input.depth) if input.depth else 0          # 0 = all history
        boundaries      = []
        level           = 0

        if named_commit_id:
            _t0             = time.monotonic()
            visited_commits = set()
            commit_queue    = [named_commit_id]

            while commit_queue:
                level += 1
                to_dl = [f'bare/data/{cid}' for cid in commit_queue
                         if cid not in visited_commits and not workspace.obj_store.exists(cid)]
                if to_dl:
                    for fid, blob in workspace.sync_client.api.batch_read(vault_id, to_dl).items():
                        if blob:
                            workspace.save_file(sg_dir, fid, blob, read_key)
                next_commits = []
                for cid in commit_queue:
                    if cid in visited_commits:
                        continue
                    visited_commits.add(cid)
                    workspace.progress('scan', 'Walking commits', str(len(visited_commits)))
                    try:
                        commit = workspace.vc.load_commit(cid, read_key)
                    except Exception as error:
                        # Absent or refused by the SP-1 integrity check: skip this
                        # lineage instead of aborting the whole clone (fail-soft
                        # per object, never per run).
                        workspace.progress('warning', 'Commit unavailable — lineage skipped',
                                           f'{cid}: {error}')
                        continue
                    tree_id = str(commit.tree_id)
                    if tree_id:
                        root_tree_ids.append(tree_id)
                    parents = [str(p) for p in (commit.parents or []) if str(p)]
                    if depth and level >= depth and parents:
                        boundaries.append(cid)                    # shallow: history stops here
                        continue
                    for pid_str in parents:
                        if pid_str not in visited_commits:
                            next_commits.append(pid_str)
                commit_queue = next_commits

            n_commits    = len(visited_commits)
            t_commits_ms = int((time.monotonic() - _t0) * 1000)
            workspace.progress('scan_done', 'Walking commits', f'{n_commits} commits')

        data                 = input.json()
        data['n_commits']    = n_commits
        data['root_tree_ids'] = root_tree_ids
        data['shallow_boundaries'] = boundaries
        data['t_commits_ms'] = t_commits_ms
        return Schema__Clone__State.from_json(data)
