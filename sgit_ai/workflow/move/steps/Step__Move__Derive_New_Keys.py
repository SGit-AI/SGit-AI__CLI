from sgit_ai.safe_types.Safe_Str__Step_Name      import Safe_Str__Step_Name
from sgit_ai.safe_types.Safe_Str__Vault_Id       import Safe_Str__Vault_Id
from sgit_ai.safe_types.Safe_Str__Vault_Key      import Safe_Str__Vault_Key
from sgit_ai.safe_types.Safe_UInt__Vault_Version import Safe_UInt__Vault_Version
from sgit_ai.schemas.workflow.move.Schema__Move__State import Schema__Move__State
from sgit_ai.workflow.Step                       import Step


class Step__Move__Derive_New_Keys(Step):
    name          = Safe_Str__Step_Name('derive-new-keys')
    input_schema  = Schema__Move__State
    output_schema = Schema__Move__State

    def execute(self, input: Schema__Move__State, workspace) -> Schema__Move__State:
        import secrets
        import string
        from sgit_ai.crypto.Vault__Crypto import Vault__Crypto

        if input.new_vault_key and str(input.new_vault_key):
            new_vault_key = str(input.new_vault_key)
        else:
            alphabet      = string.ascii_lowercase + string.digits
            passphrase    = ''.join(secrets.choice(alphabet) for _ in range(24))
            vault_id_part = ''.join(secrets.choice(alphabet) for _ in range(8))
            new_vault_key = f'{passphrase}:{vault_id_part}'

        crypto    = Vault__Crypto()
        keys      = crypto.derive_keys_from_vault_key(new_vault_key)
        new_vault_id = keys['vault_id']

        old_gen      = int(input.key_generation) if input.key_generation else 0
        key_generation = old_gen + 1

        return Schema__Move__State(
            directory      = input.directory,
            new_vault_key  = Safe_Str__Vault_Key(new_vault_key),
            target_api_url = input.target_api_url,
            reason         = input.reason,
            dry_run        = input.dry_run,
            old_vault_id   = input.old_vault_id,
            old_api_url    = input.old_api_url,
            object_count   = input.object_count,
            new_vault_id   = Safe_Str__Vault_Id(new_vault_id),
            key_generation = Safe_UInt__Vault_Version(key_generation),
        )
