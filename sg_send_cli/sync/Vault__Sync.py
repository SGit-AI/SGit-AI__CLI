import json
import os
import secrets
import string
import time
from   datetime                                      import datetime, timezone
from   osbot_utils.type_safe.Type_Safe               import Type_Safe
from   sg_send_cli.crypto.Vault__Crypto              import Vault__Crypto
from   sg_send_cli.crypto.PKI__Crypto                import PKI__Crypto
from   sg_send_cli.crypto.Vault__Key_Manager         import Vault__Key_Manager
from   sg_send_cli.api.Vault__API                    import Vault__API
from   sg_send_cli.sync.Vault__Legacy_Guard          import Vault__Legacy_Guard
from   sg_send_cli.sync.Vault__Storage               import Vault__Storage
from   sg_send_cli.sync.Vault__Branch_Manager        import Vault__Branch_Manager
from   sg_send_cli.sync.Vault__Fetch                 import Vault__Fetch
from   sg_send_cli.sync.Vault__Merge                 import Vault__Merge
from   sg_send_cli.objects.Vault__Object_Store       import Vault__Object_Store
from   sg_send_cli.objects.Vault__Ref_Manager        import Vault__Ref_Manager
from   sg_send_cli.objects.Vault__Commit             import Vault__Commit
from   sg_send_cli.schemas.Schema__Object_Commit     import Schema__Object_Commit
from   sg_send_cli.schemas.Schema__Object_Tree       import Schema__Object_Tree
from   sg_send_cli.schemas.Schema__Object_Tree_Entry import Schema__Object_Tree_Entry
from   sg_send_cli.schemas.Schema__Object_Ref        import Schema__Object_Ref
from   sg_send_cli.schemas.Schema__Branch_Index      import Schema__Branch_Index
from   sg_send_cli.schemas.Schema__Local_Config      import Schema__Local_Config

SG_VAULT_DIR  = '.sg_vault'
VAULT_KEY_FILE = 'VAULT-KEY'
TREE_FILE     = 'tree.json'
SETTINGS_FILE = 'settings.json'


