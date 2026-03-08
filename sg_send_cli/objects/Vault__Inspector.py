import json
import os
from osbot_utils.type_safe.Type_Safe          import Type_Safe
from sg_send_cli.crypto.Vault__Crypto         import Vault__Crypto
from sg_send_cli.objects.Vault__Object_Store  import Vault__Object_Store
from sg_send_cli.objects.Vault__Ref_Manager   import Vault__Ref_Manager
from sg_send_cli.schemas.Schema__Object_Commit import Schema__Object_Commit
from sg_send_cli.schemas.Schema__Object_Tree   import Schema__Object_Tree
from sg_send_cli.schemas.Schema__Object_Ref    import Schema__Object_Ref

SG_VAULT_DIR = '.sg_vault'


class Vault__Inspector(Type_Safe):
    crypto : Vault__Crypto

    def inspect_vault(self, directory: str) -> dict:
        vault_path    = os.path.join(directory, SG_VAULT_DIR)
        object_store  = Vault__Object_Store(vault_path=vault_path, crypto=self.crypto)
        ref_manager   = Vault__Ref_Manager(vault_path=vault_path)
        has_sg_vault  = os.path.isdir(vault_path)
        has_legacy    = has_sg_vault and os.path.isfile(os.path.join(vault_path, 'tree.json'))
        has_refs      = ref_manager.is_initialized()
        if not has_sg_vault:
            vault_format = 'none'
        elif has_refs:
            vault_format = 'object-store'
        elif has_legacy:
            vault_format = 'legacy'
        else:
            vault_format = 'uninitialized'

        commit_id    = ref_manager.read_head() if has_refs else None
        obj_count    = object_store.object_count()
        total_size   = object_store.total_size()
        tree_entries = 0
        version      = 0
        tree_path    = os.path.join(vault_path, 'tree.json')
        if os.path.isfile(tree_path):
            with open(tree_path, 'r') as f:
                tree_data    = json.load(f)
                version      = tree_data.get('version', 0)

        return dict(vault_format  = vault_format,
                    commit_id     = commit_id,
                    version       = version,
                    object_count  = obj_count,
                    total_size    = total_size,
                    tree_entries  = tree_entries,
                    directory     = os.path.abspath(directory))

    def inspect_object(self, directory: str, object_id: str) -> dict:
        vault_path   = os.path.join(directory, SG_VAULT_DIR)
        object_store = Vault__Object_Store(vault_path=vault_path, crypto=self.crypto)
        exists       = object_store.exists(object_id)
        path         = object_store.object_path(object_id)

        result = dict(object_id = object_id,
                      exists    = exists,
                      path      = path)

        if exists:
            ciphertext = object_store.load(object_id)
            full_hash  = self.crypto.hash_data(ciphertext)
            computed   = self.crypto.compute_object_id(ciphertext)
            result.update(size_bytes     = len(ciphertext),
                          sha256         = full_hash,
                          computed_id    = computed,
                          integrity_ok   = computed == object_id)
        return result

    def inspect_tree(self, directory: str, read_key: bytes = None) -> dict:
        vault_path   = os.path.join(directory, SG_VAULT_DIR)
        object_store = Vault__Object_Store(vault_path=vault_path, crypto=self.crypto)
        ref_manager  = Vault__Ref_Manager(vault_path=vault_path)
        commit_id    = ref_manager.read_head()

        if not commit_id:
            return dict(commit_id=None, entries=[], file_count=0, total_size=0)

        if not read_key:
            return dict(commit_id=commit_id, error='read_key required to decrypt tree')

        commit_data  = self._decrypt_object(object_store, commit_id, read_key)
        commit       = Schema__Object_Commit.from_json(json.loads(commit_data))
        tree_id      = str(commit.tree_id)
        tree_data    = self._decrypt_object(object_store, tree_id, read_key)
        tree         = Schema__Object_Tree.from_json(json.loads(tree_data))

        entries    = []
        total_size = 0
        for entry in tree.entries:
            entry_dict = dict(path=str(entry.path), blob_id=str(entry.blob_id), size=int(entry.size))
            entries.append(entry_dict)
            total_size += int(entry.size)

        return dict(commit_id  = commit_id,
                    tree_id    = tree_id,
                    entries    = entries,
                    file_count = len(entries),
                    total_size = total_size)

    def inspect_commit_chain(self, directory: str, read_key: bytes = None, limit: int = 50) -> list:
        vault_path   = os.path.join(directory, SG_VAULT_DIR)
        object_store = Vault__Object_Store(vault_path=vault_path, crypto=self.crypto)
        ref_manager  = Vault__Ref_Manager(vault_path=vault_path)
        commit_id    = ref_manager.read_head()

        if not commit_id:
            return []
        if not read_key:
            return [dict(commit_id=commit_id, error='read_key required to decrypt chain')]

        chain = []
        current_id = commit_id
        count = 0
        while current_id and count < limit:
            if not object_store.exists(current_id):
                chain.append(dict(commit_id=current_id, error='object not found locally'))
                break
            commit_data = self._decrypt_object(object_store, current_id, read_key)
            commit      = Schema__Object_Commit.from_json(json.loads(commit_data))
            chain.append(dict(commit_id = current_id,
                              version   = int(commit.version),
                              timestamp = str(commit.timestamp) if commit.timestamp else None,
                              message   = str(commit.message) if commit.message else None,
                              tree_id   = str(commit.tree_id) if commit.tree_id else None,
                              parent    = str(commit.parent) if commit.parent else None))
            current_id = str(commit.parent) if commit.parent else None
            count += 1

        return chain

    def object_store_stats(self, directory: str) -> dict:
        vault_path   = os.path.join(directory, SG_VAULT_DIR)
        object_store = Vault__Object_Store(vault_path=vault_path, crypto=self.crypto)
        all_ids      = object_store.all_object_ids()
        buckets      = {}
        total_bytes  = 0

        for oid in all_ids:
            prefix = oid[:2]
            buckets[prefix] = buckets.get(prefix, 0) + 1
            if object_store.exists(oid):
                total_bytes += os.path.getsize(object_store.object_path(oid))

        return dict(total_objects = len(all_ids),
                    total_bytes   = total_bytes,
                    buckets       = buckets)

    def format_vault_summary(self, directory: str) -> str:
        info  = self.inspect_vault(directory)
        lines = ['=== Vault Summary ===',
                 f'  Directory:    {info["directory"]}',
                 f'  Format:       {info["vault_format"]}',
                 f'  Version:      {info["version"]}',
                 f'  HEAD:         {info["commit_id"] or "(none)"}',
                 f'  Objects:      {info["object_count"]}',
                 f'  Cache size:   {info["total_size"]} bytes']
        return '\n'.join(lines)

    def format_object_detail(self, directory: str, object_id: str) -> str:
        info  = self.inspect_object(directory, object_id)
        lines = [f'=== Object: {object_id} ===',
                 f'  Exists:       {info["exists"]}',
                 f'  Path:         {info["path"]}']
        if info['exists']:
            lines.extend([f'  Size:         {info["size_bytes"]} bytes',
                          f'  SHA-256:      {info["sha256"]}',
                          f'  Computed ID:  {info["computed_id"]}',
                          f'  Integrity:    {"OK" if info["integrity_ok"] else "FAILED"}'])
        return '\n'.join(lines)

    def format_commit_log(self, chain: list) -> str:
        if not chain:
            return '(no commits)'
        lines = []
        for i, c in enumerate(chain):
            if 'error' in c:
                lines.append(f'  commit {c["commit_id"]}  [{c["error"]}]')
                continue
            head_marker = ' (HEAD)' if i == 0 else ''
            lines.append(f'  commit {c["commit_id"]}{head_marker}')
            lines.append(f'  Version:   {c["version"]}')
            if c.get('timestamp'):
                lines.append(f'  Date:      {c["timestamp"]}')
            if c.get('message'):
                lines.append(f'  Message:   {c["message"]}')
            lines.append(f'  Tree:      {c["tree_id"]}')
            lines.append('')
        return '\n'.join(lines)

    def cat_object(self, directory: str, object_id: str, read_key: bytes) -> dict:
        vault_path   = os.path.join(directory, SG_VAULT_DIR)
        object_store = Vault__Object_Store(vault_path=vault_path, crypto=self.crypto)

        if not object_store.exists(object_id):
            return dict(object_id=object_id, exists=False)

        plaintext = self._decrypt_object(object_store, object_id, read_key)

        try:
            parsed      = json.loads(plaintext)
            object_type = self._detect_object_type(parsed)
            return dict(object_id   = object_id,
                        exists      = True,
                        type        = object_type,
                        size_bytes  = len(plaintext),
                        content     = parsed)
        except (json.JSONDecodeError, UnicodeDecodeError):
            pass

        try:
            text = plaintext.decode('utf-8')
            return dict(object_id   = object_id,
                        exists      = True,
                        type        = 'blob',
                        size_bytes  = len(plaintext),
                        content     = text)
        except UnicodeDecodeError:
            return dict(object_id   = object_id,
                        exists      = True,
                        type        = 'blob (binary)',
                        size_bytes  = len(plaintext),
                        content     = plaintext.hex())

    def format_cat_object(self, directory: str, object_id: str, read_key: bytes) -> str:
        info  = self.cat_object(directory, object_id, read_key)
        if not info.get('exists'):
            return f'Object {object_id}: not found'
        lines = [f'=== Object: {object_id} ===',
                 f'  Type:   {info["type"]}',
                 f'  Size:   {info["size_bytes"]} bytes',
                 f'  ---']
        content = info['content']
        if isinstance(content, dict) or isinstance(content, list):
            lines.append(json.dumps(content, indent=2))
        else:
            lines.append(str(content))
        return '\n'.join(lines)

    def _detect_object_type(self, parsed: dict) -> str:
        if isinstance(parsed, dict):
            if 'tree_id' in parsed and 'version' in parsed:
                return 'commit'
            if 'entries' in parsed:
                return 'tree'
        return 'blob (json)'

    def _decrypt_object(self, object_store, object_id: str, read_key: bytes) -> bytes:
        ciphertext = object_store.load(object_id)
        return self.crypto.decrypt(read_key, ciphertext)
