"""Step 2 — Verify the working copy has no uncommitted changes."""
from sgit_ai.safe_types.Safe_Str__Step_Name              import Safe_Str__Step_Name
from sgit_ai.schemas.workflow.push.Schema__Push__State   import Schema__Push__State
from sgit_ai.workflow.Step                               import Step


class Step__Push__Check_Clean(Step):
    name          = Safe_Str__Step_Name('check-clean')
    input_schema  = Schema__Push__State
    output_schema = Schema__Push__State

    def execute(self, input: Schema__Push__State, workspace) -> Schema__Push__State:
        directory = str(input.directory)
        sg_dir    = str(input.sg_dir)

        workspace.ensure_managers(sg_dir)
        workspace.progress('step', 'Checking for uncommitted changes')

        from sgit_ai.core.actions.status.Vault__Sync__Status import Vault__Sync__Status
        status_checker = Vault__Sync__Status(crypto=workspace.sync_client.crypto,
                                             api=workspace.sync_client.api)
        local_status   = status_checker.status(directory)
        is_clean       = local_status.get('clean', False)

        if not is_clean:
            raise RuntimeError(
                'Working directory has uncommitted changes. '
                'Commit your changes before pushing.'
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
            working_copy_clean    = True,
        )
        return out
