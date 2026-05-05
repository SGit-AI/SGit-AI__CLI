"""Step 5 — Perform three-way merge (or fast-forward) between clone and named branch."""
import json
import os
import time

from sgit_ai.safe_types.Safe_Str__Step_Name              import Safe_Str__Step_Name
from sgit_ai.safe_types.Safe_Str__Commit_Id              import Safe_Str__Commit_Id
from sgit_ai.safe_types.Safe_UInt__File_Count            import Safe_UInt__File_Count
from sgit_ai.schemas.workflow.pull.Schema__Pull__State   import Schema__Pull__State
from sgit_ai.workflow.Step                               import Step


class Step__Pull__Merge(Step):
    name          = Safe_Str__Step_Name('merge')
    input_schema  = Schema__Pull__State
    output_schema = Schema__Pull__State

    def execute(self, input: Schema__Pull__State, workspace) -> Schema__Pull__State:
        directory       = str(input.directory)
        sg_dir          = str(input.sg_dir)
        read_key        = bytes.fromhex(str(input.read_key_hex))
        clone_ref_id    = str(input.clone_ref_id)
        clone_commit_id = str(input.clone_commit_id) if input.clone_commit_id else ''
        named_commit_id = str(input.named_commit_id) if input.named_commit_id else ''

        workspace.ensure_managers(sg_dir)

        merge_status    = ''
        n_conflicts     = 0
        merge_commit_id = ''

        if not named_commit_id:
            merge_status = 'up_to_date'
            workspace.progress('step', 'Up to date — no remote commits')
        elif clone_commit_id == named_commit_id:
            merge_status = 'up_to_date'
            workspace.progress('step', 'Already up to date')
        else:
            lca_id = workspace.fetcher.find_lca(
                workspace.obj_store, read_key, clone_commit_id, named_commit_id
            ) if clone_commit_id else None

            if lca_id == named_commit_id:
                merge_status = 'up_to_date'
                workspace.progress('step', 'Already up to date (LCA check)')
            elif lca_id == clone_commit_id:
                merge_status    = 'fast_forward'
                merge_commit_id = named_commit_id
                workspace.progress('step', 'Fast-forward merge')
                named_commit     = workspace.vc.load_commit(named_commit_id, read_key)
                theirs_map       = workspace.sub_tree.flatten(str(named_commit.tree_id), read_key)
                ours_map         = {}
                if clone_commit_id:
                    ours_commit  = workspace.vc.load_commit(clone_commit_id, read_key)
                    ours_map     = workspace.sub_tree.flatten(str(ours_commit.tree_id), read_key)
                workspace.sync_client._checkout_flat_map(directory, theirs_map, workspace.obj_store, read_key)
                workspace.sync_client._remove_deleted_flat(directory, ours_map, theirs_map)
                workspace.ref_manager.write_ref(clone_ref_id, named_commit_id, read_key)
            else:
                workspace.progress('step', 'Three-way merge')
                base_map = {}
                if lca_id:
                    lca_commit = workspace.vc.load_commit(lca_id, read_key)
                    base_map   = workspace.sub_tree.flatten(str(lca_commit.tree_id), read_key)
                ours_map = {}
                if clone_commit_id:
                    ours_commit = workspace.vc.load_commit(clone_commit_id, read_key)
                    ours_map    = workspace.sub_tree.flatten(str(ours_commit.tree_id), read_key)
                named_commit = workspace.vc.load_commit(named_commit_id, read_key)
                theirs_map   = workspace.sub_tree.flatten(str(named_commit.tree_id), read_key)

                merge_result = workspace.merge_helper.three_way_merge(base_map, ours_map, theirs_map)
                merged_map   = merge_result['merged_map']
                conflicts    = merge_result['conflicts']

                workspace.sync_client._checkout_flat_map(directory, merged_map, workspace.obj_store, read_key)
                workspace.sync_client._remove_deleted_flat(directory, ours_map, merged_map)

                if conflicts:
                    merge_status = 'conflict'
                    n_conflicts  = len(conflicts)
                    workspace.merge_helper.write_conflict_files(
                        directory, conflicts, theirs_map, workspace.obj_store, read_key
                    )
                    merge_state = dict(clone_commit_id=clone_commit_id,
                                       named_commit_id=named_commit_id,
                                       lca_id=lca_id, conflicts=conflicts)
                    merge_state_path = os.path.join(workspace.storage.local_dir(directory), 'merge_state.json')
                    with open(merge_state_path, 'w') as f:
                        json.dump(merge_state, f, indent=2)
                else:
                    merge_status   = 'merge'
                    merged_tree_id = workspace.sub_tree.build_from_flat(merged_map, read_key)
                    parent_ids     = [p for p in [clone_commit_id, named_commit_id] if p]
                    merge_commit_id = workspace.vc.create_commit(
                        read_key   = read_key,
                        tree_id    = merged_tree_id,
                        parent_ids = parent_ids,
                        message    = 'Merge remote changes',
                        branch_id  = str(input.clone_branch_id),
                    )
                    workspace.ref_manager.write_ref(clone_ref_id, merge_commit_id, read_key)

        out = Schema__Pull__State(
            vault_key             = input.vault_key,
            directory             = input.directory,
            sg_dir                = input.sg_dir,
            vault_id              = input.vault_id,
            branch_index_file_id  = input.branch_index_file_id,
            read_key_hex          = input.read_key_hex,
            clone_branch_id       = input.clone_branch_id,
            clone_ref_id          = input.clone_ref_id,
            named_ref_id          = input.named_ref_id,
            clone_commit_id       = input.clone_commit_id,
            named_commit_id       = input.named_commit_id,
            remote_reachable      = input.remote_reachable,
            n_objects_fetched     = input.n_objects_fetched,
            merge_status          = merge_status,
            n_conflicts           = Safe_UInt__File_Count(n_conflicts),
            merge_commit_id       = Safe_Str__Commit_Id(merge_commit_id) if merge_commit_id else None,
        )
        return out
