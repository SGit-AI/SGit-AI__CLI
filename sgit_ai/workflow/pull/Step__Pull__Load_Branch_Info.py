"""Step 2 — Load branch index and read current clone/named branch commit IDs."""
import os

from sgit_ai.safe_types.Safe_Str__Step_Name              import Safe_Str__Step_Name
from sgit_ai.safe_types.Safe_Str__Branch_Id              import Safe_Str__Branch_Id
from sgit_ai.safe_types.Safe_Str__Ref_Id                 import Safe_Str__Ref_Id
from sgit_ai.safe_types.Safe_Str__Commit_Id              import Safe_Str__Commit_Id
from sgit_ai.schemas.workflow.pull.Schema__Pull__State   import Schema__Pull__State
from sgit_ai.workflow.Step                               import Step


class Step__Pull__Load_Branch_Info(Step):
    name          = Safe_Str__Step_Name('load-branch-info')
    input_schema  = Schema__Pull__State
    output_schema = Schema__Pull__State

    def _refresh_index(self, workspace, directory: str) -> None:
        from sgit_ai.core.actions.index.Vault__Index_Sync import Vault__Index_Sync
        from sgit_ai.storage.Vault__Format                import Vault__Format, Vault__Client_Too_Old_Error
        sync = workspace.sync_client
        try:
            c   = sync._init_components(directory)
            out = Vault__Index_Sync(crypto=sync.crypto, api=sync.api).refresh(c, directory, write_key=c.write_key or None)
            if out.get('restored'):
                workspace.progress('step', f'Branch index: restored {out["restored"]} entr(y/ies) the remote copy had lost')
            for name, old, new in out.get('tags_changed') or []:          # a tag that moves is worth a line, a new one too
                if old and new:
                    workspace.progress('warn', f'Tag {name} now points to a different tag object ({old} -> {new}); '
                                               f'check it with: sgit vault tag show {name}')
                elif new:
                    workspace.progress('step', f'New tag: {name}')
                else:
                    workspace.progress('warn', f'Tag {name} was deleted')
            index = c.branch_manager.load_branch_index(directory, c.branch_index_file_id, c.read_key)
            workspace.obj_store.id_hex_len = Vault__Format().id_hex_len(index)
            from sgit_ai.core.actions.verify.Vault__Key_Fetch import Vault__Key_Fetch
            fetch = Vault__Key_Fetch(crypto=sync.crypto, api=sync.api)        # teammates registered since this clone was made
            fetch.fetch_missing(c, fetch.branch_key_ids(index))
        except Vault__Client_Too_Old_Error:
            raise
        except Exception as exc:
            workspace.progress('warn', f'Could not refresh the branch index from the remote: {exc}')

    def execute(self, input: Schema__Pull__State, workspace) -> Schema__Pull__State:
        sg_dir   = str(input.sg_dir)
        read_key = bytes.fromhex(str(input.read_key_hex))
        vault_id = str(input.vault_id)

        workspace.ensure_managers(sg_dir)
        workspace.progress('step', 'Loading branch info')

        from sgit_ai.storage.Vault__Storage import Vault__Storage
        storage      = Vault__Storage()
        local_config = workspace.sync_client._read_local_config(str(input.directory), storage)
        clone_branch_id = str(local_config.my_branch_id)

        branch_index_file_id = str(input.branch_index_file_id)
        if not branch_index_file_id:
            raise RuntimeError('No branch index found — is this a v2 vault?')

        # The index is a shared document: take the remote copy, merge it with ours
        # (entries the web UI's overwrite dropped come back), honour the format gate,
        # and write the merge back with compare-and-swap. Offline: use the local copy.
        self._refresh_index(workspace, str(input.directory))

        branch_index = workspace.branch_manager.load_branch_index(
            str(input.directory), branch_index_file_id, read_key
        )

        clone_meta = workspace.branch_manager.get_branch_by_id(branch_index, clone_branch_id)
        if not clone_meta:
            raise RuntimeError(f'Clone branch not found: {clone_branch_id}')

        merge_from = str(getattr(workspace, 'merge_from', None) or '')
        if merge_from:                                       # `sgit branch merge <name>`: theirs is that branch
            named_meta = (workspace.branch_manager.get_branch_by_name(branch_index, merge_from) or
                          workspace.branch_manager.get_branch_by_id(branch_index, merge_from))
            if not named_meta or str(named_meta.branch_type.value) != 'named':
                raise RuntimeError(f'Branch not found: {merge_from} (sgit branch list)')
        else:
            named_meta = workspace.branch_manager.tracked_named_branch(branch_index, clone_branch_id)
        if not named_meta:
            raise RuntimeError('The named branch this clone tracks was not found in the branch index')

        from osbot_utils.type_safe.primitives.core.Safe_Str import Safe_Str

        clone_commit_id     = workspace.ref_manager.read_ref(str(clone_meta.head_ref_id), read_key) or ''
        _pk_id              = getattr(clone_meta, 'public_key_id', None)
        _cn                 = getattr(clone_meta, 'name', None)
        _nn                 = getattr(named_meta, 'name', None)
        clone_public_key_id = str(_pk_id) if _pk_id else ''
        clone_branch_name   = str(_cn)    if _cn    else ''
        named_branch_name   = str(_nn)    if _nn    else ''

        out = Schema__Pull__State(
            vault_key             = input.vault_key,
            directory             = input.directory,
            sg_dir                = input.sg_dir,
            vault_id              = input.vault_id,
            branch_index_file_id  = input.branch_index_file_id,
            read_key_hex          = input.read_key_hex,
            clone_branch_id       = Safe_Str__Branch_Id(clone_branch_id),
            clone_ref_id          = Safe_Str__Ref_Id(str(clone_meta.head_ref_id)),
            named_ref_id          = Safe_Str__Ref_Id(str(named_meta.head_ref_id)),
            clone_commit_id       = Safe_Str__Commit_Id(clone_commit_id) if clone_commit_id else None,
            clone_public_key_id   = clone_public_key_id or None,
            clone_branch_name     = clone_branch_name or None,
            named_branch_name     = named_branch_name or None,
        )
        return out
