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
        if not last_known:
            return                                               # never accepted a head of this branch: nothing to compare
        try:
            remote_head = Vault__Sync__Status(crypto=sync.crypto, api=sync.api)._parse_ref(remote_ref_data, read_key)
            if not remote_head or remote_head == last_known:
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
        except Exception as exc:                                 # cannot decide: refuse rather than accept blind (review K2)
            if getattr(workspace, 'accept_rewind', False):
                workspace.progress('warn', f'Rewind check failed ({exc}); continuing because --accept-rewind was given')
                return
            raise Vault__Ref_Rewind_Error(f'could not check whether the server moved this branch backwards ({exc}); '
                                          f'nothing was changed. Try again, or pass --accept-rewind to continue anyway.')
        if verdict != REWOUND:
            return
        if getattr(workspace, 'accept_rewind', False):
            workspace.progress('warn', f'Accepting a rewound named branch: {last_known} -> {remote_head}')
            workspace.rewound_from = last_known                  # the merge drops what was removed, keeps only this clone's own work
            return
        raise Vault__Ref_Rewind_Error(guard.message(remote_head, last_known))

    def _parse_ref(self, crypto, ref_data: bytes, read_key: bytes) -> str:
        import json
        try:
            return json.loads(crypto.decrypt(read_key, ref_data)).get('commit_id') or ''
        except Exception:
            return ''

    def execute(self, input: Schema__Pull__State, workspace) -> Schema__Pull__State:
        sg_dir   = str(input.sg_dir)
        read_key = bytes.fromhex(str(input.read_key_hex))
        vault_id = str(input.vault_id)
        named_ref_id = str(input.named_ref_id)

        workspace.ensure_managers(sg_dir)
        workspace.progress('step', 'Fetching remote ref')

        named_ref_file_id = f'bare/refs/{named_ref_id}'
        remote_reachable  = False
        from sgit_ai.core.Vault__Errors import Vault__Ref_Rewind_Error, Vault__Unreadable_Ref_Error
        accept_rewind = bool(getattr(workspace, 'accept_rewind', False))
        try:                                                         # this branch's own accepted head: a merge from
            last_known = workspace.sync_client._accepted_head(          # another branch is guarded too (review B3)
                str(input.directory), workspace.storage, accept_rewind, named_ref_id)
        except Vault__Ref_Rewind_Error:
            raise                                                    # an unreadable record refuses (L1)
        except Exception:
            last_known = ''
        remote_head = ''
        try:
            remote_ref_data = workspace.sync_client.api.read(vault_id, named_ref_file_id)
            if remote_ref_data:
                self._guard_rewind(workspace, input, read_key, remote_ref_data, last_known)
                remote_head      = self._parse_ref(workspace.sync_client.crypto, remote_ref_data, read_key)
                if not remote_head:                                  # reachable, but the ref does not open: an
                    raise Vault__Unreadable_Ref_Error(               # error, never "could not reach remote" (F9)
                        f'the server\'s ref for this branch ({named_ref_file_id}) does not decrypt with this '
                        f'vault\'s key (damaged, or replaced by the host); nothing was changed')
                remote_reachable = bool(remote_head)
                workspace.remote_ref_data = remote_ref_data if remote_head else None
        except (Vault__Ref_Rewind_Error, Vault__Unreadable_Ref_Error):
            raise                                                    # refused on purpose, nothing written
        except Exception as exc:
            workspace.progress('warn', f'Could not fetch remote ref: {exc}')

        # Nothing is written here. The server's head is held in memory; fetch-missing writes
        # the local named ref and the baseline once the signature policy has passed and the
        # objects are local. Writing it first meant a refused pull still left the unsigned
        # head as the local ref, and a later switch checked it out (review d3b8eef N3).
        named_commit_id = remote_head or workspace.ref_manager.read_ref(named_ref_id, read_key) or ''

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
