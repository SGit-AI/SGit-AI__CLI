"""Vault__Attach — bind a key to an existing .sg_vault/bare checkout (P9).

The one missing command in the pipeline story (decision 14): a fresh
`git clone` of a one-repo vault has bare/ but no local/, and until now no
shipped command could open it — clone-headless refuses inside a vault and
status errors on the missing key. Attach writes local/ against the EXISTING
store.

Rules (tabletop 11, F6):
  - Validate FIRST: the key's derived named-ref file id must exist in
    bare/refs before anything is written. A wrong key writes NOTHING.
  - Mode-exclusive: a read-only attach removes vault_key; a read-write
    attach removes clone_mode.json — the shipped clone-mode guard refuses
    mixed state, correctly.
  - clone_mode.json is written Schema__Clone_Mode-exact.
"""
import json
import os

from sgit_ai.core.Vault__Sync__Base               import Vault__Sync__Base
from sgit_ai.safe_types.Enum__Clone_Mode          import Enum__Clone_Mode
from sgit_ai.safe_types.Enum__Local_Config_Mode   import Enum__Local_Config_Mode
from sgit_ai.schemas.Schema__Clone_Mode           import Schema__Clone_Mode
from sgit_ai.schemas.Schema__Local_Config         import Schema__Local_Config
from sgit_ai.storage.Vault__Storage               import Vault__Storage

DEFAULT_BRANCH_NAME = 'current'


class Vault__Attach(Vault__Sync__Base):

    def attach(self, directory: str, vault_key: str = None,
               read_key: str = None, vault_id: str = None) -> dict:
        """Bind a credential to directory's existing bare/ store.

        vault_key                  -> read-write attach (local/vault_key)
        read_key + vault_id        -> read-only attach (clone_mode.json)
        Returns {mode, vault_id, ref_file_id}; raises with 'Nothing written.'
        when the derived ref is absent from bare/refs (wrong key).
        """
        storage  = Vault__Storage()
        sg_dir   = storage.sg_vault_dir(directory)
        refs_dir = os.path.join(sg_dir, 'bare', 'refs')
        if not os.path.isdir(refs_dir):
            raise RuntimeError(f'{sg_dir} has no bare/refs — not a vault checkout. '
                               f'Nothing written.')

        if vault_key:
            keys = self.crypto.derive_keys_from_vault_key(vault_key.strip())
            mode = 'read-write'
        elif read_key and vault_id:
            keys = self.crypto.import_read_key(read_key.strip(), vault_id.strip())
            mode = 'read-only'
        else:
            raise ValueError('need --vault-key, or --read-key with --vault-id. '
                             'Nothing written.')

        ref_file_id = str(keys['ref_file_id'])
        if not os.path.isfile(os.path.join(refs_dir, ref_file_id)):    # validate FIRST
            raise RuntimeError(f'derived ref {ref_file_id} not found in bare/refs — '
                               f'wrong key for this store. Nothing written.')

        local_dir = storage.local_dir(directory)
        os.makedirs(local_dir, exist_ok=True)
        # Mode-exclusive: remove the OTHER mode's artifacts (F6a) — the shipped
        # clone-mode guard otherwise refuses to open the vault.
        for stale in ('clone_mode.json', 'vault_key'):
            stale_path = os.path.join(local_dir, stale)
            if os.path.isfile(stale_path):
                os.remove(stale_path)

        if mode == 'read-write':
            vault_key_path = storage.vault_key_path(directory)
            with open(vault_key_path, 'w') as f:
                f.write(self.crypto.format_vault_key(vault_key.strip()))
            storage.chmod_local_file(vault_key_path)
            config = Schema__Local_Config(my_branch_id=None, mode=None, sparse=False)
        else:
            clone_mode      = Schema__Clone_Mode(mode        = Enum__Clone_Mode.READ_ONLY,
                                                 vault_id    = str(keys['vault_id']),
                                                 read_key    = str(keys['read_key']),
                                                 branch_name = DEFAULT_BRANCH_NAME)
            clone_mode_path = storage.clone_mode_path(directory)
            with open(clone_mode_path, 'w') as f:
                json.dump(clone_mode.json(), f, indent=2)              # schema-exact (F6b)
            storage.chmod_local_file(clone_mode_path)
            config = Schema__Local_Config(my_branch_id=None,
                                          mode=Enum__Local_Config_Mode.READ_ONLY, sparse=False)

        config_path = storage.local_config_path(directory)
        with open(config_path, 'w') as f:
            json.dump(config.json(), f, indent=2)
        storage.chmod_local_file(config_path)

        return dict(mode=mode, vault_id=str(keys['vault_id']), ref_file_id=ref_file_id)
