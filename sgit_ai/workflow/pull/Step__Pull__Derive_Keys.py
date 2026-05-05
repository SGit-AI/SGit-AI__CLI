"""Step 1 — Derive cryptographic keys from vault_key stored in local config."""
import os

from sgit_ai.safe_types.Safe_Str__Step_Name              import Safe_Str__Step_Name
from sgit_ai.safe_types.Safe_Str__File_Path              import Safe_Str__File_Path
from sgit_ai.safe_types.Safe_Str__Vault_Id               import Safe_Str__Vault_Id
from sgit_ai.safe_types.Safe_Str__Index_Id               import Safe_Str__Index_Id
from sgit_ai.safe_types.Safe_Str__Read_Key               import Safe_Str__Read_Key
from sgit_ai.safe_types.Safe_Str__Write_Key              import Safe_Str__Write_Key
from sgit_ai.schemas.workflow.pull.Schema__Pull__State   import Schema__Pull__State
from sgit_ai.workflow.Step                               import Step


class Step__Pull__Derive_Keys(Step):
    name          = Safe_Str__Step_Name('derive-keys')
    input_schema  = Schema__Pull__State
    output_schema = Schema__Pull__State

    def execute(self, input: Schema__Pull__State, workspace) -> Schema__Pull__State:
        directory = str(input.directory)
        workspace.progress('step', 'Deriving vault keys')

        from sgit_ai.storage.Vault__Storage import Vault__Storage, SG_VAULT_DIR
        sg_dir    = os.path.join(directory, SG_VAULT_DIR)
        vault_key = workspace.sync_client._read_vault_key(directory)
        keys      = workspace.sync_client._derive_keys_from_stored_key(vault_key)

        return Schema__Pull__State(
            vault_key             = input.vault_key,
            directory             = input.directory,
            sg_dir                = Safe_Str__File_Path(sg_dir),
            vault_id              = Safe_Str__Vault_Id(keys['vault_id']),
            branch_index_file_id  = Safe_Str__Index_Id(keys['branch_index_file_id']),
            read_key_hex          = Safe_Str__Read_Key(keys['read_key']),
        )
