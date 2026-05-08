import os

from osbot_utils.type_safe.Type_Safe             import Type_Safe
from sgit_ai.core.actions.merge.Vault__Merge__State import Vault__Merge__State
from sgit_ai.crypto.Vault__Crypto                import Vault__Crypto
from sgit_ai.network.api.Vault__API              import Vault__API


class Vault__Merge__Abort(Type_Safe):
    crypto : Vault__Crypto
    api    : Vault__API

    def abort(self, directory: str, keep_conflict_files: bool = False) -> dict:
        merge_state_mgr = Vault__Merge__State()
        state = merge_state_mgr.read(directory)
        if state is None:
            raise RuntimeError('No merge in progress.')

        all_paths = [str(p) for p in (state.conflict_paths or [])] + \
                    [str(p) for p in (state.resolved_paths  or [])]

        if not keep_conflict_files:
            removed = self._remove_conflict_files(directory, all_paths)
        else:
            removed = []

        ours_commit_id = str(state.ours_commit_id) if state.ours_commit_id else ''
        if ours_commit_id:
            from sgit_ai.core.actions.pull.Vault__Sync__Pull import Vault__Sync__Pull
            Vault__Sync__Pull(crypto=self.crypto, api=self.api).reset(
                directory, commit_id=ours_commit_id
            )

        merge_state_mgr.delete(directory)
        return dict(
            status          = 'aborted',
            restored_to     = ours_commit_id,
            conflict_files_removed = len(removed),
        )

    def _remove_conflict_files(self, directory: str, paths: list) -> list:
        removed = []
        for rel_path in paths:
            conflict_path = os.path.join(directory, rel_path + '.conflict')
            if os.path.isfile(conflict_path):
                os.remove(conflict_path)
                removed.append(rel_path + '.conflict')
        return removed
