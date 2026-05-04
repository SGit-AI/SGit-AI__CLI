"""Vault__Sync__Admin — thin delegation shell (Brief 22 — E5-7b).

Implementations live in the three focused sub-classes:
  Vault__Sync__Branch_Ops  — merge_abort, branches, remote_*
  Vault__Sync__GC_Ops      — gc_drain, create_change_pack
  Vault__Sync__Lifecycle   — delete_on_remote, rekey_*, probe_token, uninit, restore_from_backup
"""
from   sgit_ai.core.Vault__Sync__Base       import Vault__Sync__Base
from   sgit_ai.sync.Vault__Sync__Branch_Ops import Vault__Sync__Branch_Ops
from   sgit_ai.sync.Vault__Sync__GC_Ops     import Vault__Sync__GC_Ops
from   sgit_ai.core.actions.lifecycle.Vault__Sync__Lifecycle  import Vault__Sync__Lifecycle


class Vault__Sync__Admin(Vault__Sync__Base):

    def _branch_ops(self) -> Vault__Sync__Branch_Ops:
        return Vault__Sync__Branch_Ops(crypto=self.crypto, api=self.api)

    def _gc_ops(self) -> Vault__Sync__GC_Ops:
        return Vault__Sync__GC_Ops(crypto=self.crypto, api=self.api)

    def _lifecycle(self) -> Vault__Sync__Lifecycle:
        return Vault__Sync__Lifecycle(crypto=self.crypto, api=self.api)

    def merge_abort(self, directory: str) -> dict:
        return self._branch_ops().merge_abort(directory)

    def branches(self, directory: str) -> dict:
        return self._branch_ops().branches(directory)

    def gc_drain(self, directory: str) -> dict:
        return self._gc_ops().gc_drain(directory)

    def create_change_pack(self, directory: str, files: dict) -> dict:
        return self._gc_ops().create_change_pack(directory, files)

    def remote_add(self, directory: str, name: str, url: str, vault_id: str) -> dict:
        return self._branch_ops().remote_add(directory, name, url, vault_id)

    def remote_remove(self, directory: str, name: str) -> dict:
        return self._branch_ops().remote_remove(directory, name)

    def remote_list(self, directory: str) -> dict:
        return self._branch_ops().remote_list(directory)

    def delete_on_remote(self, directory: str) -> dict:
        return self._lifecycle().delete_on_remote(directory)

    def rekey_check(self, directory: str) -> dict:
        return self._lifecycle().rekey_check(directory)

    def rekey_wipe(self, directory: str) -> dict:
        return self._lifecycle().rekey_wipe(directory)

    def rekey_init(self, directory: str, new_vault_key: str = None) -> dict:
        return self._lifecycle().rekey_init(directory, new_vault_key)

    def rekey_commit(self, directory: str) -> dict:
        return self._lifecycle().rekey_commit(directory)

    def rekey(self, directory: str, new_vault_key: str = None) -> dict:
        return self._lifecycle().rekey(directory, new_vault_key)

    def probe_token(self, token_str: str) -> dict:
        return self._lifecycle().probe_token(token_str)

    def uninit(self, directory: str) -> dict:
        return self._lifecycle().uninit(directory)

    def restore_from_backup(self, zip_path: str, directory: str) -> dict:
        return self._lifecycle().restore_from_backup(zip_path, directory)
