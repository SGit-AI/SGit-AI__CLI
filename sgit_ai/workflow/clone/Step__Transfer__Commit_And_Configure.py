"""Step 5 (transfer) — Commit imported files and store share_token in local config."""
import json
import os

from sgit_ai.safe_types.Safe_Str__Step_Name                  import Safe_Str__Step_Name
from sgit_ai.schemas.workflow.clone.Schema__Transfer__State  import Schema__Transfer__State
from sgit_ai.workflow.Step                                   import Step


class Step__Transfer__Commit_And_Configure(Step):
    name          = Safe_Str__Step_Name('transfer-commit-and-configure')
    input_schema  = Schema__Transfer__State
    output_schema = Schema__Transfer__State

    def execute(self, input: Schema__Transfer__State, workspace) -> Schema__Transfer__State:
        from sgit_ai.core.actions.commit.Vault__Sync__Commit import Vault__Sync__Commit
        from sgit_ai.storage.Vault__Storage                  import Vault__Storage

        directory = str(input.directory) if input.directory else ''
        token_str = str(input.token_str) if input.token_str else ''

        workspace.progress('step', 'Committing imported files')

        Vault__Sync__Commit(
            crypto = workspace.sync_client.crypto,
            api    = workspace.sync_client.api,
        ).commit(directory, message=f'Imported from vault://{token_str}')

        storage     = Vault__Storage()
        config_path = storage.local_config_path(directory)
        with open(config_path, 'r') as f:
            config_data = json.load(f)
        branch_id = config_data.get('my_branch_id', '')
        config_data['share_token'] = token_str
        with open(config_path, 'w') as f:
            json.dump(config_data, f, indent=2)
        storage.chmod_local_file(config_path)

        data                = input.json()
        data['branch_id']   = branch_id
        data['share_token'] = token_str
        return Schema__Transfer__State.from_json(data)
