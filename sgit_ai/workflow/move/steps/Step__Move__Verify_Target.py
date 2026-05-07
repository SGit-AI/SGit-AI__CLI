"""Step 6 — Verify that the target vault is readable and head ref is present."""
import json
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
        from sgit_ai.safe_types.Enum__Branch_Type import Enum__Branch_Type

        if input.dry_run:
            state_dict = input.json()
            state_dict['verify_completed'] = True
            return Schema__Move__State.from_json(state_dict)

        new_vault_key  = str(input.new_vault_key)
        target_api_url = str(input.target_api_url) if input.target_api_url else None
        old_api_url    = str(input.old_api_url) if input.old_api_url else None
        effective_url  = target_api_url or old_api_url
        new_sg_dir     = str(input.temp_vault_dir)

        crypto   = Vault__Crypto()
        keys     = crypto.derive_keys_from_vault_key(new_vault_key)
        vault_id = keys['vault_id']
        read_key = keys['read_key_bytes']
        index_id = keys.get('branch_index_file_id', '')

        if getattr(workspace, 'api', None) is not None:
            api = workspace.api
        elif effective_url:
            api = Vault__API(base_url=effective_url)
        else:
            api = Vault__API()

        if not index_id:
            state_dict = input.json()
            state_dict['verify_completed'] = True
            return Schema__Move__State.from_json(state_dict)

        try:
            raw_index = api.read(vault_id, f'bare/indexes/{index_id}')
        except RuntimeError as e:
            raise RuntimeError(
                f'Verify failed: branch index not found on target for vault {vault_id}. '
                f'The push may have been incomplete. ({e})'
            )

        try:
            index_data = json.loads(crypto.decrypt(read_key, raw_index))
        except Exception as e:
            raise RuntimeError(f'Verify failed: cannot decrypt branch index: {e}')

        named_ref_id = ''
        for branch in index_data.get('branches', []):
            if branch.get('branch_type') == str(Enum__Branch_Type.NAMED) or \
               branch.get('branch_type') == 'named':
                named_ref_id = branch.get('head_ref_id', '')
                break

        if named_ref_id:
            try:
                raw_ref   = api.read(vault_id, f'bare/refs/{named_ref_id}')
                plaintext = json.loads(crypto.decrypt(read_key, raw_ref))
                commit_id = plaintext.get('commit_id', '')
                if not commit_id:
                    raise RuntimeError(f'Verify: named branch ref decrypts to empty')
            except RuntimeError as e:
                if 'Not found' in str(e):
                    raise RuntimeError(
                        f'Verify failed: named branch ref {named_ref_id} not found on target. '
                        f'The push may have been incomplete.'
                    )
                raise

        state_dict = input.json()
        state_dict['verify_completed'] = True
        return Schema__Move__State.from_json(state_dict)
