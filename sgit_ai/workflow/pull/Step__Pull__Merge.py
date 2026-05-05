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

        clone_branch_name = str(input.clone_branch_name) if input.clone_branch_name else 'local'
        named_branch_name = str(input.named_branch_name) if input.named_branch_name else 'remote'

        workspace.ensure_managers(sg_dir)

        merge_status    = ''
        n_conflicts     = 0
        merge_commit_id = ''
        added_files     = []
        modified_files  = []
        deleted_files   = []
        conflict_paths  = []

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
                named_commit = workspace.vc.load_commit(named_commit_id, read_key)
                theirs_map   = workspace.sub_tree.flatten(str(named_commit.tree_id), read_key)
                ours_map     = {}
                if clone_commit_id:
                    ours_commit = workspace.vc.load_commit(clone_commit_id, read_key)
                    ours_map    = workspace.sub_tree.flatten(str(ours_commit.tree_id), read_key)
                workspace.sync_client._checkout_flat_map(directory, theirs_map, workspace.obj_store, read_key)
                workspace.sync_client._remove_deleted_flat(directory, ours_map, theirs_map)
                workspace.ref_manager.write_ref(clone_ref_id, named_commit_id, read_key)
                added_files    = [p for p in theirs_map if p not in ours_map]
                modified_files = [p for p in theirs_map
                                  if p in ours_map and
                                  theirs_map[p].get('blob_id') != ours_map[p].get('blob_id')]
                deleted_files  = [p for p in ours_map if p not in theirs_map]
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
                    merge_status   = 'conflict'
                    n_conflicts    = len(conflicts)
                    conflict_paths = list(conflicts)
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

                    signing_key = None
                    clone_public_key_id = str(input.clone_public_key_id) if input.clone_public_key_id else ''
                    key_manager = getattr(workspace, 'key_manager', None)
                    if key_manager:
                        try:
                            signing_key = key_manager.load_private_key_locally(
                                clone_public_key_id, workspace.storage.local_dir(directory))
                        except Exception:
                            pass

                    merge_msg        = f'Merge {named_branch_name} into {clone_branch_name}'
                    create_kw        = dict(read_key   = read_key,
                                            tree_id    = merged_tree_id,
                                            parent_ids = parent_ids,
                                            message    = merge_msg,
                                            branch_id  = str(input.clone_branch_id))
                    if signing_key is not None:
                        create_kw['signing_key'] = signing_key
                    merge_commit_id = workspace.vc.create_commit(**create_kw)
                    workspace.ref_manager.write_ref(clone_ref_id, merge_commit_id, read_key)
                    added_files    = merge_result.get('added', [])
                    modified_files = merge_result.get('modified', [])
                    deleted_files  = merge_result.get('deleted', [])

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
            clone_public_key_id   = input.clone_public_key_id,
            clone_branch_name     = input.clone_branch_name,
            named_branch_name     = input.named_branch_name,
            named_commit_id       = input.named_commit_id,
            remote_reachable      = input.remote_reachable,
            n_objects_fetched     = input.n_objects_fetched,
            merge_status          = merge_status,
            n_conflicts           = Safe_UInt__File_Count(n_conflicts),
            merge_commit_id       = Safe_Str__Commit_Id(merge_commit_id) if merge_commit_id else None,
            added_files           = added_files   or None,
            modified_files        = modified_files or None,
            deleted_files         = deleted_files  or None,
            conflict_paths        = conflict_paths or None,
        )
        return out
