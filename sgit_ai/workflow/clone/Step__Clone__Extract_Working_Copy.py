"""Step 9 — Check out files from the HEAD commit into the working directory."""
import time

from sgit_ai.safe_types.Safe_Str__Step_Name               import Safe_Str__Step_Name
from sgit_ai.schemas.workflow.clone.Schema__Clone__State  import Schema__Clone__State
from sgit_ai.workflow.Step                                import Step


class Step__Clone__Extract_Working_Copy(Step):
    name          = Safe_Str__Step_Name('extract-working-copy')
    input_schema  = Schema__Clone__State
    output_schema = Schema__Clone__State

    def execute(self, input: Schema__Clone__State, workspace) -> Schema__Clone__State:
        sg_dir          = str(input.sg_dir)
        directory       = str(input.directory)
        named_commit_id = str(input.named_commit_id) if input.named_commit_id else ''
        read_key        = bytes.fromhex(str(input.read_key_hex))

        workspace.ensure_managers(sg_dir)

        t_checkout_ms = 0
        n_trees       = int(input.n_trees or 0)

        scope_paths = [str(p) for p in (input.scope_paths or [])]
        if named_commit_id and not input.bare and not scope_paths:
            self._seed_from_indexes(workspace, input, directory, named_commit_id, read_key)   # a pack vault's flat map,
        if named_commit_id and not input.sparse and not input.bare:                        # files written or not
            workspace.progress('step', 'Extracting working copy' + (' (scoped)' if scope_paths else ''))
            _t0        = time.monotonic()
            commit_obj = workspace.vc.load_commit(named_commit_id, read_key)
            if scope_paths:
                from sgit_ai.core.scope.Vault__Scope       import Vault__Scope
                from sgit_ai.storage.Vault__Scoped_Tree    import Vault__Scoped_Tree
                scoped  = Vault__Scoped_Tree(crypto=workspace.sync_client.crypto, obj_store=workspace.obj_store).setup()
                flat, _ = scoped.flatten(str(commit_obj.tree_id), read_key, Vault__Scope().with_paths(scope_paths))
                missing = sorted(p for p, e in flat.items() if e.get('blob_id') and not workspace.obj_store.exists(str(e['blob_id'])))
                self._refuse_incomplete(missing)
                workspace.sync_client._checkout_flat_map(directory, flat, workspace.obj_store, read_key)
            else:
                # The flat map (cached for the head from here on, so the first status after
                # the clone opens no tree) and the same writer the pull uses, which seeds the
                # scan cache: that status then stats the files it wrote instead of reading
                # 4.2 GB back (26 Oct field report).
                from sgit_ai.storage.Vault__Object_Store import Vault__Object_Missing_Error
                tree_id = str(commit_obj.tree_id)
                if not workspace.obj_store.exists(tree_id):                     # a refused root tree (SP-1): the
                    raise Vault__Object_Missing_Error(f'object {tree_id} is not in the local store')   # typed error
                flat    = workspace.sub_tree.flatten(tree_id, read_key)
                dirs    = workspace.sub_tree.flatten_dirs(tree_id, read_key)
                for folder_tree in dirs.values():
                    if not workspace.obj_store.exists(str(folder_tree)):        # as the tree walk used to raise
                        raise Vault__Object_Missing_Error(f'object {folder_tree} is not in the local store')
                n_trees = len(dirs)
                missing = sorted(p for p, e in flat.items() if e.get('blob_id') and not workspace.obj_store.exists(str(e['blob_id'])))
                self._refuse_incomplete(missing)
                workspace.sync_client._checkout_flat_map(directory, flat, workspace.obj_store, read_key)
            t_checkout_ms = int((time.monotonic() - _t0) * 1000)

        data                  = input.json()
        data['t_checkout_ms'] = t_checkout_ms
        if n_trees and not int(input.n_trees or 0):
            data['n_trees'] = n_trees                                           # a pack clone: counted here, not walked
        return Schema__Clone__State.from_json(data)

    def _seed_from_indexes(self, workspace, input, directory: str, commit_id: str, read_key: bytes) -> None:
        """A pack vault with the advisory 'pack-indexes' feature: the head's flat map from
        the snapshot index the packs came with (dev pack 03 §5, clone), anchored to the
        root tree, so the flatten below opens one tree instead of every folder. Anything
        short of that means the flatten walks, as before."""
        if not getattr(input, 'pack_vault', False):
            return
        try:
            from sgit_ai.core.actions.pack.Vault__Pack_Index__Reader import Vault__Pack_Index__Reader
            index_id = str(input.index_id or input.branch_index_file_id or '')
            index    = workspace.branch_manager.load_branch_index(directory, index_id, read_key) if index_id else None
            reader   = Vault__Pack_Index__Reader(crypto=workspace.sync_client.crypto, api=workspace.sync_client.api)
            if index is None or not reader.usable_in(directory, index=index):
                return
            reader.setup_for(directory, read_key, index=index, key_manager=workspace.key_manager)
            if reader.seed_head_flat(directory, commit_id, read_key, workspace.sub_tree, workspace.progress) is not None:
                workspace.progress('step', 'Flat map from the pack indexes', f'from the {reader.last_seed}; no tree walk')
        except Exception:
            return

    def _refuse_incomplete(self, missing: list) -> None:
        """A HEAD file with no (verified) object must fail the clone, as it fails a
        pull: a working copy without it reads as that file deleted, and the next
        commit would delete it from the vault for everyone."""
        if not missing:
            return
        from sgit_ai.core.Vault__Errors import Vault__Integrity_Error
        shown = ', '.join(missing[:5]) + (f' (+{len(missing) - 5} more)' if len(missing) > 5 else '')
        raise Vault__Integrity_Error(
            f'clone incomplete: {len(missing)} file(s) at HEAD have no object the server would serve, '
            f'or the object it served failed its content-address check: {shown}. The directory is '
            f'not a usable clone (no key was written); remove it and try again. If it persists, the '
            f'server is missing data — a teammate whose clone has it can restore it with '
            f'`sgit check upload-objects`.')
