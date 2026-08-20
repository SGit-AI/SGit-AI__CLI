"""Vault__Ignore__Apply — deliberately remove a now-ignored folder from the vault.

The escape hatch named by the decision-17 migration notice: tracked files under
an ignored directory are grandfathered by the tracked-wins rule, so the only
way to remove them is a deliberate act. This performs it as ONE visible commit
that drops the paths from the head tree while leaving the work tree untouched
(the files usually still belong on disk — .github/ workflows run from git, not
from the vault).
"""
import os
from   sgit_ai.storage.Vault__Commit    import Vault__Commit
from   sgit_ai.storage.Vault__Sub_Tree  import Vault__Sub_Tree
from   sgit_ai.core.Vault__Sync__Base   import Vault__Sync__Base
from   sgit_ai.core.Vault__Errors       import Vault__Read_Only_Error


class Vault__Ignore__Apply(Vault__Sync__Base):

    def apply(self, directory: str, dir_name: str) -> dict:
        """Drop every head-tracked path under dir_name in one commit.

        Returns {status, removed, commit_id, message}. The work tree is not
        touched: this is `git rm --cached -r` followed by a commit, not a
        delete.
        """
        dir_name = dir_name.strip('/')
        if not dir_name or '/' in dir_name or dir_name in ('.', '..'):
            raise ValueError(f'invalid folder name: {dir_name!r} — pass a single '
                             f'top-level folder name, e.g. .github')

        c = self._init_components(directory)
        if not c.write_key:
            raise Vault__Read_Only_Error()

        local_config = self._read_local_config(directory, c.storage)
        branch_id    = str(local_config.my_branch_id)
        index_id     = c.branch_index_file_id
        if not index_id:
            raise RuntimeError('No branch index found — is this a v2 vault?')
        branch_index = c.branch_manager.load_branch_index(directory, index_id, c.read_key)
        branch_meta  = c.branch_manager.get_branch_by_id(branch_index, branch_id)
        if not branch_meta:
            raise RuntimeError(f'Branch not found: {branch_id}')

        ref_id    = str(branch_meta.head_ref_id)
        parent_id = c.ref_manager.read_ref(ref_id, c.read_key)
        if not parent_id:
            return dict(status='up_to_date', removed=[], commit_id=None,
                        message='Vault has no commits — nothing to remove')

        vault_commit = Vault__Commit(crypto=self.crypto, pki=c.pki,
                                     object_store=c.obj_store, ref_manager=c.ref_manager)
        old_commit   = vault_commit.load_commit(parent_id, c.read_key)
        sub_tree     = Vault__Sub_Tree(crypto=self.crypto, obj_store=c.obj_store)
        old_flat     = sub_tree.flatten(str(old_commit.tree_id), c.read_key)

        prefix  = dir_name + '/'
        removed = sorted(p for p in old_flat if p.startswith(prefix))
        if not removed:
            return dict(status='up_to_date', removed=[], commit_id=None,
                        message=f'No tracked files under {dir_name}/ — nothing to remove')

        new_flat     = {p: e for p, e in old_flat.items() if not p.startswith(prefix)}
        root_tree_id = sub_tree.build_from_flat(new_flat, c.read_key)

        signing_key = None
        try:
            signing_key = c.key_manager.load_private_key_locally(
                str(branch_meta.public_key_id), c.storage.local_dir(directory))
        except (FileNotFoundError, Exception):
            pass

        message   = (f'Remove {dir_name}/ from vault ({len(removed)} file(s)) — '
                     f'folder is ignored; work tree untouched')
        commit_id = vault_commit.create_commit(tree_id     = root_tree_id,
                                               read_key    = c.read_key,
                                               parent_ids  = [parent_id],
                                               message     = message,
                                               branch_id   = branch_id,
                                               signing_key = signing_key)
        c.ref_manager.write_ref(ref_id, commit_id, c.read_key)

        return dict(status='removed', removed=removed, commit_id=commit_id,
                    message=message)

    def tracked_under(self, directory: str, dir_name: str) -> list:
        """Head-tracked paths under dir_name, without changing anything."""
        dir_name = dir_name.strip('/')
        try:
            c            = self._init_components(directory)
            local_config = self._read_local_config(directory, c.storage)
            branch_index = c.branch_manager.load_branch_index(directory, c.branch_index_file_id, c.read_key)
            branch_meta  = self._resolve_working_branch(local_config, branch_index, c.branch_manager,
                                                        self._tracked_branch_name(directory))
            if not branch_meta:
                return []
            parent_id = c.ref_manager.read_ref(str(branch_meta.head_ref_id), c.read_key)
            if not parent_id:
                return []
            vault_commit = Vault__Commit(crypto=self.crypto, pki=c.pki,
                                         object_store=c.obj_store, ref_manager=c.ref_manager)
            old_commit   = vault_commit.load_commit(parent_id, c.read_key)
            sub_tree     = Vault__Sub_Tree(crypto=self.crypto, obj_store=c.obj_store)
            old_flat     = sub_tree.flatten(str(old_commit.tree_id), c.read_key)
            return sorted(p for p in old_flat if p.startswith(dir_name + '/'))
        except Exception:
            return []
