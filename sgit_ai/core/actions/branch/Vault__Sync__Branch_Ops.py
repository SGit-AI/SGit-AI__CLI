import os
from   sgit_ai.core.Vault__Remote_Manager import Vault__Remote_Manager
from   sgit_ai.storage.Vault__Storage     import Vault__Storage
from   sgit_ai.core.Vault__Sync__Base     import Vault__Sync__Base


class Vault__Sync__Branch_Ops(Vault__Sync__Base):

    def merge_abort(self, directory: str) -> dict:
        from sgit_ai.core.actions.merge.Vault__Merge__Abort import Vault__Merge__Abort
        return Vault__Merge__Abort(crypto=self.crypto, api=self.api).abort(directory)

    def branches(self, directory: str) -> dict:
        """List all branches in the vault."""
        c = self._init_components(directory)
        read_key       = c.read_key
        storage        = c.storage
        ref_manager    = c.ref_manager
        branch_manager = c.branch_manager

        index_id = c.branch_index_file_id
        if not index_id:
            return dict(branches=[], my_branch_id='')

        branch_index = branch_manager.load_branch_index(directory, index_id, read_key)

        local_config = self._read_local_config(directory, storage)
        my_branch_id = str(local_config.my_branch_id)

        result = []
        for branch in branch_index.branches:
            head_commit_id = ref_manager.read_ref(str(branch.head_ref_id), read_key)
            result.append(dict(branch_id   = str(branch.branch_id),
                               name        = str(branch.name),
                               branch_type = str(branch.branch_type.value) if branch.branch_type else 'unknown',
                               head_ref_id = str(branch.head_ref_id),
                               head_commit = head_commit_id or '',
                               is_current  = str(branch.branch_id) == my_branch_id))

        return dict(branches=result, my_branch_id=my_branch_id)

    def remote_add(self, directory: str, name: str, url: str, vault_id: str) -> dict:
        """Add a named remote to the vault."""
        storage = Vault__Storage()
        manager = Vault__Remote_Manager(storage=storage)
        remote  = manager.add_remote(directory, name, url, vault_id)
        return dict(name=str(remote.name), url=str(remote.url), vault_id=str(remote.vault_id))

    def remote_remove(self, directory: str, name: str) -> dict:
        """Remove a named remote from the vault."""
        storage = Vault__Storage()
        manager = Vault__Remote_Manager(storage=storage)
        removed = manager.remove_remote(directory, name)
        if not removed:
            raise RuntimeError(f'Remote not found: {name}')
        return dict(removed=name)

    def remote_list(self, directory: str) -> dict:
        """List all configured remotes."""
        storage = Vault__Storage()
        manager = Vault__Remote_Manager(storage=storage)
        remotes = manager.list_remotes(directory)
        return dict(remotes=remotes)
