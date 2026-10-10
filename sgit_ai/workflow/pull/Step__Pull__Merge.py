"""Step 5 — Perform three-way merge (or fast-forward) between clone and named branch."""
import json
import os
import time

from sgit_ai.safe_types.Safe_Str__Step_Name              import Safe_Str__Step_Name
from sgit_ai.safe_types.Safe_Str__Commit_Id              import Safe_Str__Commit_Id
from sgit_ai.safe_types.Safe_UInt__File_Count            import Safe_UInt__File_Count
from sgit_ai.schemas.workflow.pull.Schema__Pull__State   import Schema__Pull__State
from sgit_ai.core.actions.pull.Vault__Pull__Guard         import Vault__Pull__Guard
from sgit_ai.core.Vault__Errors                           import Vault__Dirty_Working_Tree_Error
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

        from sgit_ai.core.scope.Vault__Scope     import Vault__Scope
        from sgit_ai.storage.Vault__Scoped_Tree  import Vault__Scoped_Tree
        scope        = Vault__Scope()
        local_config = None
        try:
            local_config = workspace.sync_client._read_local_config(directory, workspace.storage)
            scope        = Vault__Scope().from_local_config(local_config)
        except Exception:
            pass
        scoped_tree = None                                   # built only for a scoped clone

        def flat_of(tree_id):
            """(flat, opaque): the held folders' files + siblings by id. A whole-vault
            clone takes exactly the path it always took (plain flatten, no opaque)."""
            nonlocal scoped_tree
            if not scope.is_scoped():
                return workspace.sub_tree.flatten(str(tree_id), read_key), {}
            if scoped_tree is None:
                scoped_tree = Vault__Scoped_Tree(crypto=workspace.sync_client.crypto, obj_store=workspace.obj_store)
            return scoped_tree.flatten(str(tree_id), read_key, scope)

        merge_status    = ''
        n_conflicts     = 0
        merge_commit_id = ''
        added_files     = []
        modified_files  = []
        deleted_files   = []
        conflict_paths  = []
        kept_dirty      = []

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
            rewound_from = str(getattr(workspace, 'rewound_from', None) or '')

            if rewound_from and clone_commit_id and lca_id != clone_commit_id:
                result = self._take_rewind(workspace, input, directory, read_key, clone_ref_id, clone_commit_id,
                                           named_commit_id, rewound_from, flat_of, local_config,
                                           clone_branch_name, named_branch_name)
                merge_status    = 'rewound'
                merge_commit_id = result['commit_id']
                added_files, modified_files, deleted_files = result['added'], result['modified'], result['deleted']
                kept_dirty      = result['kept_dirty']
            elif lca_id == named_commit_id:
                merge_status = 'up_to_date'
                workspace.progress('step', 'Already up to date (LCA check)')
            elif lca_id == clone_commit_id:
                merge_status    = 'fast_forward'
                merge_commit_id = named_commit_id
                workspace.progress('step', 'Fast-forward merge')
                named_commit    = workspace.vc.load_commit(named_commit_id, read_key)
                theirs_map, _   = flat_of(named_commit.tree_id)
                ours_map        = {}
                if clone_commit_id:
                    ours_commit = workspace.vc.load_commit(clone_commit_id, read_key)
                    ours_map, _ = flat_of(ours_commit.tree_id)
                kept_dirty = self._guard_working_tree(workspace, directory, ours_map, theirs_map,
                                                      read_key, local_config)
                apply_map  = {p: e for p, e in theirs_map.items() if p not in kept_dirty}
                workspace.sync_client._checkout_flat_map(directory, apply_map, workspace.obj_store, read_key)
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
                    lca_commit  = workspace.vc.load_commit(lca_id, read_key)
                    base_map, _ = flat_of(lca_commit.tree_id)
                ours_map = {}
                if clone_commit_id:
                    ours_commit = workspace.vc.load_commit(clone_commit_id, read_key)
                    ours_map, _ = flat_of(ours_commit.tree_id)
                named_commit  = workspace.vc.load_commit(named_commit_id, read_key)
                theirs_map, theirs_opaque = flat_of(named_commit.tree_id)
                # out-of-scope folders: a scoped clone has no local changes there,
                # so the merged tree carries THEIR entries by id (theirs_opaque)

                merge_result = workspace.merge_helper.three_way_merge(base_map, ours_map, theirs_map)
                merged_map   = merge_result['merged_map']
                conflicts    = merge_result['conflicts']

                kept_dirty = self._guard_working_tree(workspace, directory, ours_map, merged_map,
                                                      read_key, local_config)
                apply_map  = {p: e for p, e in merged_map.items() if p not in kept_dirty}
                workspace.sync_client._checkout_flat_map(directory, apply_map, workspace.obj_store, read_key)
                workspace.sync_client._remove_deleted_flat(directory, ours_map, merged_map)

                if conflicts:
                    merge_status   = 'conflict'
                    n_conflicts    = len(conflicts)
                    conflict_paths = list(conflicts)
                    workspace.merge_helper.write_conflict_files(
                        directory, conflicts, theirs_map, workspace.obj_store, read_key
                    )
                    from sgit_ai.core.actions.merge.Vault__Merge__State import Vault__Merge__State
                    ms_mgr = Vault__Merge__State()
                    state  = ms_mgr.new_state(clone_commit_id, named_commit_id,
                                              lca_id, list(conflicts))
                    ms_mgr.write(directory, state)
                else:
                    merge_status   = 'merge'
                    merged_tree_id = (workspace.sub_tree.build_from_flat(merged_map, read_key, opaque=theirs_opaque)
                                      if theirs_opaque else
                                      workspace.sub_tree.build_from_flat(merged_map, read_key))
                    parent_ids     = [p for p in [clone_commit_id, named_commit_id] if p]

                    signing_key = None
                    clone_public_key_id = str(input.clone_public_key_id) if input.clone_public_key_id else ''
                    key_manager = getattr(workspace, 'key_manager', None)
                    if key_manager:
                        try:
                            signing_key = key_manager.load_private_key_locally(
                                clone_public_key_id, workspace.storage.local_dir(directory))
                        except Exception:
                            workspace.progress('warn', 'The merge commit is UNSIGNED: no signing key for this clone in .sg_vault/local/')

                    merge_msg        = f'Merge {named_branch_name} into {clone_branch_name}'
                    create_kw        = dict(read_key   = read_key,
                                            tree_id    = merged_tree_id,
                                            parent_ids = parent_ids,
                                            message    = merge_msg,
                                            branch_id  = str(input.clone_branch_id))
                    if signing_key is not None:
                        create_kw['signing_key']   = signing_key
                        create_kw['author_key_id'] = clone_public_key_id or None
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
            kept_dirty_files      = kept_dirty     or None,
        )
        return out

    def _take_rewind(self, workspace, input, directory: str, read_key: bytes, clone_ref_id: str,
                     clone_commit_id: str, named_commit_id: str, rewound_from: str, flat_of,
                     local_config, clone_branch_name: str, named_branch_name: str) -> dict:
        """An accepted rewind: the named branch now points at named_commit_id and the
        commits after it, up to rewound_from, were removed on purpose. Keeping the
        clone where it was would leave those commits 'ahead' and the next push would
        put them back. So: this clone's OWN work (its changes since the last remote
        head it knew, base = lca(clone, rewound_from)) is re-applied on top of the
        new head as one commit whose only parent is the new head; with no own work
        the clone simply moves to the new head. A conflict between the clone's own
        work and the rewind refuses, before anything is written."""
        from sgit_ai.core.Vault__Errors import Vault__Ref_Rewind_Error
        base_id = workspace.fetcher.find_lca(workspace.obj_store, read_key, clone_commit_id, rewound_from)
        if not base_id:
            raise Vault__Ref_Rewind_Error(
                f'cannot tell this clone\'s own commits from the history that was removed '
                f'(no common commit with {rewound_from}); nothing was changed. Copy out any work '
                f'you need, then clone the vault again.')
        base_map, _                = flat_of(workspace.vc.load_commit(base_id,         read_key).tree_id)
        ours_map, _                = flat_of(workspace.vc.load_commit(clone_commit_id, read_key).tree_id)
        theirs_map, theirs_opaque  = flat_of(workspace.vc.load_commit(named_commit_id, read_key).tree_id)
        merge_result = workspace.merge_helper.three_way_merge(base_map, ours_map, theirs_map)
        merged_map   = merge_result['merged_map']
        conflicts    = list(merge_result['conflicts'] or [])
        if conflicts:
            raise Vault__Ref_Rewind_Error(
                'your own commits change file(s) that the rewind also changes: '
                + ', '.join(sorted(conflicts)[:10]) + ('…' if len(conflicts) > 10 else '')
                + '. Nothing was changed. Copy those files out, clone the vault again, and re-apply them.')
        kept_dirty = self._guard_working_tree(workspace, directory, ours_map, merged_map, read_key, local_config)
        apply_map  = {p: e for p, e in merged_map.items() if p not in kept_dirty}
        workspace.sync_client._checkout_flat_map(directory, apply_map, workspace.obj_store, read_key)
        workspace.sync_client._remove_deleted_flat(directory, ours_map, merged_map)

        def blobs(m):
            return {p: e.get('blob_id') for p, e in m.items()}
        if blobs(merged_map) == blobs(theirs_map):
            commit_id = named_commit_id                              # nothing of our own: just take the new head
            workspace.progress('step', 'Rewind accepted: this clone now matches the named branch')
        else:
            merged_tree_id = (workspace.sub_tree.build_from_flat(merged_map, read_key, opaque=theirs_opaque)
                              if theirs_opaque else workspace.sub_tree.build_from_flat(merged_map, read_key))
            create_kw = dict(read_key=read_key, tree_id=merged_tree_id, parent_ids=[named_commit_id],
                             message=f'Re-apply {clone_branch_name} work on top of the rewound {named_branch_name}',
                             branch_id=str(input.clone_branch_id))
            clone_public_key_id = str(input.clone_public_key_id) if input.clone_public_key_id else ''
            key_manager         = getattr(workspace, 'key_manager', None)
            if key_manager and clone_public_key_id:
                try:
                    create_kw['signing_key']   = key_manager.load_private_key_locally(
                        clone_public_key_id, workspace.storage.local_dir(directory))
                    create_kw['author_key_id'] = clone_public_key_id
                except Exception:
                    create_kw.pop('signing_key', None)
                    workspace.progress('warn', 'This commit is UNSIGNED: no signing key for this clone in .sg_vault/local/')
            commit_id = workspace.vc.create_commit(**create_kw)
            workspace.progress('step', 'Rewind accepted: your own commits were re-applied on top of the new head')
        workspace.ref_manager.write_ref(clone_ref_id, commit_id, read_key)
        return dict(commit_id = commit_id,
                    added     = [p for p in merged_map if p not in ours_map],
                    modified  = [p for p in merged_map if p in ours_map and
                                 merged_map[p].get('blob_id') != ours_map[p].get('blob_id')],
                    deleted   = [p for p in ours_map if p not in merged_map],
                    kept_dirty= kept_dirty)

    def _guard_working_tree(self, workspace, directory: str, ours_map: dict, merged_map: dict,
                            read_key: bytes = None, local_config=None) -> list:
        """Uncommitted work must survive a pull. Returns the dirty paths the merge
        must leave alone; raises Vault__Dirty_Working_Tree_Error — before any
        write — when the merge would overwrite one. See Vault__Pull__Guard."""
        sync      = workspace.sync_client
        scan      = sync._scan_local_directory(directory)
        sparse    = bool(getattr(local_config, 'sparse', False)) if local_config is not None else False
        obj_store = workspace.obj_store

        def blob_hash(blob_id: str) -> str:
            # the incoming file's real content, from the decrypted blob (never the tree entry's claim)
            try:
                if read_key is None or not obj_store.exists(blob_id):
                    return ''
                return sync.crypto.content_hash(sync.crypto.decrypt(read_key, obj_store.load(blob_id)))
            except Exception:
                return ''

        guard  = Vault__Pull__Guard()
        dirty  = guard.dirty_paths(directory, ours_map, scan, obj_store=obj_store, sparse=sparse)
        plan   = guard.plan(dirty, ours_map, merged_map, scan, blob_hash_fn=blob_hash)
        if plan['blocked']:
            raise Vault__Dirty_Working_Tree_Error(guard.message(plan['blocked']))
        for path in plan['carry_over']:
            workspace.progress('warn', f'{path}: kept your uncommitted change (not touched by the incoming commits)')
        return plan['carry_over']
