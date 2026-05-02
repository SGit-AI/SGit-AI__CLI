import json
import os
import secrets
import stat
import string
import sys
import time
from   urllib.request                                import urlopen
from   datetime                                      import datetime, timezone
from   osbot_utils.type_safe.Type_Safe               import Type_Safe
from   sgit_ai.crypto.Vault__Crypto              import Vault__Crypto
from   sgit_ai.crypto.PKI__Crypto                import PKI__Crypto
from   sgit_ai.crypto.Vault__Key_Manager         import Vault__Key_Manager
from   sgit_ai.api.Vault__API                    import Vault__API, LARGE_BLOB_THRESHOLD
from   sgit_ai.sync.Vault__Storage               import Vault__Storage
from   sgit_ai.sync.Vault__Branch_Manager        import Vault__Branch_Manager
from   sgit_ai.sync.Vault__Batch                 import Vault__Batch
from   sgit_ai.sync.Vault__Fetch                 import Vault__Fetch
from   sgit_ai.sync.Vault__Merge                 import Vault__Merge
from   sgit_ai.sync.Vault__Change_Pack           import Vault__Change_Pack
from   sgit_ai.sync.Vault__GC                   import Vault__GC
from   sgit_ai.sync.Vault__Remote_Manager        import Vault__Remote_Manager
from   sgit_ai.sync.Vault__Sub_Tree              import Vault__Sub_Tree
from   sgit_ai.objects.Vault__Object_Store       import Vault__Object_Store
from   sgit_ai.objects.Vault__Ref_Manager        import Vault__Ref_Manager
from   sgit_ai.objects.Vault__Commit             import Vault__Commit
from   sgit_ai.schemas.Schema__Object_Commit     import Schema__Object_Commit
from   sgit_ai.schemas.Schema__Object_Tree       import Schema__Object_Tree
from   sgit_ai.schemas.Schema__Object_Tree_Entry import Schema__Object_Tree_Entry
from   sgit_ai.schemas.Schema__Object_Ref        import Schema__Object_Ref
from   sgit_ai.schemas.Schema__Branch_Index      import Schema__Branch_Index
from   sgit_ai.schemas.Schema__Local_Config      import Schema__Local_Config
from   sgit_ai.schemas.Schema__Push_State        import Schema__Push_State
from   sgit_ai.schemas.Schema__Clone_Mode        import Schema__Clone_Mode
from   sgit_ai.safe_types.Enum__Clone_Mode           import Enum__Clone_Mode
from   sgit_ai.safe_types.Enum__Local_Config_Mode    import Enum__Local_Config_Mode
from   sgit_ai.safe_types.Safe_Str__Object_Id    import Safe_Str__Object_Id
from   sgit_ai.sync.Vault__Components             import Vault__Components
from   sgit_ai.sync.Vault__Errors                import Vault__Read_Only_Error, Vault__Clone_Mode_Corrupt_Error
from   sgit_ai.sync.Vault__Ignore                import Vault__Ignore
from   sgit_ai.sync.Vault__Storage               import SG_VAULT_DIR
from   sgit_ai.sync.Vault__Sync__Base            import Vault__Sync__Base
from   sgit_ai.sync.Vault__Sync__Commit          import Vault__Sync__Commit
from   sgit_ai.sync.Vault__Sync__Pull            import Vault__Sync__Pull
from   sgit_ai.sync.Vault__Sync__Push            import Vault__Sync__Push
from   sgit_ai.sync.Vault__Sync__Status          import Vault__Sync__Status
from   sgit_ai.sync.Vault__Sync__Clone           import Vault__Sync__Clone
from   sgit_ai.sync.Vault__Sync__Branch_Ops      import Vault__Sync__Branch_Ops
from   sgit_ai.sync.Vault__Sync__GC_Ops          import Vault__Sync__GC_Ops
from   sgit_ai.sync.Vault__Sync__Lifecycle       import Vault__Sync__Lifecycle


def _pull_stats_line(fetch_stats: dict, t_checkout: float) -> str:
    t_graph    = fetch_stats.get('t_graph', 0.0)
    t_download = fetch_stats.get('t_download', 0.0)
    n_commits  = fetch_stats.get('n_commits', 0)
    n_blobs    = fetch_stats.get('n_blobs', 0)
    parts = [f'graph-walk {t_graph:.1f}s', f'blobs {t_download:.1f}s', f'checkout {t_checkout:.1f}s']
    if n_commits or n_blobs:
        parts.append(f'({n_commits} commits, {n_blobs} blobs)')
    return '  '.join(parts)


