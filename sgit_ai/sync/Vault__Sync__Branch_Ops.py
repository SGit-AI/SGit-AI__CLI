"""Vault__Sync__Branch_Ops — branch listing and remote management (Brief 22 — E5-7b)."""
import json
import os
from   sgit_ai.objects.Vault__Commit      import Vault__Commit
from   sgit_ai.sync.Vault__Merge          import Vault__Merge
from   sgit_ai.sync.Vault__Remote_Manager import Vault__Remote_Manager
from   sgit_ai.sync.Vault__Storage        import Vault__Storage
from   sgit_ai.sync.Vault__Sub_Tree       import Vault__Sub_Tree
from   sgit_ai.sync.Vault__Sync__Base     import Vault__Sync__Base


class Vault__Sync__Branch_Ops(Vault__Sync__Base):

    def merge_abort(self, directory: str) -> dict:
        """Abort an in-progress merge by restoring the pre-merge state."""
        c = self._init_components(directory)
        read_key    = c.read_key
        storage     = c.storage
        pki         = c.pki
        obj_store   = c.obj_store
        ref_manager = c.ref_manager
        merger      = Vault__Merge(crypto=self.crypto)

        merge_state_path = os.path.join(storage.local_dir(directory), 'merge_state.json')
        if not os.path.isfile(merge_state_path):
            raise RuntimeError('No merge in progress')

        with open(merge_state_path, 'r') as f:
            merge_state = json.load(f)

        clone_commit_id = merge_state['clone_commit_id']

        vault_commit = Vault__Commit(crypto=self.crypto, pki=pki,
                                     object_store=obj_store, ref_manager=ref_manager)

        if clone_commit_id:
            ours_commit = vault_commit.load_commit(clone_commit_id, read_key)
            sub_tree    = Vault__Sub_Tree(crypto=self.crypto, obj_store=obj_store)
            sub_tree.checkout(directory, str(ours_commit.tree_id), read_key)

        removed = merger.remove_conflict_files(directory)
        os.remove(merge_state_path)

        return dict(status          = 'aborted',
                    restored_commit = clone_commit_id,
                    removed_files   = removed)

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
