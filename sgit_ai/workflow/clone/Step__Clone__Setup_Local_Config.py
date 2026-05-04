"""Step 10 — Write local config files (vault_key, config.json)."""
import json
import os

from sgit_ai.safe_types.Safe_Str__Step_Name               import Safe_Str__Step_Name
from sgit_ai.schemas.workflow.clone.Schema__Clone__State  import Schema__Clone__State
from sgit_ai.workflow.Step                                import Step


class Step__Clone__Setup_Local_Config(Step):
    name          = Safe_Str__Step_Name('setup-local-config')
    input_schema  = Schema__Clone__State
    output_schema = Schema__Clone__State

    def execute(self, input: Schema__Clone__State, workspace) -> Schema__Clone__State:
        from sgit_ai.safe_types.Enum__Local_Config_Mode import Enum__Local_Config_Mode
        from sgit_ai.schemas.Schema__Local_Config       import Schema__Local_Config
        from sgit_ai.network.transfer.Simple_Token              import Simple_Token

        sg_dir    = str(input.sg_dir)
        directory = str(input.directory)
        vault_key = str(input.vault_key)

        workspace.ensure_managers(sg_dir)
        workspace.progress('step', 'Setting up local config')

        _is_simple_token = Simple_Token.is_simple_token(vault_key)
        local_config = Schema__Local_Config(
            my_branch_id = str(input.clone_branch_id),
            mode         = Enum__Local_Config_Mode.SIMPLE_TOKEN if _is_simple_token else None,
            edit_token   = vault_key if _is_simple_token else None,
            sparse       = input.sparse,
        )
        config_path = workspace.storage.local_config_path(directory)
        with open(config_path, 'w') as f:
            json.dump(local_config.json(), f, indent=2)
        workspace.storage.chmod_local_file(config_path)

        vault_key_path = workspace.storage.vault_key_path(directory)
        with open(vault_key_path, 'w') as f:
            f.write(vault_key)
        workspace.storage.chmod_local_file(vault_key_path)

        return Schema__Clone__State.from_json(input.json())
