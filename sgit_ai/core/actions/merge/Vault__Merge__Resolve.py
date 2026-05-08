import os

from osbot_utils.type_safe.Type_Safe             import Type_Safe
from sgit_ai.core.actions.merge.Vault__Merge__State import Vault__Merge__State


class Vault__Merge__Resolve(Type_Safe):

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

        if strategy == 'ours':
            self._resolve_ours(directory, rel_path)
        elif strategy == 'theirs':
            self._resolve_theirs(directory, rel_path)
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

    def _resolve_ours(self, directory: str, rel_path: str) -> None:
        conflict = os.path.join(directory, rel_path + '.conflict')
        if os.path.isfile(conflict):
            os.remove(conflict)

    def _resolve_theirs(self, directory: str, rel_path: str) -> None:
        src = os.path.join(directory, rel_path + '.conflict')
        dst = os.path.join(directory, rel_path)
        if os.path.isfile(src):
            os.replace(src, dst)
