"""Step 3 (headless) — Write local config only; no bare/ data directory created."""
import json
import os

from sgit_ai.safe_types.Safe_Str__Step_Name               import Safe_Str__Step_Name
from sgit_ai.schemas.workflow.clone.Schema__Clone__State  import Schema__Clone__State
from sgit_ai.workflow.Step                                import Step


class Step__Clone__Headless__Setup_Config(Step):
    """Write vault_key and config.json with no clone_branch_id (headless = read-only credentials)."""
    name          = Safe_Str__Step_Name('headless-setup-config')
    input_schema  = Schema__Clone__State
    output_schema = Schema__Clone__State

    def execute(self, input: Schema__Clone__State, workspace) -> Schema__Clone__State:
        from sgit_ai.schemas.Schema__Local_Config       import Schema__Local_Config
        from sgit_ai.storage.Vault__Storage             import Vault__Storage

        directory = str(input.directory)
        vault_key = str(input.vault_key)
        vault_id  = str(input.vault_id) if input.vault_id else ''

        os.makedirs(directory, exist_ok=True)

        storage = Vault__Storage()

        local_config = Schema__Local_Config(
            my_branch_id = '',
            mode         = None,
            sparse       = True,
        )

        local_dir   = storage.local_dir(directory)
        os.makedirs(local_dir, exist_ok=True)

        config_path = storage.local_config_path(directory)
        with open(config_path, 'w') as f:
            json.dump(local_config.json(), f, indent=2)
        storage.chmod_local_file(config_path)

        vault_key_path = storage.vault_key_path(directory)
        with open(vault_key_path, 'w') as f:
            f.write(workspace.sync_client.crypto.format_vault_key(vault_key))   # sgit_vk1_… on disk
        storage.chmod_local_file(vault_key_path)

        workspace.progress('step', 'Headless config written')
        return Schema__Clone__State.from_json(input.json())