class Vault__Sync(Type_Safe):
    crypto       : Vault__Crypto
    api          : Vault__API
    legacy_guard : Vault__Legacy_Guard

    def generate_vault_key(self) -> str:
        alphabet   = string.ascii_lowercase + string.digits
        passphrase = ''.join(secrets.choice(alphabet) for _ in range(24))
        vault_id   = ''.join(secrets.choice(alphabet) for _ in range(8))
        return f'{passphrase}:{vault_id}'

    def init(self, directory: str, vault_key: str = None) -> dict:
        if os.path.exists(directory):
            entries = os.listdir(directory)
            if entries:
                raise RuntimeError(f'Directory is not empty: {directory}')
        os.makedirs(directory, exist_ok=True)

        if not vault_key:
            vault_key = self.generate_vault_key()

        keys       = self.crypto.derive_keys_from_vault_key(vault_key)
        vault_id   = keys['vault_id']
        read_key   = keys['read_key_bytes']
        write_key  = keys['write_key']

        sg_vault_dir = os.path.join(directory, SG_VAULT_DIR)
        os.makedirs(sg_vault_dir, exist_ok=True)
        object_store = Vault__Object_Store(vault_path=sg_vault_dir, crypto=self.crypto)
        ref_manager  = Vault__Ref_Manager(vault_path=sg_vault_dir)

        now          = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.000Z')
        tree_obj     = Schema__Object_Tree()
        tree_data    = dict(version=1, updated=now, tree={'/': {'type': 'folder', 'children': {}}})
        settings_data = dict(vault_id=vault_id, vault_name=vault_id)

        encrypted_tree = self.crypto.encrypt(read_key, json.dumps(tree_data).encode())
        self.api.write(vault_id, keys['tree_file_id'], write_key, encrypted_tree)

        encrypted_settings = self.crypto.encrypt(read_key, json.dumps(settings_data).encode())
        self.api.write(vault_id, keys['settings_file_id'], write_key, encrypted_settings)

        tree_obj_json      = json.dumps(tree_obj.json()).encode()
        encrypted_tree_obj = self.crypto.encrypt(read_key, tree_obj_json)
        tree_obj_id        = object_store.store(encrypted_tree_obj)

        commit = Schema__Object_Commit(tree_id   = tree_obj_id,
                                        version   = 1,
                                        timestamp = now,
                                        message   = 'init')
        commit_json      = json.dumps(commit.json()).encode()
        encrypted_commit = self.crypto.encrypt(read_key, commit_json)
        commit_id        = object_store.store(encrypted_commit)

        ref_manager.write_head(commit_id)

        with open(os.path.join(sg_vault_dir, VAULT_KEY_FILE), 'w') as f:
            f.write(vault_key)
        with open(os.path.join(sg_vault_dir, TREE_FILE), 'w') as f:
            json.dump(tree_data, f, indent=2)
        with open(os.path.join(sg_vault_dir, SETTINGS_FILE), 'w') as f:
            json.dump(settings_data, f, indent=2)

        return dict(directory=directory, vault_key=vault_key, vault_id=vault_id)

    def clone(self, vault_key: str, directory: str = None, on_progress: callable = None, bare: bool = False) -> str:
        keys       = self.crypto.derive_keys_from_vault_key(vault_key)
        vault_id   = keys['vault_id']
        read_key   = keys['read_key_bytes']

        if directory is None:
            directory = vault_id
        os.makedirs(directory, exist_ok=True)

        if on_progress:
            on_progress('metadata', 'Downloading vault metadata...')

        settings = self._download_and_decrypt(vault_id, keys['settings_file_id'], read_key)
        tree     = self._download_and_decrypt(vault_id, keys['tree_file_id'], read_key)

        settings_data = json.loads(settings)
        tree_data     = json.loads(tree)

        file_map = self._flatten_tree(tree_data.get('tree', {}))

        if on_progress:
            on_progress('tree_resolved', None, dict(total_files=len(file_map), vault_id=vault_id,
                                                     vault_name=settings_data.get('vault_name', vault_id),
                                                     version=tree_data.get('version', 1)))

        sg_vault_dir = os.path.join(directory, SG_VAULT_DIR)
        os.makedirs(sg_vault_dir, exist_ok=True)
        object_store = Vault__Object_Store(vault_path=sg_vault_dir, crypto=self.crypto)
        ref_manager  = Vault__Ref_Manager(vault_path=sg_vault_dir)

        tree_obj     = Schema__Object_Tree()
        total_bytes  = 0

        for idx, (file_path, file_info) in enumerate(file_map.items()):
            file_id        = file_info['file_id']
            encrypted_data = self.api.read(vault_id, file_id)
            plaintext      = self.crypto.decrypt(read_key, encrypted_data)

            if not bare:
                full_path = os.path.join(directory, file_path)
                os.makedirs(os.path.dirname(full_path), exist_ok=True)
                with open(full_path, 'wb') as f:
                    f.write(plaintext)

            blob_id = object_store.store(encrypted_data)
            tree_obj.entries.append(Schema__Object_Tree_Entry(path=file_path, blob_id=blob_id, size=len(plaintext)))
            total_bytes += len(plaintext)

            if on_progress:
                on_progress('file', file_path, dict(index=idx + 1, total=len(file_map),
                                                     size=len(plaintext), total_bytes=total_bytes))

        now       = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.000Z')
        version   = tree_data.get('version', 1)
        tree_json = json.dumps(tree_obj.json()).encode()
        encrypted_tree_obj = self.crypto.encrypt(read_key, tree_json)
        tree_obj_id = object_store.store(encrypted_tree_obj)

        commit = Schema__Object_Commit(tree_id   = tree_obj_id,
                                        version   = version,
                                        timestamp = now,
                                        message   = 'clone')
        commit_json     = json.dumps(commit.json()).encode()
        encrypted_commit = self.crypto.encrypt(read_key, commit_json)
        commit_id        = object_store.store(encrypted_commit)

        ref_manager.write_head(commit_id)

        if not bare:
            with open(os.path.join(sg_vault_dir, VAULT_KEY_FILE), 'w') as f:
                f.write(vault_key)
        with open(os.path.join(sg_vault_dir, TREE_FILE), 'w') as f:
            json.dump(tree_data, f, indent=2)
        with open(os.path.join(sg_vault_dir, SETTINGS_FILE), 'w') as f:
            json.dump(settings_data, f, indent=2)

        if on_progress:
            on_progress('done', directory, dict(total_files=len(file_map), total_bytes=total_bytes,
                                                 commit_id=commit_id, version=version))

        return directory

    def pull(self, directory: str = '.') -> dict:
        self.legacy_guard.check_vault_format(directory)
        vault_key = self._read_vault_key(directory)
        keys      = self.crypto.derive_keys_from_vault_key(vault_key)
        vault_id  = keys['vault_id']
        read_key  = keys['read_key_bytes']

        sg_vault_dir = os.path.join(directory, SG_VAULT_DIR)
        object_store = Vault__Object_Store(vault_path=sg_vault_dir, crypto=self.crypto)
        ref_manager  = Vault__Ref_Manager(vault_path=sg_vault_dir)

        settings      = self._download_and_decrypt(vault_id, keys['settings_file_id'], read_key)
        tree          = self._download_and_decrypt(vault_id, keys['tree_file_id'], read_key)
        settings_data = json.loads(settings)
        tree_data     = json.loads(tree)

        old_file_map  = self._read_local_tree_from_objects(sg_vault_dir, read_key)
        new_file_map  = self._flatten_tree(tree_data.get('tree', {}))

        old_paths = set(old_file_map.keys())
        new_paths = set(new_file_map.keys())

        added    = new_paths - old_paths
        deleted  = old_paths - new_paths
        modified = set()
        for path in old_paths & new_paths:
            if old_file_map[path].get('file_id') != new_file_map[path].get('file_id'):
                modified.add(path)

        new_tree_obj = Schema__Object_Tree()

        for path in new_paths:
            file_info = new_file_map[path]
            if path in added | modified:
                file_id        = file_info['file_id']
                encrypted_data = self.api.read(vault_id, file_id)
                plaintext      = self.crypto.decrypt(read_key, encrypted_data)
                full_path      = os.path.join(directory, path)
                os.makedirs(os.path.dirname(full_path), exist_ok=True)
                with open(full_path, 'wb') as f:
                    f.write(plaintext)
                blob_id = object_store.store(encrypted_data)
                new_tree_obj.entries.append(Schema__Object_Tree_Entry(path=path, blob_id=blob_id, size=len(plaintext)))
            else:
                old_entry = old_file_map[path]
                new_tree_obj.entries.append(Schema__Object_Tree_Entry(path=path, blob_id=old_entry['blob_id'], size=old_entry['size']))

        for path in deleted:
            full_path = os.path.join(directory, path)
            if os.path.exists(full_path):
                os.remove(full_path)

        now       = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.000Z')
        version   = tree_data.get('version', 1)
        parent_id = ref_manager.read_head()

        tree_json          = json.dumps(new_tree_obj.json()).encode()
        encrypted_tree_obj = self.crypto.encrypt(read_key, tree_json)
        tree_obj_id        = object_store.store(encrypted_tree_obj)

        commit = Schema__Object_Commit(tree_id   = tree_obj_id,
                                        version   = version,
                                        parent    = parent_id or '',
                                        timestamp = now,
                                        message   = 'pull')
        commit_json      = json.dumps(commit.json()).encode()
        encrypted_commit = self.crypto.encrypt(read_key, commit_json)
        commit_id        = object_store.store(encrypted_commit)

        ref_manager.write_head(commit_id)

        with open(os.path.join(sg_vault_dir, TREE_FILE), 'w') as f:
            json.dump(tree_data, f, indent=2)
        with open(os.path.join(sg_vault_dir, SETTINGS_FILE), 'w') as f:
            json.dump(settings_data, f, indent=2)

        return dict(added=sorted(added), modified=sorted(modified), deleted=sorted(deleted))

    def push(self, directory: str = '.') -> dict:
        self.legacy_guard.check_vault_format(directory)
        vault_key = self._read_vault_key(directory)
        keys      = self.crypto.derive_keys_from_vault_key(vault_key)
        vault_id  = keys['vault_id']
        read_key  = keys['read_key_bytes']
        write_key = keys['write_key']

        sg_vault_dir = os.path.join(directory, SG_VAULT_DIR)
        object_store = Vault__Object_Store(vault_path=sg_vault_dir, crypto=self.crypto)
        ref_manager  = Vault__Ref_Manager(vault_path=sg_vault_dir)

        old_file_map  = self._read_local_tree_from_objects(sg_vault_dir, read_key)
        new_file_map  = self._scan_local_directory(directory)

        old_paths = set(old_file_map.keys())
        new_paths = set(new_file_map.keys())

        added    = new_paths - old_paths
        deleted  = old_paths - new_paths
        common   = old_paths & new_paths
        modified = set()

        for path in common:
            local_file = os.path.join(directory, path)
            with open(local_file, 'rb') as f:
                content = f.read()
            if len(content) != old_file_map[path].get('size', -1):
                modified.add(path)

        uploaded     = {}
        new_tree_obj = Schema__Object_Tree()

        for path in sorted(new_paths):
            if path in added | modified:
                local_file = os.path.join(directory, path)
                with open(local_file, 'rb') as f:
                    content = f.read()
                file_id   = os.urandom(6).hex()
                encrypted = self.crypto.encrypt(read_key, content)
                self.api.write(vault_id, file_id, write_key, encrypted)
                blob_id = object_store.store(encrypted)
                new_tree_obj.entries.append(Schema__Object_Tree_Entry(path=path, blob_id=blob_id, size=len(content)))
                uploaded[path] = dict(file_id=file_id, size=len(content))
            else:
                old_entry = old_file_map[path]
                new_tree_obj.entries.append(Schema__Object_Tree_Entry(path=path, blob_id=old_entry['blob_id'], size=old_entry['size']))
                uploaded[path] = dict(file_id=old_entry.get('file_id', ''), size=old_entry['size'])

        for path in deleted:
            file_id = old_file_map[path].get('file_id', '')
            if file_id:
                self.api.delete(vault_id, file_id, write_key)

        old_tree_data = self._read_local_tree(directory)
        new_tree_data = self._build_tree_json(old_tree_data,
                                               self._flatten_tree(old_tree_data.get('tree', {})),
                                               {p: uploaded[p] for p in added | modified},
                                               deleted)

        tree_json      = json.dumps(new_tree_data).encode()
        encrypted_tree = self.crypto.encrypt(read_key, tree_json)
        self.api.write(vault_id, keys['tree_file_id'], write_key, encrypted_tree)

        settings_data      = self._read_local_settings(directory)
        settings_json      = json.dumps(settings_data).encode()
        encrypted_settings = self.crypto.encrypt(read_key, settings_json)
        self.api.write(vault_id, keys['settings_file_id'], write_key, encrypted_settings)

        now       = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.000Z')
        version   = new_tree_data.get('version', 1)
        parent_id = ref_manager.read_head()

        tree_obj_json      = json.dumps(new_tree_obj.json()).encode()
        encrypted_tree_obj = self.crypto.encrypt(read_key, tree_obj_json)
        tree_obj_id        = object_store.store(encrypted_tree_obj)

        commit = Schema__Object_Commit(tree_id   = tree_obj_id,
                                        version   = version,
                                        parent    = parent_id or '',
                                        timestamp = now,
                                        message   = 'push')
        commit_json      = json.dumps(commit.json()).encode()
        encrypted_commit = self.crypto.encrypt(read_key, commit_json)
        commit_id        = object_store.store(encrypted_commit)

        ref_manager.write_head(commit_id)

        with open(os.path.join(sg_vault_dir, TREE_FILE), 'w') as f:
            json.dump(new_tree_data, f, indent=2)

        return dict(added=list(added), modified=list(modified), deleted=list(deleted))

    def status(self, directory: str = '.') -> dict:
        self.legacy_guard.check_vault_format(directory)
        sg_vault_dir = os.path.join(directory, SG_VAULT_DIR)
        read_key     = self._get_read_key(directory)
        old_file_map = self._read_local_tree_from_objects(sg_vault_dir, read_key)
        new_file_map = self._scan_local_directory(directory)

        old_paths = set(old_file_map.keys())
        new_paths = set(new_file_map.keys())

        added    = sorted(new_paths - old_paths)
        deleted  = sorted(old_paths - new_paths)
        common   = old_paths & new_paths
        modified = []

        for path in sorted(common):
            local_file = os.path.join(directory, path)
            with open(local_file, 'rb') as f:
                content = f.read()
            if len(content) != old_file_map[path].get('size', -1):
                modified.append(path)

        return dict(added=added, modified=modified, deleted=deleted,
                    clean=not added and not modified and not deleted)

    def remote_status(self, directory: str = '.') -> dict:
        self.legacy_guard.check_vault_format(directory)
        vault_key = self._read_vault_key(directory)
        keys      = self.crypto.derive_keys_from_vault_key(vault_key)
        vault_id  = keys['vault_id']
        read_key  = keys['read_key_bytes']

        remote_tree_raw  = self._download_and_decrypt(vault_id, keys['tree_file_id'], read_key)
        remote_tree_data = json.loads(remote_tree_raw)
        remote_file_map  = self._flatten_tree(remote_tree_data.get('tree', {}))

        sg_vault_dir   = os.path.join(directory, SG_VAULT_DIR)
        local_file_map = self._read_local_tree_from_objects(sg_vault_dir, read_key)

        remote_paths = set(remote_file_map.keys())
        local_paths  = set(local_file_map.keys())

        remote_added    = sorted(remote_paths - local_paths)
        remote_deleted  = sorted(local_paths - remote_paths)
        remote_modified = []
        for path in sorted(remote_paths & local_paths):
            if remote_file_map[path].get('file_id') != local_file_map[path].get('file_id'):
                remote_modified.append(path)

        local_status = self.status(directory)

        return dict(remote_version = remote_tree_data.get('version'),
                    local_version  = self._read_local_tree(directory).get('version'),
                    remote_added   = remote_added,
                    remote_modified= remote_modified,
                    remote_deleted = remote_deleted,
                    local_added    = local_status['added'],
                    local_modified = local_status['modified'],
                    local_deleted  = local_status['deleted'])

    # --- v2 methods ---

    def init_v2(self, directory: str, vault_key: str = None) -> dict:
        if os.path.exists(directory):
            entries = os.listdir(directory)
            if entries:
                raise RuntimeError(f'Directory is not empty: {directory}')
        os.makedirs(directory, exist_ok=True)

        if not vault_key:
            vault_key = self.generate_vault_key()

        keys       = self.crypto.derive_keys_from_vault_key(vault_key)
        vault_id   = keys['vault_id']
        read_key   = keys['read_key_bytes']

        storage = Vault__Storage()
        sg_dir  = storage.create_bare_structure(directory)

        pki         = PKI__Crypto()
        key_manager = Vault__Key_Manager(vault_path=sg_dir, crypto=self.crypto, pki=pki)
        ref_manager = Vault__Ref_Manager(vault_path=sg_dir, crypto=self.crypto, use_v2=True)
        obj_store   = Vault__Object_Store(vault_path=sg_dir, crypto=self.crypto, use_v2=True)

        branch_manager = Vault__Branch_Manager(vault_path    = sg_dir,
                                               crypto        = self.crypto,
                                               key_manager   = key_manager,
                                               ref_manager   = ref_manager,
                                               storage       = storage)

        timestamp_ms   = int(time.time() * 1000)
        named_branch   = branch_manager.create_named_branch(directory, 'current', read_key,
                                                             timestamp_ms=timestamp_ms)
        clone_branch   = branch_manager.create_clone_branch(directory, 'local', read_key,
                                                             creator_branch_id=str(named_branch.branch_id),
                                                             timestamp_ms=timestamp_ms)

        branch_index = Schema__Branch_Index(schema   = 'branch_index_v1',
                                            branches = [named_branch, clone_branch])
        branch_manager.save_branch_index(directory, branch_index, read_key)

        clone_private_key = key_manager.load_private_key_locally(
            str(clone_branch.public_key_id), storage.local_dir(directory))

        vault_commit = Vault__Commit(crypto=self.crypto, pki=pki,
                                     object_store=obj_store, ref_manager=ref_manager)

        tree_obj = Schema__Object_Tree(schema='tree_v1')
        commit_id = vault_commit.create_commit(tree          = tree_obj,
                                               read_key      = read_key,
                                               message       = 'init',
                                               branch_id     = str(clone_branch.branch_id),
                                               signing_key   = clone_private_key,
                                               timestamp_ms  = timestamp_ms)

        ref_manager.write_ref(str(named_branch.head_ref_id), commit_id, read_key)
        ref_manager.write_ref(str(clone_branch.head_ref_id), commit_id, read_key)

        # Also write legacy refs/head for backward compat during transition
        ref_manager.write_head(commit_id)

        local_config = Schema__Local_Config(my_branch_id=str(clone_branch.branch_id))
        config_path  = storage.local_config_path(directory)
        with open(config_path, 'w') as f:
            json.dump(local_config.json(), f, indent=2)

        with open(os.path.join(sg_dir, VAULT_KEY_FILE), 'w') as f:
            f.write(vault_key)

        return dict(directory    = directory,
                    vault_key    = vault_key,
                    vault_id     = vault_id,
                    branch_id    = str(clone_branch.branch_id),
                    named_branch = str(named_branch.branch_id),
                    commit_id    = commit_id)

    def commit_v2(self, directory: str, message: str = '') -> dict:
        vault_key  = self._read_vault_key(directory)
        keys       = self.crypto.derive_keys_from_vault_key(vault_key)
        read_key   = keys['read_key_bytes']
        sg_dir     = os.path.join(directory, SG_VAULT_DIR)

        storage    = Vault__Storage()
        pki        = PKI__Crypto()
        obj_store  = Vault__Object_Store(vault_path=sg_dir, crypto=self.crypto, use_v2=True)
        ref_manager = Vault__Ref_Manager(vault_path=sg_dir, crypto=self.crypto, use_v2=True)

        local_config = self._read_local_config(directory, storage)
        branch_id    = str(local_config.my_branch_id)

        key_manager    = Vault__Key_Manager(vault_path=sg_dir, crypto=self.crypto, pki=pki)
        branch_manager = Vault__Branch_Manager(vault_path=sg_dir, crypto=self.crypto,
                                               key_manager=key_manager, ref_manager=ref_manager,
                                               storage=storage)

        index_id = branch_manager.find_branch_index_id(directory)
        if not index_id:
            raise RuntimeError('No branch index found — is this a v2 vault?')
        branch_index = branch_manager.load_branch_index(directory, index_id, read_key)
        branch_meta  = branch_manager.get_branch_by_id(branch_index, branch_id)
        if not branch_meta:
            raise RuntimeError(f'Branch not found: {branch_id}')

        ref_id     = str(branch_meta.head_ref_id)
        parent_id  = ref_manager.read_ref(ref_id, read_key)

        old_tree = Schema__Object_Tree(schema='tree_v1')
        if parent_id:
            vault_commit_reader = Vault__Commit(crypto=self.crypto, pki=pki,
                                                object_store=obj_store, ref_manager=ref_manager)
            old_commit  = vault_commit_reader.load_commit(parent_id, read_key)
            old_tree    = vault_commit_reader.load_tree(str(old_commit.tree_id), read_key)

        new_file_map = self._scan_local_directory(directory)

        old_entries = {}
        for entry in old_tree.entries:
            path = str(entry.path) if entry.path else str(entry.name)
            old_entries[path] = entry

        new_tree = Schema__Object_Tree(schema='tree_v1')
        for path in sorted(new_file_map.keys()):
            local_file = os.path.join(directory, path)
            with open(local_file, 'rb') as f:
                content = f.read()

            old_entry = old_entries.get(path)
            if old_entry and int(old_entry.size) == len(content):
                new_tree.entries.append(Schema__Object_Tree_Entry(path=path, blob_id=str(old_entry.blob_id), size=len(content)))
            else:
                encrypted = self.crypto.encrypt(read_key, content)
                blob_id   = obj_store.store(encrypted)
                new_tree.entries.append(Schema__Object_Tree_Entry(path=path, blob_id=blob_id, size=len(content)))

        signing_key = None
        try:
            signing_key = key_manager.load_private_key_locally(
                str(branch_meta.public_key_id), storage.local_dir(directory))
        except (FileNotFoundError, Exception):
            pass

        vault_commit = Vault__Commit(crypto=self.crypto, pki=pki,
                                     object_store=obj_store, ref_manager=ref_manager)

        auto_msg = message or self._generate_commit_message(old_entries, new_file_map)
        commit_id = vault_commit.create_commit(tree        = new_tree,
                                               read_key    = read_key,
                                               parent_ids  = [parent_id] if parent_id else [],
                                               message     = auto_msg,
                                               branch_id   = branch_id,
                                               signing_key = signing_key)

        ref_manager.write_ref(ref_id, commit_id, read_key)
        ref_manager.write_head(commit_id)

        return dict(commit_id = commit_id,
                    branch_id = branch_id,
                    message   = auto_msg)

    def status_v2(self, directory: str) -> dict:
        vault_key  = self._read_vault_key(directory)
        keys       = self.crypto.derive_keys_from_vault_key(vault_key)
        read_key   = keys['read_key_bytes']
        sg_dir     = os.path.join(directory, SG_VAULT_DIR)

        storage    = Vault__Storage()
        pki        = PKI__Crypto()
        obj_store  = Vault__Object_Store(vault_path=sg_dir, crypto=self.crypto, use_v2=True)
        ref_manager = Vault__Ref_Manager(vault_path=sg_dir, crypto=self.crypto, use_v2=True)

        local_config = self._read_local_config(directory, storage)
        branch_id    = str(local_config.my_branch_id)

        key_manager    = Vault__Key_Manager(vault_path=sg_dir, crypto=self.crypto, pki=pki)
        branch_manager = Vault__Branch_Manager(vault_path=sg_dir, crypto=self.crypto,
                                               key_manager=key_manager, ref_manager=ref_manager,
                                               storage=storage)

        index_id = branch_manager.find_branch_index_id(directory)
        if not index_id:
            return dict(added=[], modified=[], deleted=[], clean=True)
        branch_index = branch_manager.load_branch_index(directory, index_id, read_key)
        branch_meta  = branch_manager.get_branch_by_id(branch_index, branch_id)
        if not branch_meta:
            return dict(added=[], modified=[], deleted=[], clean=True)

        ref_id    = str(branch_meta.head_ref_id)
        parent_id = ref_manager.read_ref(ref_id, read_key)

        old_entries = {}
        if parent_id:
            vault_commit_reader = Vault__Commit(crypto=self.crypto, pki=pki,
                                                object_store=obj_store, ref_manager=ref_manager)
            old_commit = vault_commit_reader.load_commit(parent_id, read_key)
            old_tree   = vault_commit_reader.load_tree(str(old_commit.tree_id), read_key)
            for entry in old_tree.entries:
                path = str(entry.path) if entry.path else str(entry.name)
                old_entries[path] = int(entry.size)

        new_file_map = self._scan_local_directory(directory)

        old_paths = set(old_entries.keys())
        new_paths = set(new_file_map.keys())

        added   = sorted(new_paths - old_paths)
        deleted = sorted(old_paths - new_paths)
        modified = []
        for path in sorted(old_paths & new_paths):
            local_file = os.path.join(directory, path)
            with open(local_file, 'rb') as f:
                content = f.read()
            if len(content) != old_entries[path]:
                modified.append(path)

        return dict(added=added, modified=modified, deleted=deleted,
                    clean=not added and not modified and not deleted)

    def pull_v2(self, directory: str) -> dict:
        """Fetch named branch state and merge into clone branch.

        Workflow:
        1. Read local config to find clone branch
        2. Find named branch in branch index
        3. Read named branch ref (remote state) and clone branch ref (local state)
        4. Find LCA of both heads
        5. Three-way merge: base=LCA tree, ours=clone tree, theirs=named tree
        6. If no conflicts, create merge commit on clone branch
        7. If conflicts, write .conflict files and return conflict info
        8. Update working directory with merged files
        """
        vault_key  = self._read_vault_key(directory)
        keys       = self.crypto.derive_keys_from_vault_key(vault_key)
        read_key   = keys['read_key_bytes']
        sg_dir     = os.path.join(directory, SG_VAULT_DIR)

        storage     = Vault__Storage()
        pki         = PKI__Crypto()
        obj_store   = Vault__Object_Store(vault_path=sg_dir, crypto=self.crypto, use_v2=True)
        ref_manager = Vault__Ref_Manager(vault_path=sg_dir, crypto=self.crypto, use_v2=True)

        local_config   = self._read_local_config(directory, storage)
        clone_branch_id = str(local_config.my_branch_id)

        key_manager    = Vault__Key_Manager(vault_path=sg_dir, crypto=self.crypto, pki=pki)
        branch_manager = Vault__Branch_Manager(vault_path=sg_dir, crypto=self.crypto,
                                               key_manager=key_manager, ref_manager=ref_manager,
                                               storage=storage)

        index_id = branch_manager.find_branch_index_id(directory)
        if not index_id:
            raise RuntimeError('No branch index found')
        branch_index = branch_manager.load_branch_index(directory, index_id, read_key)

        clone_meta = branch_manager.get_branch_by_id(branch_index, clone_branch_id)
        if not clone_meta:
            raise RuntimeError(f'Clone branch not found: {clone_branch_id}')

        named_meta = branch_manager.get_branch_by_name(branch_index, 'current')
        if not named_meta:
            raise RuntimeError('Named branch "current" not found')

        clone_commit_id = ref_manager.read_ref(str(clone_meta.head_ref_id), read_key)
        named_commit_id = ref_manager.read_ref(str(named_meta.head_ref_id), read_key)

        if not named_commit_id:
            return dict(status='up_to_date', message='Named branch has no commits')

        if clone_commit_id == named_commit_id:
            return dict(status='up_to_date', message='Already up to date')

        vault_commit = Vault__Commit(crypto=self.crypto, pki=pki,
                                     object_store=obj_store, ref_manager=ref_manager)
        fetcher      = Vault__Fetch(crypto=self.crypto, api=self.api, storage=storage)
        merger       = Vault__Merge(crypto=self.crypto)

        lca_id = fetcher.find_lca(obj_store, read_key, clone_commit_id, named_commit_id)

        # If LCA is the named commit, clone is already ahead — nothing to pull
        if lca_id == named_commit_id:
            return dict(status='up_to_date', message='Clone branch is ahead of named branch')

        base_tree = Schema__Object_Tree(schema='tree_v1')
        if lca_id:
            lca_commit = vault_commit.load_commit(lca_id, read_key)
            base_tree  = vault_commit.load_tree(str(lca_commit.tree_id), read_key)

        ours_tree = Schema__Object_Tree(schema='tree_v1')
        if clone_commit_id:
            ours_commit = vault_commit.load_commit(clone_commit_id, read_key)
            ours_tree   = vault_commit.load_tree(str(ours_commit.tree_id), read_key)

        named_commit = vault_commit.load_commit(named_commit_id, read_key)
        theirs_tree  = vault_commit.load_tree(str(named_commit.tree_id), read_key)

        merge_result = merger.three_way_merge(base_tree, ours_tree, theirs_tree)
        merged_tree  = merge_result['merged_tree']
        conflicts    = merge_result['conflicts']

        # Write merged files to working directory
        self._checkout_tree(directory, merged_tree, obj_store, read_key)

        # Remove files that were deleted in the merge
        self._remove_deleted_files(directory, ours_tree, merged_tree)

        if conflicts:
            conflict_files = merger.write_conflict_files(directory, conflicts,
                                                         ours_tree, theirs_tree,
                                                         obj_store, read_key)
            # Save merge state for merge_abort
            merge_state = dict(clone_commit_id = clone_commit_id,
                               named_commit_id = named_commit_id,
                               lca_id          = lca_id,
                               conflicts       = conflicts)
            merge_state_path = os.path.join(storage.local_dir(directory), 'merge_state.json')
            with open(merge_state_path, 'w') as f:
                json.dump(merge_state, f, indent=2)

            return dict(status         = 'conflicts',
                        conflicts      = conflicts,
                        conflict_files = conflict_files,
                        added          = merge_result['added'],
                        modified       = merge_result['modified'],
                        deleted        = merge_result['deleted'])

        # No conflicts — create merge commit
        signing_key = None
        try:
            signing_key = key_manager.load_private_key_locally(
                str(clone_meta.public_key_id), storage.local_dir(directory))
        except (FileNotFoundError, Exception):
            pass

        parent_ids = [clone_commit_id, named_commit_id]
        parent_ids = [p for p in parent_ids if p]

        merge_commit_id = vault_commit.create_commit(
            tree        = merged_tree,
            read_key    = read_key,
            parent_ids  = parent_ids,
            message     = f'Merge {str(named_meta.name)} into {str(clone_meta.name)}',
            branch_id   = clone_branch_id,
            signing_key = signing_key)

        ref_manager.write_ref(str(clone_meta.head_ref_id), merge_commit_id, read_key)
        ref_manager.write_head(merge_commit_id)

        return dict(status    = 'merged',
                    commit_id = merge_commit_id,
                    added     = merge_result['added'],
                    modified  = merge_result['modified'],
                    deleted   = merge_result['deleted'],
                    conflicts = [])

    def push_v2(self, directory: str, message: str = '', force: bool = False) -> dict:
        """Push local clone branch state to the named branch.

        Workflow:
        1. Check for uncommitted changes — reject if dirty
        2. Pull first (fetch-first pattern) — merge remote changes
        3. Compute delta between named branch tree and clone branch tree
        4. Upload changed objects via individual API writes
        5. Update named branch ref to match clone branch head
        """
        vault_key  = self._read_vault_key(directory)
        keys       = self.crypto.derive_keys_from_vault_key(vault_key)
        vault_id   = keys['vault_id']
        read_key   = keys['read_key_bytes']
        write_key  = keys['write_key']
        sg_dir     = os.path.join(directory, SG_VAULT_DIR)

        storage     = Vault__Storage()
        pki         = PKI__Crypto()
        obj_store   = Vault__Object_Store(vault_path=sg_dir, crypto=self.crypto, use_v2=True)
        ref_manager = Vault__Ref_Manager(vault_path=sg_dir, crypto=self.crypto, use_v2=True)

        local_config    = self._read_local_config(directory, storage)
        clone_branch_id = str(local_config.my_branch_id)

        key_manager    = Vault__Key_Manager(vault_path=sg_dir, crypto=self.crypto, pki=pki)
        branch_manager = Vault__Branch_Manager(vault_path=sg_dir, crypto=self.crypto,
                                               key_manager=key_manager, ref_manager=ref_manager,
                                               storage=storage)

        index_id = branch_manager.find_branch_index_id(directory)
        if not index_id:
            raise RuntimeError('No branch index found — is this a v2 vault?')
        branch_index = branch_manager.load_branch_index(directory, index_id, read_key)

        clone_meta = branch_manager.get_branch_by_id(branch_index, clone_branch_id)
        if not clone_meta:
            raise RuntimeError(f'Clone branch not found: {clone_branch_id}')

        named_meta = branch_manager.get_branch_by_name(branch_index, 'current')
        if not named_meta:
            raise RuntimeError('Named branch "current" not found')

        # Step 1: Check for uncommitted changes
        status = self.status_v2(directory)
        if not status['clean']:
            raise RuntimeError('Working directory has uncommitted changes. '
                               'Commit your changes before pushing.')

        # Step 2: Pull first (fetch-first pattern)
        if not force:
            pull_result = self.pull_v2(directory)
            if pull_result['status'] == 'conflicts':
                raise RuntimeError('Pull resulted in merge conflicts. '
                                   'Resolve conflicts before pushing.')

        # Re-read refs after pull (pull may have created a merge commit)
        clone_commit_id = ref_manager.read_ref(str(clone_meta.head_ref_id), read_key)
        named_commit_id = ref_manager.read_ref(str(named_meta.head_ref_id), read_key)

        if clone_commit_id == named_commit_id:
            return dict(status='up_to_date', message='Nothing to push')

        if not clone_commit_id:
            return dict(status='up_to_date', message='No commits to push')

        # Step 3: Compute delta — find objects in clone tree not in named tree
        vault_commit = Vault__Commit(crypto=self.crypto, pki=pki,
                                     object_store=obj_store, ref_manager=ref_manager)

        clone_commit = vault_commit.load_commit(clone_commit_id, read_key)
        clone_tree   = vault_commit.load_tree(str(clone_commit.tree_id), read_key)

        named_blob_ids = set()
        if named_commit_id:
            named_commit = vault_commit.load_commit(named_commit_id, read_key)
            named_tree   = vault_commit.load_tree(str(named_commit.tree_id), read_key)
            for entry in named_tree.entries:
                if entry.blob_id:
                    named_blob_ids.add(str(entry.blob_id))

        # Step 4: Upload changed objects
        uploaded_count = 0
        for entry in clone_tree.entries:
            blob_id = str(entry.blob_id) if entry.blob_id else None
            if not blob_id or blob_id in named_blob_ids:
                continue
            ciphertext = obj_store.load(blob_id)
            file_id    = os.urandom(6).hex()
            self.api.write(vault_id, file_id, write_key, ciphertext)
            uploaded_count += 1

        # Also upload the commit chain objects (tree + commits) between clone and named
        fetcher = Vault__Fetch(crypto=self.crypto, api=self.api, storage=storage)
        commit_chain = fetcher.fetch_commit_chain(obj_store, read_key, clone_commit_id,
                                                   stop_at=named_commit_id)
        for cid in commit_chain:
            if cid == named_commit_id:
                continue
            # Upload commit object
            commit_ciphertext = obj_store.load(cid)
            self.api.write(vault_id, os.urandom(6).hex(), write_key, commit_ciphertext)
            # Upload tree object for this commit
            c = vault_commit.load_commit(cid, read_key)
            tree_id = str(c.tree_id)
            tree_ciphertext = obj_store.load(tree_id)
            self.api.write(vault_id, os.urandom(6).hex(), write_key, tree_ciphertext)

        # Step 5: Update named branch ref to match clone branch head
        ref_manager.write_ref(str(named_meta.head_ref_id), clone_commit_id, read_key)

        return dict(status         = 'pushed',
                    commit_id      = clone_commit_id,
                    objects_uploaded = uploaded_count,
                    commits_pushed  = len([c for c in commit_chain if c != named_commit_id]))

    def merge_abort(self, directory: str) -> dict:
        """Abort an in-progress merge by restoring the pre-merge state."""
        vault_key  = self._read_vault_key(directory)
        keys       = self.crypto.derive_keys_from_vault_key(vault_key)
        read_key   = keys['read_key_bytes']
        sg_dir     = os.path.join(directory, SG_VAULT_DIR)

        storage     = Vault__Storage()
        pki         = PKI__Crypto()
        obj_store   = Vault__Object_Store(vault_path=sg_dir, crypto=self.crypto, use_v2=True)
        ref_manager = Vault__Ref_Manager(vault_path=sg_dir, crypto=self.crypto, use_v2=True)
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
            ours_tree   = vault_commit.load_tree(str(ours_commit.tree_id), read_key)
            self._checkout_tree(directory, ours_tree, obj_store, read_key)

        removed = merger.remove_conflict_files(directory)
        os.remove(merge_state_path)

        return dict(status          = 'aborted',
                    restored_commit = clone_commit_id,
                    removed_files   = removed)

    def _checkout_tree(self, directory: str, tree: Schema__Object_Tree,
                       obj_store: Vault__Object_Store, read_key: bytes) -> None:
        """Write all files from a tree to the working directory."""
        for entry in tree.entries:
            path    = str(entry.path) if entry.path else str(entry.name)
            blob_id = str(entry.blob_id) if entry.blob_id else None
            if not blob_id:
                continue
            try:
                ciphertext = obj_store.load(blob_id)
                plaintext  = self.crypto.decrypt(read_key, ciphertext)
                full_path  = os.path.join(directory, path)
                os.makedirs(os.path.dirname(full_path), exist_ok=True)
                with open(full_path, 'wb') as f:
                    f.write(plaintext)
            except Exception:
                pass

    def _remove_deleted_files(self, directory: str, old_tree: Schema__Object_Tree,
                              new_tree: Schema__Object_Tree) -> None:
        """Remove files that exist in old_tree but not in new_tree."""
        old_paths = set()
        for entry in old_tree.entries:
            path = str(entry.path) if entry.path else str(entry.name)
            old_paths.add(path)

        new_paths = set()
        for entry in new_tree.entries:
            path = str(entry.path) if entry.path else str(entry.name)
            new_paths.add(path)

        for path in old_paths - new_paths:
            full_path = os.path.join(directory, path)
            if os.path.isfile(full_path):
                os.remove(full_path)

    def _read_local_config(self, directory: str, storage: Vault__Storage) -> Schema__Local_Config:
        config_path = storage.local_config_path(directory)
        with open(config_path, 'r') as f:
            data = json.load(f)
        return Schema__Local_Config.from_json(data)

    def _generate_commit_message(self, old_entries: dict, new_file_map: dict) -> str:
        old_paths = set(old_entries.keys())
        new_paths = set(new_file_map.keys())
        added     = len(new_paths - old_paths)
        deleted   = len(old_paths - new_paths)
        modified  = 0
        for path in old_paths & new_paths:
            old_size = int(old_entries[path].size) if hasattr(old_entries[path], 'size') else old_entries[path].get('size', -1) if isinstance(old_entries[path], dict) else -1
            new_size = new_file_map[path].get('size', -2)
            if old_size != new_size:
                modified += 1
        return f'Commit: {added} added, {modified} modified, {deleted} deleted'

    # --- internal helpers ---

    def _download_and_decrypt(self, vault_id: str, file_id: str, read_key: bytes) -> bytes:
        encrypted = self.api.read(vault_id, file_id)
        return self.crypto.decrypt(read_key, encrypted)

    def _read_vault_key(self, directory: str) -> str:
        vault_key_path = os.path.join(directory, SG_VAULT_DIR, VAULT_KEY_FILE)
        with open(vault_key_path, 'r') as f:
            return f.read().strip()

    def _get_read_key(self, directory: str) -> bytes:
        vault_key = self._read_vault_key(directory)
        keys      = self.crypto.derive_keys_from_vault_key(vault_key)
        return keys['read_key_bytes']

    def _read_local_tree(self, directory: str) -> dict:
        tree_path = os.path.join(directory, SG_VAULT_DIR, TREE_FILE)
        with open(tree_path, 'r') as f:
            return json.load(f)

    def _read_local_settings(self, directory: str) -> dict:
        settings_path = os.path.join(directory, SG_VAULT_DIR, SETTINGS_FILE)
        with open(settings_path, 'r') as f:
            return json.load(f)

    def _read_local_tree_from_objects(self, vault_path: str, read_key: bytes) -> dict:
        """Read the tree from the object store (new format).

        Returns a dict of {path: {blob_id, size, file_id}} where file_id comes
        from the legacy tree.json for server-side compatibility.
        """
        ref_manager  = Vault__Ref_Manager(vault_path=vault_path)
        object_store = Vault__Object_Store(vault_path=vault_path, crypto=self.crypto)

        commit_id = ref_manager.read_head()
        if not commit_id:
            return {}

        commit_data = self.crypto.decrypt(read_key, object_store.load(commit_id))
        commit      = Schema__Object_Commit.from_json(json.loads(commit_data))
        tree_data   = self.crypto.decrypt(read_key, object_store.load(str(commit.tree_id)))
        tree        = Schema__Object_Tree.from_json(json.loads(tree_data))

        legacy_tree = {}
        tree_json_path = os.path.join(vault_path, TREE_FILE)
        if os.path.isfile(tree_json_path):
            with open(tree_json_path, 'r') as f:
                legacy_data = json.load(f)
            legacy_tree = self._flatten_tree(legacy_data.get('tree', {}))

        result = {}
        for entry in tree.entries:
            path    = str(entry.path)
            blob_id = str(entry.blob_id)
            size    = int(entry.size)
            file_id = legacy_tree.get(path, {}).get('file_id', '')
            result[path] = dict(blob_id=blob_id, size=size, file_id=file_id)

        return result

    def _flatten_tree(self, tree: dict, prefix: str = '') -> dict:
        result = {}
        for name, node in tree.items():
            if name == '/':
                result.update(self._flatten_tree(node.get('children', {}), prefix))
            elif node.get('type') == 'folder':
                child_prefix = f'{prefix}{name}/' if prefix else f'{name}/'
                result.update(self._flatten_tree(node.get('children', {}), child_prefix))
            elif node.get('type') == 'file':
                path = f'{prefix}{name}'
                result[path] = node
        return result

    def _scan_local_directory(self, directory: str) -> dict:
        result = {}
        for root, dirs, files in os.walk(directory):
            dirs[:] = [d for d in dirs if d != SG_VAULT_DIR and not d.startswith('.')]
            for filename in files:
                if filename.startswith('.'):
                    continue
                full_path = os.path.join(root, filename)
                rel_path  = os.path.relpath(full_path, directory)
                rel_path  = rel_path.replace(os.sep, '/')
                result[rel_path] = dict(size=os.path.getsize(full_path))
        return result

    def _build_tree_json(self, old_tree_data: dict, old_file_map: dict,
                         uploaded: dict, deleted: set) -> dict:
        now = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.000Z')
        all_files = {}
        for path, info in old_file_map.items():
            if path not in deleted:
                all_files[path] = info
        for path, info in uploaded.items():
            all_files[path] = dict(type    = 'file',
                                   file_id = info['file_id'],
                                   size    = info['size'],
                                   uploaded= now)

        tree = {'/': {'type': 'folder', 'children': {}}}
        for path, info in sorted(all_files.items()):
            parts   = path.split('/')
            current = tree['/']['children']
            for part in parts[:-1]:
                if part not in current:
                    current[part] = {'type': 'folder', 'children': {}}
                current = current[part]['children']
            current[parts[-1]] = info

        version = old_tree_data.get('version', 0) + 1
        return dict(version=version, updated=now, tree=tree)
