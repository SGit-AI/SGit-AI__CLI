"""Step 4 — Verify we can fast-forward: fetch remote ref and check ancestry."""
import os

from sgit_ai.safe_types.Safe_Str__Step_Name              import Safe_Str__Step_Name
from sgit_ai.safe_types.Safe_Str__Commit_Id              import Safe_Str__Commit_Id
from sgit_ai.schemas.workflow.push.Schema__Push__State   import Schema__Push__State
from sgit_ai.workflow.Step                               import Step


class Step__Push__Fast_Forward_Check(Step):
    name          = Safe_Str__Step_Name('fast-forward-check')
    input_schema  = Schema__Push__State
    output_schema = Schema__Push__State

    def execute(self, input: Schema__Push__State, workspace) -> Schema__Push__State:
        sg_dir          = str(input.sg_dir)
        read_key        = bytes.fromhex(str(input.read_key_hex))
        vault_id        = str(input.vault_id)
        named_ref_id    = str(input.named_ref_id)
        clone_commit_id = str(input.clone_commit_id) if input.clone_commit_id else ''
        named_commit_id = str(input.named_commit_id) if input.named_commit_id else ''

        workspace.ensure_managers(sg_dir)
        workspace.progress('step', 'Checking fast-forward eligibility')

        named_ref_file_id = f'bare/refs/{named_ref_id}'
        remote_commit_id  = ''
        try:
            remote_ref_data = workspace.sync_client.api.read(vault_id, named_ref_file_id)
            if remote_ref_data:
                ref_path = os.path.join(sg_dir, named_ref_file_id)
                os.makedirs(os.path.dirname(ref_path), exist_ok=True)
                with open(ref_path, 'wb') as f:
                    f.write(remote_ref_data)
        except Exception:
            pass

        remote_commit_id = workspace.ref_manager.read_ref(named_ref_id, read_key) or ''

        if remote_commit_id and remote_commit_id == clone_commit_id:
            can_fast_forward = True
        elif not remote_commit_id:
            can_fast_forward = True
        elif input.force:
            can_fast_forward = True
        elif remote_commit_id and clone_commit_id:
            try:
                from sgit_ai.core.actions.fetch.Vault__Fetch import Vault__Fetch
                from sgit_ai.storage.Vault__Storage import Vault__Storage
                fetcher = Vault__Fetch(crypto=workspace.sync_client.crypto,
                                       api=workspace.sync_client.api,
                                       storage=Vault__Storage())
                lca_id = fetcher.find_lca(workspace.obj_store, read_key,
                                          clone_commit_id, remote_commit_id)
                can_fast_forward = (lca_id == remote_commit_id)
            except Exception:
                can_fast_forward = False
        else:
            can_fast_forward = False

        if not can_fast_forward and not input.force:
            raise RuntimeError(
                f'Push rejected: remote has diverged from local branch. '
                f'Run `sgit pull` to merge remote changes first, or use --force.'
            )

        out = Schema__Push__State(
            vault_key             = input.vault_key,
            directory             = input.directory,
            force                 = input.force,
            sg_dir                = input.sg_dir,
            vault_id              = input.vault_id,
            branch_index_file_id  = input.branch_index_file_id,
            read_key_hex          = input.read_key_hex,
            write_key_hex         = input.write_key_hex,
            working_copy_clean    = input.working_copy_clean,
            clone_branch_id       = input.clone_branch_id,
            clone_ref_id          = input.clone_ref_id,
            named_ref_id          = input.named_ref_id,
            clone_commit_id       = input.clone_commit_id,
            named_commit_id       = input.named_commit_id,
            n_local_only_objects  = input.n_local_only_objects,
            remote_commit_id      = Safe_Str__Commit_Id(remote_commit_id) if remote_commit_id else None,
            can_fast_forward      = can_fast_forward,
        )
        return out
