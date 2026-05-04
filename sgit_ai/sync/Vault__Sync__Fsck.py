"""Vault__Sync__Fsck — vault integrity verification and repair (Brief 22 — E5-9)."""
import os
from   sgit_ai.crypto.PKI__Crypto        import PKI__Crypto
from   sgit_ai.storage.Vault__Commit     import Vault__Commit
from   sgit_ai.storage.Vault__Storage       import SG_VAULT_DIR
from   sgit_ai.core.Vault__Sync__Base    import Vault__Sync__Base


class Vault__Sync__Fsck(Vault__Sync__Base):

    def fsck(self, directory: str, repair: bool = False, on_progress: callable = None) -> dict:
        """Verify vault integrity and optionally repair by downloading missing objects."""
        _p     = on_progress or (lambda *a, **k: None)
        result = dict(ok=True, missing=[], corrupt=[], repaired=[], errors=[])

        sg_dir = os.path.join(directory, SG_VAULT_DIR)
        if not os.path.isdir(sg_dir):
            result['ok'] = False
            result['errors'].append(f'Not a vault: {directory} (no .sg_vault/ directory)')
            return result

        _p('step', 'Reading vault configuration')
        try:
            c = self._init_components(directory)
        except Exception as e:
            result['ok'] = False
            result['errors'].append(f'Cannot read vault config: {e}')
            return result

        read_key    = c.read_key
        obj_store   = c.obj_store
        ref_manager = c.ref_manager
        pki         = c.pki

        _p('step', 'Loading branch index')
        try:
            index_id     = c.branch_index_file_id
            branch_index = c.branch_manager.load_branch_index(directory, index_id, read_key)
            local_config = self._read_local_config(directory, c.storage)
            clone_meta   = c.branch_manager.get_branch_by_id(branch_index, str(local_config.my_branch_id))
            commit_id    = ref_manager.read_ref(str(clone_meta.head_ref_id), read_key) if clone_meta else None
        except Exception as e:
            result['ok'] = False
            result['errors'].append(f'Cannot read branch info: {e}')
            return result

        if not commit_id:
            _p('step', 'Empty vault — no commits to check')
            return result

        _p('step', 'Walking commit chain')
        vc      = Vault__Commit(crypto=self.crypto, pki=pki,
                                object_store=obj_store, ref_manager=ref_manager)
        visited = set()
        queue   = [commit_id]
        checked = 0

        while queue:
            oid = queue.pop(0)
            if not oid or oid in visited:
                continue
            visited.add(oid)
            checked += 1

            if not obj_store.exists(oid):
                result['missing'].append(oid)
                result['ok'] = False
                if repair:
                    if self._repair_object(oid, c.vault_id, c.sg_dir):
                        result['repaired'].append(oid)
                else:
                    continue

            if not obj_store.exists(oid):
                continue

            if not obj_store.verify_integrity(oid):
                result['corrupt'].append(oid)
                result['ok'] = False

            try:
                commit = vc.load_commit(oid, read_key)
            except Exception:
                result['errors'].append(f'Cannot load commit {oid}')
                result['ok'] = False
                continue

            tree_queue    = [str(commit.tree_id)] if commit.tree_id else []
            visited_trees = set()
            while tree_queue:
                tid = tree_queue.pop(0)
                if not tid or tid in visited_trees:
                    continue
                visited_trees.add(tid)

                if not obj_store.exists(tid):
                    result['missing'].append(tid)
                    result['ok'] = False
                    if repair:
                        if self._repair_object(tid, c.vault_id, c.sg_dir):
                            result['repaired'].append(tid)
                    if not obj_store.exists(tid):
                        continue

                if not obj_store.verify_integrity(tid):
                    result['corrupt'].append(tid)
                    result['ok'] = False

                try:
                    tree = vc.load_tree(tid, read_key)
                except Exception:
                    result['errors'].append(f'Cannot load tree {tid}')
                    result['ok'] = False
                    continue

                for entry in tree.entries:
                    blob_id = str(entry.blob_id) if entry.blob_id else None
                    if blob_id:
                        if not obj_store.exists(blob_id):
                            result['missing'].append(blob_id)
                            result['ok'] = False
                            if repair:
                                if self._repair_object(blob_id, c.vault_id, c.sg_dir):
                                    result['repaired'].append(blob_id)
                        elif not obj_store.verify_integrity(blob_id):
                            result['corrupt'].append(blob_id)
                            result['ok'] = False
                    sub_tree_id = str(entry.tree_id) if entry.tree_id else None
                    if sub_tree_id:
                        tree_queue.append(sub_tree_id)

            parents = list(commit.parents) if commit.parents else []
            for pid in parents:
                if str(pid) not in visited:
                    queue.append(str(pid))

        _p('step', f'Checked {checked} commits, {len(visited_trees) if "visited_trees" in dir() else 0} trees')

        if repair and result['repaired']:
            still_missing = [oid for oid in result['missing'] if not obj_store.exists(oid)]
            result['missing'] = still_missing
            if not still_missing and not result['corrupt'] and not result['errors']:
                result['ok'] = True

        return result

    def _repair_object(self, object_id: str, vault_id: str, sg_dir: str) -> bool:
        """Try to download a single missing object from the remote."""
        try:
            data = self.api.read(vault_id, f'bare/data/{object_id}')
            if data:
                local_path = os.path.join(sg_dir, 'bare', 'data', object_id)
                os.makedirs(os.path.dirname(local_path), exist_ok=True)
                with open(local_path, 'wb') as f:
                    f.write(data)
                return True
        except Exception:
            pass
        return False
