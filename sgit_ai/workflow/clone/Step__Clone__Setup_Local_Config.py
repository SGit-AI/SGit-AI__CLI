"""Step 10 — Write local config files (vault_key, config.json)."""
import json

from sgit_ai.safe_types.Safe_Str__Step_Name               import Safe_Str__Step_Name
from sgit_ai.schemas.workflow.clone.Schema__Clone__State  import Schema__Clone__State
from sgit_ai.workflow.Step                                import Step


class Step__Clone__Setup_Local_Config(Step):
    name          = Safe_Str__Step_Name('setup-local-config')
    input_schema  = Schema__Clone__State
    output_schema = Schema__Clone__State

    def execute(self, input: Schema__Clone__State, workspace) -> Schema__Clone__State:
        from sgit_ai.schemas.Schema__Local_Config       import Schema__Local_Config

        sg_dir    = str(input.sg_dir)
        directory = str(input.directory)
        vault_key = str(input.vault_key)

        workspace.ensure_managers(sg_dir)
        workspace.progress('step', 'Setting up local config')

        local_config = Schema__Local_Config(
            my_branch_id       = str(input.clone_branch_id),
            mode               = None,
            sparse             = input.sparse,
            scope_paths        = [str(p) for p in (input.scope_paths        or [])],
            shallow_boundaries = [str(b) for b in (input.shallow_boundaries or [])],
            last_remote_head   = str(input.named_commit_id) if input.named_commit_id else None,
        )
        config_path = workspace.storage.local_config_path(directory)
        workspace.storage.write_local_config(directory, local_config.json())

        vault_key_path = workspace.storage.vault_key_path(directory)
        workspace.storage.write_private(vault_key_path, workspace.sync_client.crypto.format_vault_key(vault_key))   # sgit_private_vault_… on disk

        return Schema__Clone__State.from_json(input.json())
