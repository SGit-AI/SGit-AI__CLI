import json
import os

from datetime import datetime, timezone

from osbot_utils.type_safe.Type_Safe          import Type_Safe
from sgit_ai.schemas.merge.Schema__Merge_State import Schema__Merge_State

MERGE_STATE_FILE = 'merge_state.json'


class Vault__Merge__State(Type_Safe):

    def state_path(self, directory: str) -> str:
        from sgit_ai.storage.Vault__Storage import Vault__Storage
        return os.path.join(Vault__Storage().local_dir(directory), MERGE_STATE_FILE)

    def exists(self, directory: str) -> bool:
        return os.path.isfile(self.state_path(directory))

    def read(self, directory: str) -> Schema__Merge_State:
        path = self.state_path(directory)
        if not os.path.isfile(path):
            return None
        with open(path) as f:
            raw = json.load(f)
        if 'clone_commit_id' in raw:
            raw = self._migrate_legacy(raw)
        return Schema__Merge_State.from_json(raw)

    def write(self, directory: str, state: Schema__Merge_State) -> None:
        path = self.state_path(directory)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w') as f:
            json.dump(state.json(), f, indent=2)

    def delete(self, directory: str) -> None:
        path = self.state_path(directory)
        if os.path.isfile(path):
            os.remove(path)

    def check_not_in_progress(self, directory: str, action: str) -> None:
        from sgit_ai.core.Vault__Errors import Vault__Merge_In_Progress_Error
        if self.exists(directory):
            raise Vault__Merge_In_Progress_Error(
                f'Cannot {action}: merge in progress. '
                f"Use 'sgit resolve' to resolve conflicts, then 'sgit commit'. "
                f"Or 'sgit merge-abort' to discard the merge."
            )

    def _migrate_legacy(self, raw: dict) -> dict:
        conflicts = raw.get('conflicts') or []
        if isinstance(conflicts, dict):
            conflicts = list(conflicts.keys())
        return {
            'schema_version'  : 1,
            'ours_commit_id'  : raw.get('clone_commit_id', ''),
            'theirs_commit_id': raw.get('named_commit_id', ''),
            'lca_id'          : raw.get('lca_id', ''),
            'started_at'      : '',
            'conflict_paths'  : conflicts,
            'resolved_paths'  : [],
        }

    def new_state(self, ours_commit_id: str, theirs_commit_id: str,
                  lca_id: str, conflict_paths: list) -> Schema__Merge_State:
        from sgit_ai.safe_types.Safe_Str__Commit_Id     import Safe_Str__Commit_Id
        from sgit_ai.safe_types.Safe_Str__ISO_Timestamp import Safe_Str__ISO_Timestamp
        from sgit_ai.safe_types.Safe_UInt__Vault_Version import Safe_UInt__Vault_Version
        now = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        data = {
            'schema_version'  : 1,
            'ours_commit_id'  : ours_commit_id or '',
            'theirs_commit_id': theirs_commit_id or '',
            'lca_id'          : lca_id or '',
            'started_at'      : now,
            'conflict_paths'  : conflict_paths or [],
            'resolved_paths'  : [],
        }
        return Schema__Merge_State.from_json(data)
