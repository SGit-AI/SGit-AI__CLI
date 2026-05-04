"""Vault__Sync__GC_Ops — garbage collection and change pack operations (Brief 22 — E5-7b)."""
from   sgit_ai.core.actions.gc.Vault__Change_Pack import Vault__Change_Pack
from   sgit_ai.core.actions.gc.Vault__GC          import Vault__GC
from   sgit_ai.storage.Vault__Storage     import Vault__Storage
from   sgit_ai.core.Vault__Sync__Base  import Vault__Sync__Base


class Vault__Sync__GC_Ops(Vault__Sync__Base):

    def gc_drain(self, directory: str) -> dict:
        """Drain all pending change packs into the object store."""
        vault_key  = self._read_vault_key(directory)
        keys       = self.crypto.derive_keys_from_vault_key(vault_key)
        read_key   = keys['read_key_bytes']

        storage         = Vault__Storage()
        local_config    = self._read_local_config(directory, storage)
        clone_branch_id = str(local_config.my_branch_id)

        gc = Vault__GC(crypto=self.crypto, storage=storage)
        return gc.drain_pending(directory, read_key, clone_branch_id,
                                branch_index_file_id=keys['branch_index_file_id'])

    def create_change_pack(self, directory: str, files: dict) -> dict:
        """Create a change pack in bare/pending/ for later integration."""
        vault_key  = self._read_vault_key(directory)
        keys       = self.crypto.derive_keys_from_vault_key(vault_key)
        read_key   = keys['read_key_bytes']

        storage         = Vault__Storage()
        local_config    = self._read_local_config(directory, storage)
        clone_branch_id = str(local_config.my_branch_id)

        change_pack = Vault__Change_Pack(crypto=self.crypto, storage=storage)
        return change_pack.create_change_pack(directory, read_key, files, clone_branch_id)
