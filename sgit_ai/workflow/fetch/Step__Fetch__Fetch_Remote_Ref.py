"""Step 3 — Fetch the named branch ref from the remote server."""
import os

from sgit_ai.safe_types.Safe_Str__Step_Name               import Safe_Str__Step_Name
from sgit_ai.safe_types.Safe_Str__Commit_Id               import Safe_Str__Commit_Id
from sgit_ai.schemas.workflow.fetch.Schema__Fetch__State  import Schema__Fetch__State
from sgit_ai.workflow.Step                                import Step


class Step__Fetch__Fetch_Remote_Ref(Step):
    name          = Safe_Str__Step_Name('fetch-remote-ref')
    input_schema  = Schema__Fetch__State
    output_schema = Schema__Fetch__State

    def execute(self, input: Schema__Fetch__State, workspace) -> Schema__Fetch__State:
        sg_dir       = str(input.sg_dir)
        read_key     = bytes.fromhex(str(input.read_key_hex))
        vault_id     = str(input.vault_id)
        named_ref_id = str(input.named_ref_id)

        workspace.ensure_managers(sg_dir)
        workspace.progress('step', 'Fetching remote ref')

        named_ref_file_id = f'bare/refs/{named_ref_id}'
        remote_reachable  = False
        remote_head       = ''
        try:
            remote_ref_data = workspace.sync_client.api.read(vault_id, named_ref_file_id)
            if remote_ref_data:
                import json
                try:
                    remote_head = json.loads(workspace.sync_client.crypto.decrypt(read_key, remote_ref_data)).get('commit_id') or ''
                except Exception:
                    remote_head = ''
                if not remote_head:                                  # reachable, but it does not open: an error,
                    from sgit_ai.core.Vault__Errors import Vault__Unreadable_Ref_Error   # never the local ref (F3)
                    raise Vault__Unreadable_Ref_Error(workspace.sync_client._unreadable_ref_message(named_ref_id))
                remote_reachable = bool(remote_head)
        except Exception as exc:
            from sgit_ai.core.Vault__Errors import Vault__Unreadable_Ref_Error
            if isinstance(exc, Vault__Unreadable_Ref_Error):
                raise
            workspace.progress('warn', f'Could not fetch remote ref: {exc}')

        # Fetch downloads objects (content-addressed, verified before write) and never writes
        # the local named ref: only pull's verify-then-accept does (review 0a0707d F7).
        named_commit_id = remote_head or workspace.ref_manager.read_ref(named_ref_id, read_key) or ''

        return Schema__Fetch__State(
            vault_key             = input.vault_key,
            directory             = input.directory,
            sg_dir                = input.sg_dir,
            vault_id              = input.vault_id,
            branch_index_file_id  = input.branch_index_file_id,
            read_key_hex          = input.read_key_hex,
            clone_commit_id       = input.clone_commit_id,
            named_ref_id          = input.named_ref_id,
            named_commit_id       = Safe_Str__Commit_Id(named_commit_id) if named_commit_id else None,
            remote_reachable      = remote_reachable,
        )
