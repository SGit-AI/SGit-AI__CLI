"""Step 4 (read-only) — Check out the named-branch HEAD into the working copy.

This is the read-only replacement for Step__Pull__Merge. It performs a STRAIGHT
checkout of the new named HEAD's tree — NO three-way merge, NO commit creation,
and NO clone-branch ref write (read-only clones have no clone branch; guard rails
§8 #3/#4 and §5.3). It:

  1. flattens the new named HEAD's tree (the desired working-copy contents),
  2. flattens the previously-cached named HEAD's tree (clone_commit_id) to know
     which files were removed between the old and new HEAD,
  3. writes every blob from the new tree to the working copy (_checkout_flat_map),
  4. deletes files that existed at the old HEAD but not the new one
     (_remove_deleted_flat), pruning now-empty directories.

Server interaction: NONE. All objects were already downloaded by the preceding
Step__Pull__Fetch_Missing (api.read only). This step touches only local disk —
no api.read and no api.write — preserving the read-only / zero-knowledge
guarantee.
"""
from sgit_ai.safe_types.Safe_Str__Step_Name              import Safe_Str__Step_Name
from sgit_ai.safe_types.Safe_UInt__File_Count            import Safe_UInt__File_Count
from sgit_ai.schemas.workflow.pull.Schema__Pull__State   import Schema__Pull__State
from sgit_ai.workflow.Step                               import Step


class Step__Pull__RO__Checkout(Step):
    name          = Safe_Str__Step_Name('ro-checkout')
    input_schema  = Schema__Pull__State
    output_schema = Schema__Pull__State

    def execute(self, input: Schema__Pull__State, workspace) -> Schema__Pull__State:
        directory       = str(input.directory)
        sg_dir          = str(input.sg_dir)
        read_key        = bytes.fromhex(str(input.read_key_hex))
        named_commit_id = str(input.named_commit_id) if input.named_commit_id else ''
        old_commit_id   = str(input.clone_commit_id) if input.clone_commit_id else ''  # previously-cached named HEAD

        workspace.ensure_managers(sg_dir)

        merge_status   = ''
        added_files    = []
        modified_files = []
        deleted_files  = []

        if not named_commit_id:
            merge_status = 'up_to_date'
            workspace.progress('step', 'Up to date — no remote commits')
        elif named_commit_id == old_commit_id:
            merge_status = 'up_to_date'
            workspace.progress('step', 'Already up to date')
        else:
            merge_status = 'fast_forward'                                       # straight re-checkout, never a merge
            workspace.progress('step', 'Checking out named-branch HEAD')

            named_commit = workspace.vc.load_commit(named_commit_id, read_key)
            new_map      = workspace.sub_tree.flatten(str(named_commit.tree_id), read_key)

            # old_map (the previous named HEAD's tree) drives the added/modified
            # report when available. It may be empty if the cached HEAD pointer was
            # advanced ahead of the downloaded objects (see Step__Pull__RO__Load_Named_Head).
            old_map = {}
            if old_commit_id:
                old_commit = workspace.vc.load_commit(old_commit_id, read_key)
                old_map    = workspace.sub_tree.flatten(str(old_commit.tree_id), read_key)

            # Deletion baseline is the actual working copy on disk (like reset): this
            # prunes files removed in the new HEAD regardless of the cached-ref state,
            # and never deletes anything still present in the new HEAD.
            disk_map = workspace.sync_client._scan_local_directory(directory)

            workspace.sync_client._checkout_flat_map(directory, new_map, workspace.obj_store, read_key)
            workspace.sync_client._remove_deleted_flat(directory, disk_map, new_map)

            added_files    = [p for p in new_map if p not in old_map]
            modified_files = [p for p in new_map
                              if p in old_map and
                              new_map[p].get('blob_id') != old_map[p].get('blob_id')]
            deleted_files  = [p for p in disk_map if p not in new_map]

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
            merge_commit_id       = None,                                       # no commit ever created on RO pull
            added_files           = added_files    or None,
            modified_files        = modified_files or None,
            deleted_files         = deleted_files  or None,
        )
        return out