class Vault__Sync(Vault__Sync__Base):
    crypto       : Vault__Crypto
    api          : Vault__API

    def generate_vault_key(self) -> str:
        alphabet   = string.ascii_lowercase + string.digits
        passphrase = ''.join(secrets.choice(alphabet) for _ in range(24))
        vault_id   = ''.join(secrets.choice(alphabet) for _ in range(8))
        return f'{passphrase}:{vault_id}'

    def init(self, directory: str, vault_key: str = None,
             allow_nonempty: bool = False, token: str = None) -> dict:
        from sgit_ai.transfer.Simple_Token import Simple_Token
        if os.path.exists(directory):
            entries = [e for e in os.listdir(directory) if e != SG_VAULT_DIR]
            if entries and not allow_nonempty:
                raise RuntimeError(f'Directory is not empty: {directory}')
        os.makedirs(directory, exist_ok=True)

        # Simple token path: token arg takes precedence over vault_key
        simple_token_mode = False
        if token and Simple_Token.is_simple_token(token):
            simple_token_mode = True
            vault_key         = token
        elif vault_key and Simple_Token.is_simple_token(vault_key):
            simple_token_mode = True
            token             = vault_key

        if not vault_key:
            vault_key = self.generate_vault_key()

        if simple_token_mode:
            keys = self.crypto.derive_keys_from_simple_token(vault_key)
        else:
            keys = self.crypto.derive_keys_from_vault_key(vault_key)
        vault_id   = keys['vault_id']
        read_key   = keys['read_key_bytes']

        storage = Vault__Storage()
        sg_dir  = storage.create_bare_structure(directory)

        pki         = PKI__Crypto()
        key_manager = Vault__Key_Manager(vault_path=sg_dir, crypto=self.crypto, pki=pki)
        ref_manager = Vault__Ref_Manager(vault_path=sg_dir, crypto=self.crypto)
        obj_store   = Vault__Object_Store(vault_path=sg_dir, crypto=self.crypto)

        branch_manager = Vault__Branch_Manager(vault_path    = sg_dir,
                                               crypto        = self.crypto,
                                               key_manager   = key_manager,
                                               ref_manager   = ref_manager,
                                               storage       = storage)

        timestamp_ms   = int(time.time() * 1000)
        clone_ref_id   = 'ref-pid-snw-' + self.crypto.derive_branch_ref_file_id(
                             read_key, vault_id, 'local')
        named_branch   = branch_manager.create_named_branch(directory, 'current', read_key,
                                                             head_ref_id=keys['ref_file_id'],
                                                             timestamp_ms=timestamp_ms)
        clone_branch   = branch_manager.create_clone_branch(directory, 'local', read_key,
                                                             head_ref_id=clone_ref_id,
                                                             creator_branch_id=str(named_branch.branch_id),
                                                             timestamp_ms=timestamp_ms)

        branch_index = Schema__Branch_Index(schema   = 'branch_index_v1',
                                            branches = [named_branch, clone_branch])
        branch_manager.save_branch_index(directory, branch_index, read_key,
                                         index_file_id=keys['branch_index_file_id'])

        clone_private_key = key_manager.load_private_key_locally(
            str(clone_branch.public_key_id), storage.local_dir(directory))

        vault_commit = Vault__Commit(crypto=self.crypto, pki=pki,
                                     object_store=obj_store, ref_manager=ref_manager)

        # Create empty root tree and store it
        sub_tree     = Vault__Sub_Tree(crypto=self.crypto, obj_store=obj_store)
        empty_tree   = Schema__Object_Tree(schema='tree_v1')
        root_tree_id = sub_tree._store_tree(empty_tree, read_key)

        commit_id = vault_commit.create_commit(read_key      = read_key,
                                               tree_id       = root_tree_id,
                                               message       = 'init',
                                               branch_id     = str(clone_branch.branch_id),
                                               signing_key   = clone_private_key,
                                               timestamp_ms  = timestamp_ms)

        ref_manager.write_ref(str(named_branch.head_ref_id), commit_id, read_key)
        ref_manager.write_ref(str(clone_branch.head_ref_id), commit_id, read_key)

        local_config = Schema__Local_Config(
            my_branch_id = str(clone_branch.branch_id),
            mode         = Enum__Local_Config_Mode.SIMPLE_TOKEN if simple_token_mode else None,
            edit_token   = vault_key if simple_token_mode else None,
        )
        config_path  = storage.local_config_path(directory)
        with open(config_path, 'w') as f:
            json.dump(local_config.json(), f, indent=2)
        storage.chmod_local_file(config_path)

        vault_key_path = storage.vault_key_path(directory)
        with open(vault_key_path, 'w') as f:
            f.write(vault_key)
        storage.chmod_local_file(vault_key_path)

        return dict(directory    = directory,
                    vault_key    = vault_key,
                    vault_id     = vault_id,
                    branch_id    = str(clone_branch.branch_id),
                    named_branch = str(named_branch.branch_id),
                    commit_id    = commit_id)

    def commit(self, directory: str, message: str = '') -> dict:
        return Vault__Sync__Commit(crypto=self.crypto, api=self.api).commit(directory, message)

    def write_file(self, directory: str, path: str, content: bytes,
                   message: str = '', also: dict = None) -> dict:
        return Vault__Sync__Commit(crypto=self.crypto, api=self.api).write_file(
            directory, path, content, message, also)

    def reset(self, directory: str, commit_id: str = None) -> dict:
        return Vault__Sync__Pull(crypto=self.crypto, api=self.api).reset(directory, commit_id)

    def status(self, directory: str) -> dict:
        return Vault__Sync__Status(crypto=self.crypto, api=self.api).status(directory)

    def pull(self, directory: str, on_progress: callable = None) -> dict:
        return Vault__Sync__Pull(crypto=self.crypto, api=self.api).pull(directory, on_progress)

    def push(self, directory: str, message: str = '', force: bool = False,
             use_batch: bool = True, branch_only: bool = False,
             on_progress: callable = None) -> dict:
        return Vault__Sync__Push(crypto=self.crypto, api=self.api).push(
            directory, message, force, use_batch, branch_only, on_progress)

    def merge_abort(self, directory: str) -> dict:
        return Vault__Sync__Branch_Ops(crypto=self.crypto, api=self.api).merge_abort(directory)

    def branches(self, directory: str) -> dict:
        return Vault__Sync__Branch_Ops(crypto=self.crypto, api=self.api).branches(directory)

    def gc_drain(self, directory: str) -> dict:
        return Vault__Sync__GC_Ops(crypto=self.crypto, api=self.api).gc_drain(directory)

    def create_change_pack(self, directory: str, files: dict) -> dict:
        return Vault__Sync__GC_Ops(crypto=self.crypto, api=self.api).create_change_pack(directory, files)

    def remote_add(self, directory: str, name: str, url: str, vault_id: str) -> dict:
        return Vault__Sync__Branch_Ops(crypto=self.crypto, api=self.api).remote_add(directory, name, url, vault_id)

    def remote_remove(self, directory: str, name: str) -> dict:
        return Vault__Sync__Branch_Ops(crypto=self.crypto, api=self.api).remote_remove(directory, name)

    def remote_list(self, directory: str) -> dict:
        return Vault__Sync__Branch_Ops(crypto=self.crypto, api=self.api).remote_list(directory)

    def clone(self, vault_key: str, directory: str, on_progress: callable = None, sparse: bool = False) -> dict:
        return Vault__Sync__Clone(crypto=self.crypto, api=self.api).clone(vault_key, directory, on_progress, sparse)

    def clone_read_only(self, vault_id: str, read_key_hex: str, directory: str,
                        on_progress: callable = None, sparse: bool = False) -> dict:
        return Vault__Sync__Clone(crypto=self.crypto, api=self.api).clone_read_only(
            vault_id, read_key_hex, directory, on_progress, sparse)

    def clone_from_transfer(self, token_str: str, directory: str, debug_log=None) -> dict:
        return Vault__Sync__Clone(crypto=self.crypto, api=self.api).clone_from_transfer(
            token_str, directory, debug_log)

    def delete_on_remote(self, directory: str) -> dict:
        return Vault__Sync__Lifecycle(crypto=self.crypto, api=self.api).delete_on_remote(directory)

    def rekey_check(self, directory: str) -> dict:
        return Vault__Sync__Lifecycle(crypto=self.crypto, api=self.api).rekey_check(directory)

    def rekey_wipe(self, directory: str) -> dict:
        return Vault__Sync__Lifecycle(crypto=self.crypto, api=self.api).rekey_wipe(directory)

    def rekey_init(self, directory: str, new_vault_key: str = None) -> dict:
        return Vault__Sync__Lifecycle(crypto=self.crypto, api=self.api).rekey_init(directory, new_vault_key)

    def rekey_commit(self, directory: str) -> dict:
        return Vault__Sync__Lifecycle(crypto=self.crypto, api=self.api).rekey_commit(directory)

    def rekey(self, directory: str, new_vault_key: str = None) -> dict:
        return Vault__Sync__Lifecycle(crypto=self.crypto, api=self.api).rekey(directory, new_vault_key)

    def probe_token(self, token_str: str) -> dict:
        return Vault__Sync__Lifecycle(crypto=self.crypto, api=self.api).probe_token(token_str)

    def uninit(self, directory: str) -> dict:
        return Vault__Sync__Lifecycle(crypto=self.crypto, api=self.api).uninit(directory)

    def restore_from_backup(self, zip_path: str, directory: str) -> dict:
        return Vault__Sync__Lifecycle(crypto=self.crypto, api=self.api).restore_from_backup(zip_path, directory)

    def _get_head_flat_map(self, directory: str) -> tuple:
        """Return (flat_entries, obj_store, read_key) for the clone branch HEAD."""
        c           = self._init_components(directory)
        storage     = c.storage
        obj_store   = c.obj_store
        ref_manager = c.ref_manager
        read_key    = c.read_key
        pki         = PKI__Crypto()

        local_config = self._read_local_config(directory, storage)
        branch_id    = str(local_config.my_branch_id)
        index_id     = c.branch_index_file_id
        branch_index = c.branch_manager.load_branch_index(directory, index_id, read_key)
        branch_meta  = c.branch_manager.get_branch_by_id(branch_index, branch_id)
        if not branch_meta:
            branch_meta = c.branch_manager.get_branch_by_name(branch_index, 'current')
            if not branch_meta:
                return {}, obj_store, read_key, str(c.vault_id), c.sg_dir

        commit_id = ref_manager.read_ref(str(branch_meta.head_ref_id), read_key)
        if not commit_id:
            return {}, obj_store, read_key, str(c.vault_id), c.sg_dir

        vc       = Vault__Commit(crypto=self.crypto, pki=pki,
                                 object_store=obj_store, ref_manager=ref_manager)
        sub_tree = Vault__Sub_Tree(crypto=self.crypto, obj_store=obj_store)
        commit   = vc.load_commit(commit_id, read_key)
        flat     = sub_tree.flatten(str(commit.tree_id), read_key)
        return flat, obj_store, read_key, str(c.vault_id), c.sg_dir

    def sparse_ls(self, directory: str, path: str = None) -> list:
        """List vault tree entries with local fetch status."""
        flat, obj_store, read_key, vault_id, sg_dir = self._get_head_flat_map(directory)
        prefix  = (path.rstrip('/') + '/') if path else None
        results = []
        for entry_path, entry_data in sorted(flat.items()):
            if prefix and not (entry_path == path or entry_path.startswith(prefix)):
                continue
            blob_id = entry_data.get('blob_id', '')
            results.append(dict(
                path    = entry_path,
                size    = entry_data.get('size', 0),
                blob_id = blob_id,
                fetched = obj_store.exists(blob_id) if blob_id else False,
                large   = bool(entry_data.get('large', False)),
            ))
        return results

    def sparse_fetch(self, directory: str, path: str = None,
                     on_progress: callable = None) -> dict:
        """Fetch file(s) to the local object store and write to working copy."""
        flat, obj_store, read_key, vault_id, sg_dir = self._get_head_flat_map(directory)
        _p = on_progress or (lambda *a, **k: None)

        prefix  = (path.rstrip('/') + '/') if path else None
        entries = []
        for entry_path, entry_data in flat.items():
            if prefix and not (entry_path == path or entry_path.startswith(prefix)):
                continue
            blob_id = entry_data.get('blob_id', '')
            if not blob_id:
                continue
            entries.append(dict(
                path    = entry_path,
                blob_id = blob_id,
                size    = entry_data.get('size', 0),
                large   = bool(entry_data.get('large', False)),
                fetched = obj_store.exists(blob_id),
            ))

        if not entries:
            return dict(fetched=0, already_local=0, written=[])

        to_download   = [e for e in entries if not e['fetched']]
        already_local = len(entries) - len(to_download)

        if to_download:
            LARGE_THRESHOLD = 2 * 1024 * 1024
            small = [e for e in to_download if not e['large'] and e['size'] <= LARGE_THRESHOLD]
            large = [e for e in to_download if e['large'] or e['size'] > LARGE_THRESHOLD]
            total = len(to_download)
            done  = 0
            _p('download', 'Fetching objects', f'0/{total}')

            if small:
                fids = [f'bare/data/{e["blob_id"]}' for e in small]
                for fid, data in self.api.batch_read(vault_id, fids).items():
                    if data:
                        blob_id    = fid.replace('bare/data/', '')
                        local_path = os.path.join(sg_dir, 'bare', 'data', blob_id)
                        os.makedirs(os.path.dirname(local_path), exist_ok=True)
                        with open(local_path, 'wb') as f:
                            f.write(data)
                    done += 1
                    _p('download', 'Fetching objects', f'{done}/{total}')

            for e in large:
                fid      = f'bare/data/{e["blob_id"]}'
                url_info = self.api.presigned_read_url(vault_id, fid)
                s3_url   = url_info.get('url') or url_info.get('presigned_url', '')
                with urlopen(s3_url) as resp:
                    data = resp.read()
                local_path = os.path.join(sg_dir, 'bare', 'data', e['blob_id'])
                os.makedirs(os.path.dirname(local_path), exist_ok=True)
                with open(local_path, 'wb') as f:
                    f.write(data)
                done += 1
                _p('download', 'Fetching objects', f'{done}/{total}')

        written = []
        for e in entries:
            if obj_store.exists(e['blob_id']):
                ciphertext = obj_store.load(e['blob_id'])
                plaintext  = self.crypto.decrypt(read_key, ciphertext)
                full_path  = os.path.join(directory, e['path'])
                os.makedirs(os.path.dirname(full_path), exist_ok=True)
                with open(full_path, 'wb') as f:
                    f.write(plaintext)
                written.append(e['path'])

        return dict(fetched=len(to_download), already_local=already_local, written=written)

    def sparse_cat(self, directory: str, path: str) -> bytes:
        """Decrypt and return file content. Fetches blob from server if not locally cached."""
        flat, obj_store, read_key, vault_id, sg_dir = self._get_head_flat_map(directory)
        match = flat.get(path)
        if not match:
            raise RuntimeError(f'File not found in vault: {path}')

        blob_id = match.get('blob_id', '')
        if not blob_id:
            raise RuntimeError(f'No blob stored for: {path}')

        if not obj_store.exists(blob_id):
            fid = f'bare/data/{blob_id}'
            if match.get('large'):
                url_info = self.api.presigned_read_url(vault_id, fid)
                s3_url   = url_info.get('url') or url_info.get('presigned_url', '')
                with urlopen(s3_url) as resp:
                    data = resp.read()
            else:
                data = self.api.read(vault_id, fid)
            if data:
                local_path = os.path.join(sg_dir, 'bare', 'data', blob_id)
                os.makedirs(os.path.dirname(local_path), exist_ok=True)
                with open(local_path, 'wb') as f:
                    f.write(data)

        if not obj_store.exists(blob_id):
            raise RuntimeError(f'Failed to fetch {path!r} from server')

        ciphertext = obj_store.load(blob_id)
        return self.crypto.decrypt(read_key, ciphertext)

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

    def _scan_local_directory(self, directory: str) -> dict:
        ignore = Vault__Ignore().load_gitignore(directory)
        result = {}
        for root, dirs, files in os.walk(directory):
            rel_root = os.path.relpath(root, directory).replace(os.sep, '/')
            if rel_root == '.':
                rel_root = ''
            dirs[:] = [d for d in dirs
                       if not ignore.should_ignore_dir(f'{rel_root}/{d}' if rel_root else d)]
            for filename in files:
                rel_path = f'{rel_root}/{filename}' if rel_root else filename
                if ignore.should_ignore_file(rel_path):
                    continue
                full_path = os.path.join(root, filename)
                file_size = os.path.getsize(full_path)
                with open(full_path, 'rb') as f:
                    file_hash = self.crypto.content_hash(f.read())
                result[rel_path] = dict(size=file_size, content_hash=file_hash)
        return result
