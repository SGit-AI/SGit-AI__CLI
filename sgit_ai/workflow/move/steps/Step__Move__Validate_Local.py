"""Step 1 — Validate local vault: clean working copy + basic integrity."""
import json
import os

from sgit_ai.safe_types.Safe_Str__Base_URL       import Safe_Str__Base_URL
from sgit_ai.safe_types.Safe_Str__Step_Name      import Safe_Str__Step_Name
from sgit_ai.safe_types.Safe_Str__Vault_Id       import Safe_Str__Vault_Id
from sgit_ai.safe_types.Safe_UInt__Vault_Version import Safe_UInt__Vault_Version
from sgit_ai.schemas.workflow.move.Schema__Move__State import Schema__Move__State
from sgit_ai.workflow.Step                       import Step


class Step__Move__Validate_Local(Step):
    name          = Safe_Str__Step_Name('validate-local')
    input_schema  = Schema__Move__State
    output_schema = Schema__Move__State

    def execute(self, input: Schema__Move__State, workspace) -> Schema__Move__State:
        from sgit_ai.core.actions.status.Vault__Sync__Status import Vault__Sync__Status
        from sgit_ai.crypto.Vault__Crypto                    import Vault__Crypto
        from sgit_ai.storage.Vault__Storage                  import Vault__Storage
        from sgit_ai.network.api.Vault__API                  import DEFAULT_BASE_URL

        directory = str(input.directory)
        storage   = Vault__Storage()
        sg_dir    = storage.sg_vault_dir(directory)
        if not os.path.isdir(sg_dir):
            raise RuntimeError(f'Not a vault: {directory}')

        if not input.dry_run:
            crypto = Vault__Crypto()
            status = Vault__Sync__Status(crypto=crypto).status(directory)
            if not status.get('clean', True):
                raise RuntimeError(
                    'Vault has uncommitted changes — commit or stash before running vault move.'
                )

        local_config_path = storage.local_config_path(directory)
        vault_id       = ''
        key_generation = 1
        api_url        = DEFAULT_BASE_URL
        if os.path.isfile(local_config_path):
            with open(local_config_path) as f:
                cfg = json.load(f)
            vault_id       = cfg.get('vault_id', '') or ''
            key_generation = cfg.get('key_generation', 1) or 1
            api_url        = cfg.get('api_url', '') or DEFAULT_BASE_URL

        obj_count = 0
        data_dir  = storage.bare_data_dir(directory)
        if os.path.isdir(data_dir):
            obj_count = sum(1 for f in os.listdir(data_dir) if f.startswith('obj-cas-imm-'))

        return Schema__Move__State(
            directory      = input.directory,
            new_vault_key  = input.new_vault_key,
            target_api_url = input.target_api_url,
            reason         = input.reason,
            dry_run        = input.dry_run,
            old_vault_id   = Safe_Str__Vault_Id(vault_id) if vault_id else None,
            old_api_url    = Safe_Str__Base_URL(api_url),
            object_count   = Safe_UInt__Vault_Version(obj_count),
        )
