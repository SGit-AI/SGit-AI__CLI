import json
import os
from osbot_utils.type_safe.Type_Safe          import Type_Safe
from sg_send_cli.crypto.Vault__Crypto         import Vault__Crypto
from sg_send_cli.objects.Vault__Object_Store  import Vault__Object_Store
from sg_send_cli.objects.Vault__Ref_Manager   import Vault__Ref_Manager
from sg_send_cli.schemas.Schema__Object_Commit import Schema__Object_Commit
from sg_send_cli.schemas.Schema__Object_Tree   import Schema__Object_Tree
from sg_send_cli.schemas.Schema__Object_Ref    import Schema__Object_Ref
from sg_send_cli.sync.Vault__Storage           import SG_VAULT_DIR


class Vault__Inspector(Type_Safe):
    crypto : Vault__Crypto

    def _is_v2(self, vault_path: str) -> bool:
        return os.path.isdir(os.path.join(vault_path, 'bare'))

    def _make_stores(self, directory: str):
        vault_path = os.path.join(directory, SG_VAULT_DIR)
        v2         = self._is_v2(vault_path)
        obj_store  = Vault__Object_Store(vault_path=vault_path, crypto=self.crypto, use_v2=v2)
        ref_mgr    = Vault__Ref_Manager(vault_path=vault_path, crypto=self.crypto, use_v2=v2)
        return vault_path, obj_store, ref_mgr

    def inspect_vault(self, directory: str) -> dict:
        vault_path, object_store, ref_manager = self._make_stores(directory)
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

        commit_id    = ref_manager.read_head() if has_refs else None  # basic info, no read_key available here
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
        vault_path, object_store, _ = self._make_stores(directory)
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
        vault_path, object_store, ref_manager = self._make_stores(directory)
        commit_id    = self._resolve_head(directory, ref_manager, read_key)

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
        vault_path, object_store, ref_manager = self._make_stores(directory)
        commit_id    = self._resolve_head(directory, ref_manager, read_key)

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
        vault_path, object_store, _ = self._make_stores(directory)
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

    def format_commit_log(self, chain: list, oneline: bool = False, graph: bool = False) -> str:
        if not chain:
            return '(no commits)'
        lines = []
        total = len(chain)
        for i, c in enumerate(chain):
            if 'error' in c:
                if graph:
                    lines.append(f'  * {c["commit_id"]}  [{c["error"]}]')
                else:
                    lines.append(f'  commit {c["commit_id"]}  [{c["error"]}]')
                continue

            head_marker = ' (HEAD)' if i == 0 else ''
            message     = c.get('message') or ''

            if oneline and not graph:
                lines.append(f'  {c["commit_id"]}{head_marker} {message}')
            elif graph:
                is_last = (i == total - 1)
                prefix  = '  *' if not is_last else '  *'
                connector = '  |' if not is_last else '   '
                lines.append(f'{prefix} {c["commit_id"]}{head_marker} v{c["version"]} {message}')
                if not oneline:
                    if c.get('timestamp'):
                        lines.append(f'{connector}   Date: {c["timestamp"]}')
                    lines.append(f'{connector}   Tree: {c["tree_id"]}')
                if not is_last:
                    lines.append(f'{connector}')
            else:
                lines.append(f'  commit {c["commit_id"]}{head_marker}')
                lines.append(f'  Version:   {c["version"]}')
                if c.get('timestamp'):
                    lines.append(f'  Date:      {c["timestamp"]}')
                if message:
                    lines.append(f'  Message:   {message}')
                lines.append(f'  Tree:      {c["tree_id"]}')
                lines.append('')
        return '\n'.join(lines)

    def cat_object(self, directory: str, object_id: str, read_key: bytes) -> dict:
        vault_path, object_store, _ = self._make_stores(directory)

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

        if info['type'] == 'commit' and isinstance(content, dict) and content.get('tree_id'):
            tree_info = self.cat_object(directory, content['tree_id'], read_key)
            if tree_info.get('exists') and tree_info['type'] == 'tree':
                lines.append('')
                lines.append(f'  Tree {content["tree_id"]} entries:')
                for entry in tree_info['content'].get('entries', []):
                    lines.append(f'    {entry["blob_id"]}  {entry.get("size", "?"):>8}  {entry["path"]}')

            chain    = self.inspect_commit_chain(directory, read_key)
            child_id = self._find_child_commit(chain, object_id)
            if child_id:
                lines.append('')
                lines.append(f'  Child:  {child_id}')
            parent = content.get('parent')
            if parent:
                lines.append(f'  Parent: {parent}')
            else:
                lines.append(f'  Parent: (root commit)')

        return '\n'.join(lines)

    def _find_child_commit(self, chain: list, commit_id: str) -> str:
        for i in range(1, len(chain)):
            if chain[i].get('commit_id') == commit_id:
                return chain[i-1]['commit_id']
        return None

    def _detect_object_type(self, parsed: dict) -> str:
        if isinstance(parsed, dict):
            if 'tree_id' in parsed and 'version' in parsed:
                return 'commit'
            if 'entries' in parsed:
                return 'tree'
        return 'blob (json)'

    def _resolve_head(self, directory: str, ref_manager: Vault__Ref_Manager, read_key: bytes = None) -> str:
        """Resolve HEAD commit ID for v1 (legacy refs/head) or v2 (encrypted branch refs)."""
        head = ref_manager.read_head()
        if head:
            return head
        if not read_key:
            return None
        vault_path = os.path.join(directory, SG_VAULT_DIR)
        config_path = os.path.join(vault_path, 'local', 'config.json')
        if not os.path.isfile(config_path):
            return None
        with open(config_path) as f:
            config = json.load(f)
        branch_id = config.get('my_branch_id', '')
        from sg_send_cli.sync.Vault__Branch_Manager import Vault__Branch_Manager
        from sg_send_cli.crypto.Vault__Key_Manager  import Vault__Key_Manager
        from sg_send_cli.crypto.PKI__Crypto         import PKI__Crypto
        from sg_send_cli.sync.Vault__Storage        import Vault__Storage
        storage        = Vault__Storage()
        pki            = PKI__Crypto()
        key_manager    = Vault__Key_Manager(vault_path=vault_path, crypto=self.crypto, pki=pki)
        branch_manager = Vault__Branch_Manager(vault_path    = vault_path,
                                                crypto        = self.crypto,
                                                key_manager   = key_manager,
                                                ref_manager   = ref_manager,
                                                storage       = storage)
        index_id = branch_manager.find_branch_index_id(directory)
        if not index_id:
            return None
        branch_index = branch_manager.load_branch_index(directory, index_id, read_key)
        branch_meta  = branch_manager.get_branch_by_id(branch_index, branch_id)
        if not branch_meta:
            return None
        return ref_manager.read_ref(str(branch_meta.head_ref_id), read_key)

    def _decrypt_object(self, object_store, object_id: str, read_key: bytes) -> bytes:
        ciphertext = object_store.load(object_id)
        return self.crypto.decrypt(read_key, ciphertext)
