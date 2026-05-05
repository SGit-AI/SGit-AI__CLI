"""Step 3 — Load branch info and inventory local-only objects."""
from sgit_ai.safe_types.Safe_Str__Step_Name              import Safe_Str__Step_Name
from sgit_ai.safe_types.Safe_Str__Branch_Id              import Safe_Str__Branch_Id
from sgit_ai.safe_types.Safe_Str__Ref_Id                 import Safe_Str__Ref_Id
from sgit_ai.safe_types.Safe_Str__Commit_Id              import Safe_Str__Commit_Id
from sgit_ai.safe_types.Safe_UInt__File_Count            import Safe_UInt__File_Count
from sgit_ai.schemas.workflow.push.Schema__Push__State   import Schema__Push__State
from sgit_ai.workflow.Step                               import Step


class Step__Push__Local_Inventory(Step):
    name          = Safe_Str__Step_Name('local-inventory')
    input_schema  = Schema__Push__State
    output_schema = Schema__Push__State

    def execute(self, input: Schema__Push__State, workspace) -> Schema__Push__State:
        sg_dir   = str(input.sg_dir)
        read_key = bytes.fromhex(str(input.read_key_hex))

        workspace.ensure_managers(sg_dir)
        workspace.progress('step', 'Inventorying local changes')

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
        named_commit_id = workspace.ref_manager.read_ref(str(named_meta.head_ref_id), read_key) or ''

        n_local_only = 0
        if clone_commit_id and named_commit_id != clone_commit_id:
            try:
                clone_commit  = workspace.vc.load_commit(clone_commit_id, read_key)
                clone_tree    = workspace.sub_tree.flatten(str(clone_commit.tree_id), read_key)
                named_tree    = {}
                if named_commit_id:
                    named_commit = workspace.vc.load_commit(named_commit_id, read_key)
                    named_tree   = workspace.sub_tree.flatten(str(named_commit.tree_id), read_key)
                n_local_only = sum(
                    1 for p, v in clone_tree.items()
                    if p not in named_tree or named_tree[p].get('blob_id') != v.get('blob_id')
                )
            except Exception:
                n_local_only = 0

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
            clone_branch_id       = Safe_Str__Branch_Id(clone_branch_id),
            clone_ref_id          = Safe_Str__Ref_Id(str(clone_meta.head_ref_id)),
            named_ref_id          = Safe_Str__Ref_Id(str(named_meta.head_ref_id)),
            clone_commit_id       = Safe_Str__Commit_Id(clone_commit_id) if clone_commit_id else None,
            named_commit_id       = Safe_Str__Commit_Id(named_commit_id) if named_commit_id else None,
            n_local_only_objects  = Safe_UInt__File_Count(n_local_only),
        )
        return out
