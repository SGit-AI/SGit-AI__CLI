"""Step 2 — Load branch index and read current clone branch commit ID."""
from sgit_ai.safe_types.Safe_Str__Step_Name               import Safe_Str__Step_Name
from sgit_ai.safe_types.Safe_Str__Commit_Id               import Safe_Str__Commit_Id
from sgit_ai.safe_types.Safe_Str__Ref_Id                  import Safe_Str__Ref_Id
from sgit_ai.schemas.workflow.fetch.Schema__Fetch__State  import Schema__Fetch__State
from sgit_ai.workflow.Step                                import Step


class Step__Fetch__Load_Branch_Info(Step):
    name          = Safe_Str__Step_Name('load-branch-info')
    input_schema  = Schema__Fetch__State
    output_schema = Schema__Fetch__State

    def execute(self, input: Schema__Fetch__State, workspace) -> Schema__Fetch__State:
        sg_dir   = str(input.sg_dir)
        read_key = bytes.fromhex(str(input.read_key_hex))

        workspace.ensure_managers(sg_dir)
        workspace.progress('step', 'Loading branch info')

        from sgit_ai.storage.Vault__Storage import Vault__Storage
        storage         = Vault__Storage()
        local_config    = workspace.sync_client._read_local_config(str(input.directory), storage)
        clone_branch_id = str(local_config.my_branch_id)

        branch_index = workspace.branch_manager.load_branch_index(
            str(input.directory), str(input.branch_index_file_id), read_key
        )

        clone_meta = workspace.branch_manager.get_branch_by_id(branch_index, clone_branch_id)
        if not clone_meta:
            raise RuntimeError(f'Clone branch not found: {clone_branch_id}')

        named_meta = workspace.branch_manager.get_branch_by_name(branch_index, 'current')
        if not named_meta:
            raise RuntimeError('Named branch "current" not found')

        clone_commit_id = workspace.ref_manager.read_ref(str(clone_meta.head_ref_id), read_key) or ''

        return Schema__Fetch__State(
            vault_key             = input.vault_key,
            directory             = input.directory,
            sg_dir                = input.sg_dir,
            vault_id              = input.vault_id,
            branch_index_file_id  = input.branch_index_file_id,
            read_key_hex          = input.read_key_hex,
            clone_commit_id       = Safe_Str__Commit_Id(clone_commit_id) if clone_commit_id else None,
            named_ref_id          = Safe_Str__Ref_Id(str(named_meta.head_ref_id)),
        )
