"""Vault__Sync__Move — vault move/key-rotation action (Brief 02)."""
import json
import os
import shutil

from osbot_utils.type_safe.Type_Safe         import Type_Safe
from sgit_ai.crypto.Vault__Crypto            import Vault__Crypto
from sgit_ai.network.api.Vault__API          import Vault__API
from sgit_ai.safe_types.Safe_Str__Base_URL   import Safe_Str__Base_URL
from sgit_ai.safe_types.Safe_Str__File_Path  import Safe_Str__File_Path
from sgit_ai.safe_types.Safe_Str__Vault_Key  import Safe_Str__Vault_Key
from sgit_ai.safe_types.Safe_Str__Commit_Message import Safe_Str__Commit_Message
from sgit_ai.schemas.workflow.move.Schema__Move__State import Schema__Move__State

SG_VAULT     = '.sg_vault'
SG_VAULT_NEW = '.sg_vault_new'


class Vault__Sync__Move(Type_Safe):
    crypto : Vault__Crypto
    api    : Vault__API

    def move(self, directory: str, new_vault_key: str = None,
             target_api_url: str = None, reason: str = '',
             on_progress: callable = None, dry_run: bool = False) -> dict:
        """Execute the 8-step vault move workflow."""
        import tempfile
        import shutil
        from sgit_ai.workflow.move.Workflow__Vault_Move import Workflow__Vault_Move
        from sgit_ai.workflow.move.Move__Workspace      import Move__Workspace
        from sgit_ai.safe_types.Safe_Str__File_Path     import Safe_Str__File_Path as _FP

        directory = os.path.abspath(directory)
        state = Schema__Move__State(
            directory      = Safe_Str__File_Path(directory),
            new_vault_key  = Safe_Str__Vault_Key(new_vault_key) if new_vault_key else None,
            target_api_url = Safe_Str__Base_URL(target_api_url) if target_api_url else None,
            reason         = Safe_Str__Commit_Message(reason) if reason else None,
            dry_run        = dry_run,
        )
        tmp_workspace = tempfile.mkdtemp(prefix='sgit-move-ws-')
        try:
            workspace     = Move__Workspace(workspace_dir=_FP(tmp_workspace))
            workspace.api = self.api   # inject api for in-memory testing
            final         = Workflow__Vault_Move().execute(state, workspace)
        finally:
            shutil.rmtree(tmp_workspace, ignore_errors=True)
        return final

    def cleanup(self, directory: str, on_progress: callable = None) -> dict:
        """Finish or roll back a partially completed move.

        Detection:
        - If .sg_vault_new/ exists locally: rename has not happened → complete 8a then 8b.
        - If local clone is on new vault (move-history shows rotation) but old vault still
          live on server → retry 8b only.
        - If old vault already tombstoned → treat as clean.
        - If nothing to clean up → raise RuntimeError.
        """
        directory  = os.path.abspath(directory)
        sg_dir     = os.path.join(directory, SG_VAULT)
        new_sg_dir = os.path.join(directory, SG_VAULT_NEW)

        if os.path.isdir(new_sg_dir):
            return self._cleanup_resume_rename(directory, sg_dir, new_sg_dir)

        if os.path.isdir(sg_dir):
            result = self._cleanup_retry_server_delete(directory, sg_dir)
            if result:
                return result

        raise RuntimeError(
            'No pending vault move to clean up. '
            'Neither .sg_vault_new/ exists nor does move-history show a recent in-progress move.'
        )

    def _cleanup_resume_rename(self, directory: str, sg_dir: str, new_sg_dir: str) -> dict:
        """8a: rename .sg_vault_new/ → .sg_vault/ (old vault may still be present)."""
        from datetime import datetime, timezone
        import sys

        now_ts   = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        old_bak  = os.path.join(directory, f'.sg_vault_old_{now_ts}')

        if os.path.isdir(sg_dir):
            os.rename(sg_dir, old_bak)
        os.rename(new_sg_dir, sg_dir)

        try:
            shutil.rmtree(old_bak)
        except Exception:
            pass

        server_deleted = self._try_server_delete_from_history(directory, sg_dir)
        return dict(
            status         = 'cleanup_complete',
            renamed        = True,
            server_deleted = server_deleted,
        )

    def _cleanup_retry_server_delete(self, directory: str, sg_dir: str) -> dict:
        """If move-history shows a recent move but old vault is still live, retry 8b."""
        hist_path = os.path.join(sg_dir, 'local', 'move-history.json')
        if not os.path.isfile(hist_path):
            return None
        with open(hist_path) as f:
            data = json.load(f)
        moves = data.get('moves', [])
        if not moves:
            return None

        last = moves[-1]
        from_vault_id = last.get('from_vault_id', '')
        from_api      = last.get('from_api', '')
        if not from_vault_id:
            return None

        server_deleted = self._try_server_delete(directory, sg_dir, from_vault_id, from_api)
        if server_deleted is None:
            return None  # already tombstoned; move was already complete, nothing pending
        return dict(
            status         = 'cleanup_complete',
            renamed        = False,
            server_deleted = server_deleted,
        )

    def _try_server_delete_from_history(self, directory: str, sg_dir: str) -> bool:
        hist_path = os.path.join(sg_dir, 'local', 'move-history.json')
        if not os.path.isfile(hist_path):
            return False
        with open(hist_path) as f:
            data = json.load(f)
        moves = data.get('moves', [])
        if not moves:
            return False
        last          = moves[-1]
        from_vault_id = last.get('from_vault_id', '')
        from_api      = last.get('from_api', '')
        return self._try_server_delete(directory, sg_dir, from_vault_id, from_api)

    def _try_server_delete(self, directory: str, sg_dir: str,
                            vault_id: str, api_url: str) -> bool:
        import sys
        if not vault_id:
            return False
        old_key_path = os.path.join(sg_dir, 'local', 'vault_key')
        if not os.path.isfile(old_key_path):
            return False
        with open(old_key_path) as f:
            vault_key = f.read().strip()
        try:
            keys      = self.crypto.derive_keys_from_vault_key(vault_key)
            write_key = keys['write_key']
            if hasattr(self.api, 'is_tombstoned') and self.api.is_tombstoned(vault_id):
                return None  # already tombstoned; caller should treat as no-pending
            result    = self.api.delete_vault(vault_id, write_key)
            return result.get('status') == 'deleted'
        except RuntimeError as e:
            if '403' in str(e):
                return None  # already tombstoned; caller should treat as no-pending
            print(f'Warning: server delete failed: {e}', file=sys.stderr)
            return False
        except Exception as e:
            print(f'Warning: server delete failed: {e}', file=sys.stderr)
            return False
