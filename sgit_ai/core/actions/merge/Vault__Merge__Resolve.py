import os

from osbot_utils.type_safe.Type_Safe             import Type_Safe
from sgit_ai.core.actions.merge.Vault__Merge__State import Vault__Merge__State


class Vault__Merge__Resolve(Type_Safe):
    crypto : object = None                          # Vault__Crypto: needed to restore one side of a marker file

    def resolve_file(self, directory: str, rel_path: str, strategy: str) -> dict:
        merge_state_mgr = Vault__Merge__State()
        state = merge_state_mgr.read(directory)
        if state is None:
            raise RuntimeError('No merge in progress.')

        conflict_paths = [str(p) for p in (state.conflict_paths or [])]
        resolved_paths = [str(p) for p in (state.resolved_paths or [])]

        if rel_path not in conflict_paths:
            if rel_path in resolved_paths:
                return dict(status='already_resolved', path=rel_path)
            raise RuntimeError(f'No conflict for path: {rel_path}')

        markers = {str(p) for p in (getattr(state, 'marker_paths', None) or [])}
        if rel_path in markers and strategy in ('ours', 'theirs'):
            commit_id = state.ours_commit_id if strategy == 'ours' else state.theirs_commit_id
            self._restore_side(directory, rel_path, str(commit_id or ''))      # the markers give way to one side
        elif strategy == 'ours':
            self._resolve_ours(directory, rel_path)
        elif strategy == 'theirs':
            self._resolve_theirs(directory, rel_path)
        elif strategy == 'mark':
            from sgit_ai.core.actions.merge.Vault__Merge import Vault__Merge
            if rel_path in markers and Vault__Merge(crypto=self.crypto).has_marker_block(directory, rel_path):
                raise RuntimeError(f'{rel_path} still has conflict markers: edit them out, or take one side '
                                   f'with sgit resolve {rel_path} --ours / --theirs')
            if rel_path not in markers:
                self._resolve_ours(directory, rel_path)                        # your edited file stands
        else:
            raise RuntimeError(f'Unknown strategy: {strategy}. Use --ours or --theirs.')

        conflict_paths.remove(rel_path)
        resolved_paths.append(rel_path)

        data = state.json()
        data['conflict_paths'] = conflict_paths
        data['resolved_paths'] = resolved_paths
        from sgit_ai.schemas.merge.Schema__Merge_State import Schema__Merge_State
        new_state = Schema__Merge_State.from_json(data)
        merge_state_mgr.write(directory, new_state)

        remaining = len(conflict_paths)
        if remaining == 0:
            print("All conflicts resolved. Run 'sgit commit' to finalise the merge.")
        else:
            print(f'{remaining} conflict(s) remaining: {conflict_paths}')

        return dict(status='resolved', path=rel_path, strategy=strategy,
                    remaining=remaining)

    def resolve_all(self, directory: str, strategy: str) -> dict:
        merge_state_mgr = Vault__Merge__State()
        state = merge_state_mgr.read(directory)
        if state is None:
            raise RuntimeError('No merge in progress.')

        conflict_paths = [str(p) for p in (state.conflict_paths or [])]
        resolved_count = 0
        for rel_path in list(conflict_paths):
            self.resolve_file(directory, rel_path, strategy)
            resolved_count += 1

        return dict(status='all_resolved', resolved=resolved_count, strategy=strategy)

    def show(self, directory: str) -> dict:
        merge_state_mgr = Vault__Merge__State()
        state = merge_state_mgr.read(directory)
        if state is None:
            raise RuntimeError('No merge in progress.')
        conflict_paths = [str(p) for p in (state.conflict_paths or [])]
        resolved_paths = [str(p) for p in (state.resolved_paths or [])]
        print(f'Unresolved conflicts ({len(conflict_paths)}):')
        for p in conflict_paths:
            print(f'  {p}')
        if resolved_paths:
            print(f'Resolved ({len(resolved_paths)}):')
            for p in resolved_paths:
                print(f'  {p}')
        return dict(conflict_paths=conflict_paths, resolved_paths=resolved_paths)

    def _restore_side(self, directory: str, rel_path: str, commit_id: str) -> None:
        """Write `rel_path` as it is in `commit_id` (ours or theirs of the merge), over
        the marker file."""
        from sgit_ai.core.Vault__Sync__Base      import Vault__Sync__Base
        from sgit_ai.storage.Vault__Commit       import Vault__Commit
        from sgit_ai.storage.Vault__Path_Guard   import Vault__Path_Guard
        from sgit_ai.storage.Vault__Sub_Tree     import Vault__Sub_Tree
        if self.crypto is None or not commit_id:
            raise RuntimeError(f'cannot restore one side of {rel_path}: run sgit resolve from the CLI')
        c      = Vault__Sync__Base(crypto=self.crypto)._init_components(directory)
        commit = Vault__Commit(crypto=self.crypto, pki=c.pki, object_store=c.obj_store,
                               ref_manager=c.ref_manager).load_commit(commit_id, c.read_key)
        entry  = Vault__Sub_Tree(crypto=self.crypto, obj_store=c.obj_store).flatten(str(commit.tree_id), c.read_key).get(rel_path)
        guard  = Vault__Path_Guard()
        target = guard.safe_join(directory, rel_path)
        if entry is None:                                                      # that side deleted it
            if os.path.isfile(target):
                os.remove(target)
            return
        with open(target, 'wb') as f:
            f.write(self.crypto.decrypt(c.read_key, c.obj_store.load(entry['blob_id'])))

    def _resolve_ours(self, directory: str, rel_path: str) -> None:
        from sgit_ai.storage.Vault__Path_Guard import Vault__Path_Guard
        guard = Vault__Path_Guard()
        if not guard.is_writable(directory, rel_path + '.conflict'):       # paths come from merge state (vault data)
            return
        conflict = guard.safe_join(directory, rel_path + '.conflict')
        if os.path.isfile(conflict):
            os.remove(conflict)

    def _resolve_theirs(self, directory: str, rel_path: str) -> None:
        from sgit_ai.storage.Vault__Path_Guard import Vault__Path_Guard
        guard = Vault__Path_Guard()
        src = guard.safe_join(directory, rel_path + '.conflict')
        dst = guard.safe_join(directory, rel_path)          # rel_path is vault-derived — contain it
        if os.path.isfile(src):
            os.replace(src, dst)
