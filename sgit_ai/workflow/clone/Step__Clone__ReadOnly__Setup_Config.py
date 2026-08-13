"""Step 9 (read-only) — Write clone_mode.json AND config.json for a read-only clone.

Writes NO vault_key file (the user holds no passphrase) and NO clone-branch ref
(read-only clones have no clone branch). See architect contract §3 and guard
rails §8 #2/#3/#4.
"""
import json

from sgit_ai.safe_types.Safe_Str__Step_Name               import Safe_Str__Step_Name
from sgit_ai.schemas.workflow.clone.Schema__Clone__State  import Schema__Clone__State
from sgit_ai.workflow.Step                                import Step


class Step__Clone__ReadOnly__Setup_Config(Step):
    name          = Safe_Str__Step_Name('readonly-setup-config')
    input_schema  = Schema__Clone__State
    output_schema = Schema__Clone__State

    # The named branch a read-only clone tracks. The clone pipeline resolves
    # the named branch via get_branch_by_name(branch_index, 'current') in
    # Step__Clone__Download_Index, so the recorded branch_name matches (Q7).
    DEFAULT_BRANCH_NAME = 'current'

    def execute(self, input: Schema__Clone__State, workspace) -> Schema__Clone__State:
        from sgit_ai.safe_types.Enum__Clone_Mode        import Enum__Clone_Mode
        from sgit_ai.safe_types.Enum__Local_Config_Mode import Enum__Local_Config_Mode
        from sgit_ai.schemas.Schema__Clone_Mode         import Schema__Clone_Mode
        from sgit_ai.schemas.Schema__Local_Config       import Schema__Local_Config

        directory    = str(input.directory)
        vault_id     = str(input.vault_id)     if input.vault_id     else ''
        read_key_hex = str(input.read_key_hex) if input.read_key_hex else ''

        workspace.progress('step', 'Setting up read-only local config')

        # clone_mode.json — drives key derivation; records the tracked branch name (Q7)
        clone_mode      = Schema__Clone_Mode(mode        = Enum__Clone_Mode.READ_ONLY,
                                             vault_id    = vault_id,
                                             read_key    = read_key_hex,
                                             branch_name = self.DEFAULT_BRANCH_NAME)
        clone_mode_path = workspace.storage.clone_mode_path(directory)
        with open(clone_mode_path, 'w') as f:
            json.dump(clone_mode.json(), f, indent=2)
        workspace.storage.chmod_local_file(clone_mode_path)

        # config.json — always written now (§3.3). my_branch_id stays None (no clone
        # branch, guard rail #3); mode=READ_ONLY; sparse carried through.
        local_config = Schema__Local_Config(my_branch_id = None,
                                            mode         = Enum__Local_Config_Mode.READ_ONLY,
                                            sparse       = input.sparse)
        config_path  = workspace.storage.local_config_path(directory)
        with open(config_path, 'w') as f:
            json.dump(local_config.json(), f, indent=2)
        workspace.storage.chmod_local_file(config_path)

        return Schema__Clone__State.from_json(input.json())
