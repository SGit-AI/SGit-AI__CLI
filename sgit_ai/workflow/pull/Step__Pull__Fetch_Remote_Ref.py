"""Step 3 — Fetch the named branch ref from the remote server."""
import os

from sgit_ai.safe_types.Safe_Str__Step_Name              import Safe_Str__Step_Name
from sgit_ai.safe_types.Safe_Str__Commit_Id              import Safe_Str__Commit_Id
from sgit_ai.schemas.workflow.pull.Schema__Pull__State   import Schema__Pull__State
from sgit_ai.workflow.Step                               import Step


class Step__Pull__Fetch_Remote_Ref(Step):
    name          = Safe_Str__Step_Name('fetch-remote-ref')
    input_schema  = Schema__Pull__State
    output_schema = Schema__Pull__State

    def _guard_rewind(self, workspace, input, read_key: bytes, remote_ref_data: bytes, last_known: str) -> None:
        """Refuse, before the local ref is touched, a remote named head that does not
        descend from the last one this clone fetched, unless --accept-rewind."""
        from sgit_ai.core.actions.status.Vault__Sync__Status import Vault__Sync__Status
        from sgit_ai.core.actions.pull.Vault__Ref_Guard      import Vault__Ref_Guard, REWOUND
        from sgit_ai.core.Vault__Errors                       import Vault__Ref_Rewind_Error
        from sgit_ai.storage.Vault__Scope                     import Vault__Scope
        sync = workspace.sync_client
        try:
            remote_head = Vault__Sync__Status(crypto=sync.crypto, api=sync.api)._parse_ref(remote_ref_data, read_key)
            if not remote_head or not last_known or remote_head == last_known:
                return
            directory = str(input.directory)
            c         = sync._init_components(directory)
            try:
                boundaries = set(Vault__Scope().from_local_config(sync._read_local_config(directory, c.storage)).boundary_ids())
            except Exception:
                boundaries = set()
            status = Vault__Sync__Status(crypto=sync.crypto, api=sync.api)
            fetched, connected = status._fetch_commit_chain(c, workspace.obj_store, read_key, remote_head,
                                                            limit=int(getattr(sync, 'commit_fetch_limit', 50) or 50),
                                                            boundaries=boundaries,
                                                            known={last_known, str(input.clone_commit_id or ''),
                                                                   workspace.ref_manager.read_ref(str(input.named_ref_id), read_key) or ''})
            guard   = Vault__Ref_Guard(crypto=sync.crypto)
            verdict = guard.classify(c, read_key, remote_head, last_known, connected,
                                     getattr(status, '_chain_reached_known', False), boundaries)
        except Exception as exc:                                 # cannot decide: never block on our own failure
            workspace.progress('warn', f'Rewind check skipped: {exc}')
            return
        if verdict != REWOUND:
            return
        if getattr(workspace, 'accept_rewind', False):
            workspace.progress('warn', f'Accepting a rewound named branch: {last_known} -> {remote_head}')
            workspace.rewound_from = last_known                  # the merge drops what was removed, keeps only this clone's own work
            return
        raise Vault__Ref_Rewind_Error(guard.message(remote_head, last_known))

    def execute(self, input: Schema__Pull__State, workspace) -> Schema__Pull__State:
        sg_dir   = str(input.sg_dir)
        read_key = bytes.fromhex(str(input.read_key_hex))
        vault_id = str(input.vault_id)
        named_ref_id = str(input.named_ref_id)

        workspace.ensure_managers(sg_dir)
        workspace.progress('step', 'Fetching remote ref')

        named_ref_file_id = f'bare/refs/{named_ref_id}'
        remote_reachable  = False
        from sgit_ai.core.Vault__Errors import Vault__Ref_Rewind_Error
        try:
            last_known = workspace.sync_client._read_last_remote_head(str(input.directory), workspace.storage)
        except Exception:
            last_known = ''
        try:
            remote_ref_data = workspace.sync_client.api.read(vault_id, named_ref_file_id)
            merging_other = bool(getattr(workspace, 'merge_from', None))        # another branch: no rewind baseline applies
            if remote_ref_data:
                if not merging_other:
                    self._guard_rewind(workspace, input, read_key, remote_ref_data, last_known)
                ref_path = os.path.join(sg_dir, named_ref_file_id)
                os.makedirs(os.path.dirname(ref_path), exist_ok=True)
                with open(ref_path, 'wb') as f:
                    f.write(remote_ref_data)
                remote_reachable = True
        except Vault__Ref_Rewind_Error:
            raise                                                    # refused on purpose, nothing written
        except Exception as exc:
            workspace.progress('warn', f'Could not fetch remote ref: {exc}')

        named_commit_id = workspace.ref_manager.read_ref(named_ref_id, read_key) or ''
        if remote_reachable and named_commit_id and not getattr(workspace, 'merge_from', None):
            try:
                workspace.sync_client._write_last_remote_head(str(input.directory), workspace.storage, named_commit_id)
            except Exception:
                pass

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
            named_commit_id       = Safe_Str__Commit_Id(named_commit_id) if named_commit_id else None,
            remote_reachable      = remote_reachable,
        )
        return out
