"""Step 6 — Verify that the target vault is readable and head ref is present."""
import os

from sgit_ai.safe_types.Safe_Str__Step_Name  import Safe_Str__Step_Name
from sgit_ai.schemas.workflow.move.Schema__Move__State import Schema__Move__State
from sgit_ai.workflow.Step                   import Step


class Step__Move__Verify_Target(Step):
    name          = Safe_Str__Step_Name('verify-target')
    input_schema  = Schema__Move__State
    output_schema = Schema__Move__State

    def execute(self, input: Schema__Move__State, workspace) -> Schema__Move__State:
        from sgit_ai.crypto.Vault__Crypto  import Vault__Crypto
        from sgit_ai.network.api.Vault__API import Vault__API

        if input.dry_run:
            state_dict = input.json()
            state_dict['verify_completed'] = True
            return Schema__Move__State.from_json(state_dict)

        new_sg_dir    = str(input.temp_vault_dir)
        new_vault_key = str(input.new_vault_key)
        target_api_url = str(input.target_api_url) if input.target_api_url else None
        old_api_url    = str(input.old_api_url) if input.old_api_url else None
        effective_url  = target_api_url or old_api_url

        crypto  = Vault__Crypto()
        keys    = crypto.derive_keys_from_vault_key(new_vault_key)
        vault_id  = keys['vault_id']
        read_key  = keys['read_key_bytes']
        ref_id    = keys.get('ref_file_id', '')

        api = Vault__API(base_url=effective_url) if effective_url else Vault__API()

        if ref_id:
            try:
                import json as _json
                remote_ref_data = api.read(vault_id, f'bare/refs/{ref_id}')
                plaintext  = crypto.decrypt(read_key, remote_ref_data)
                commit_id  = _json.loads(plaintext).get('commit_id', '')
                if not commit_id:
                    raise RuntimeError(f'Verify: head ref {ref_id} decrypts to empty on target')
            except RuntimeError as e:
                if 'Not found' in str(e) or 'not_found' in str(e):
                    raise RuntimeError(
                        f'Verify failed: head ref not found on target server for vault {vault_id}. '
                        f'The push may have been incomplete.'
                    )
                raise

        state_dict = input.json()
        state_dict['verify_completed'] = True
        return Schema__Move__State.from_json(state_dict)
