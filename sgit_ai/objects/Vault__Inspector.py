import json
import os
from osbot_utils.type_safe.Type_Safe          import Type_Safe
from sgit_ai.crypto.Vault__Crypto         import Vault__Crypto
from sgit_ai.objects.Vault__Object_Store  import Vault__Object_Store
from sgit_ai.objects.Vault__Ref_Manager   import Vault__Ref_Manager
from sgit_ai.schemas.Schema__Object_Commit import Schema__Object_Commit
from sgit_ai.schemas.Schema__Object_Tree   import Schema__Object_Tree
from sgit_ai.schemas.Schema__Object_Ref    import Schema__Object_Ref
from sgit_ai.sync.Vault__Storage           import SG_VAULT_DIR


class Vault__Inspector(Type_Safe):
    crypto : Vault__Crypto

    def _make_stores(self, directory: str):
        vault_path = os.path.join(directory, SG_VAULT_DIR)
        obj_store  = Vault__Object_Store(vault_path=vault_path, crypto=self.crypto)
        ref_mgr    = Vault__Ref_Manager(vault_path=vault_path, crypto=self.crypto)
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

        commit_id    = None
        obj_count    = object_store.object_count()
        total_size   = object_store.total_size()

        return dict(vault_format  = vault_format,
                    commit_id     = commit_id,
                    object_count  = obj_count,
                    total_size    = total_size,
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

        # Use sub-tree flattener to resolve nested trees into flat paths
        from sgit_ai.sync.Vault__Sub_Tree import Vault__Sub_Tree
        sub_tree     = Vault__Sub_Tree(crypto=self.crypto, obj_store=object_store)
        flat_entries = sub_tree.flatten(tree_id, read_key)

        entries    = []
        total_size = 0
        for path, entry in sorted(flat_entries.items()):
            entry_dict = dict(path=path, blob_id=entry['blob_id'], size=entry['size'])
            entries.append(entry_dict)
            total_size += entry['size']

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

            message = None
            if commit.message_enc:
                try:
                    message = self.crypto.decrypt_metadata(read_key, str(commit.message_enc))
                except Exception:
                    message = '[encrypted]'

            parents = [str(p) for p in commit.parents] if commit.parents else []

            chain.append(dict(commit_id    = current_id,
                              timestamp_ms = int(commit.timestamp_ms) if commit.timestamp_ms else 0,
                              message      = message,
                              tree_id      = str(commit.tree_id) if commit.tree_id else None,
                              parents      = parents))
            current_id = parents[0] if parents else None
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
            parents     = c.get('parents', [])

            if oneline and not graph:
                lines.append(f'  {c["commit_id"]}{head_marker} {message}')
            elif graph:
                is_last   = (i == total - 1)
                prefix    = '  *'
                connector = '  |' if not is_last else '   '
                lines.append(f'{prefix} {c["commit_id"]}{head_marker} {message}')
                if not oneline:
                    if c.get('timestamp_ms'):
                        from datetime import datetime, timezone
                        dt = datetime.fromtimestamp(c['timestamp_ms'] / 1000, tz=timezone.utc)
                        lines.append(f'{connector}   Date: {dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")}')
                    lines.append(f'{connector}   Tree: {c["tree_id"]}')
                if not is_last:
                    lines.append(f'{connector}')
            else:
                lines.append(f'  commit {c["commit_id"]}{head_marker}')
                if c.get('timestamp_ms'):
                    from datetime import datetime, timezone
                    dt = datetime.fromtimestamp(c['timestamp_ms'] / 1000, tz=timezone.utc)
                    lines.append(f'  Date:      {dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")}')
                if message:
                    lines.append(f'  Message:   {message}')
                lines.append(f'  Tree:      {c["tree_id"]}')
                if parents:
                    lines.append(f'  Parents:   {", ".join(parents)}')
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
                    name_enc = entry.get('name_enc', '[encrypted]')
                    blob_id  = entry.get('blob_id', '')
                    tree_id  = entry.get('tree_id', '')
                    eid      = blob_id or tree_id
                    etype    = 'blob' if blob_id else 'tree'
                    lines.append(f'    {eid}  {etype}  {name_enc[:20]}...')

            chain    = self.inspect_commit_chain(directory, read_key)
            child_id = self._find_child_commit(chain, object_id)
            if child_id:
                lines.append('')
                lines.append(f'  Child:   {child_id}')
            parents = content.get('parents', [])
            if parents:
                lines.append(f'  Parents: {", ".join(parents)}')
            else:
                lines.append(f'  Parents: (root commit)')

        return '\n'.join(lines)

    def _find_child_commit(self, chain: list, commit_id: str) -> str:
        for i in range(1, len(chain)):
            if chain[i].get('commit_id') == commit_id:
                return chain[i-1]['commit_id']
        return None

    def _detect_object_type(self, parsed: dict) -> str:
        if isinstance(parsed, dict):
            if 'tree_id' in parsed and ('timestamp_ms' in parsed or 'schema' in parsed):
                return 'commit'
            if 'entries' in parsed:
                return 'tree'
        return 'blob (json)'

    def _resolve_head(self, directory: str, ref_manager: Vault__Ref_Manager, read_key: bytes = None) -> str:
        """Resolve HEAD commit ID from encrypted branch refs."""
        if not read_key:
            return None
        vault_path = os.path.join(directory, SG_VAULT_DIR)
        config_path = os.path.join(vault_path, 'local', 'config.json')
        if not os.path.isfile(config_path):
            return None
        with open(config_path) as f:
            config = json.load(f)
        branch_id = config.get('my_branch_id', '')
        from sgit_ai.sync.Vault__Branch_Manager import Vault__Branch_Manager
        from sgit_ai.crypto.Vault__Key_Manager  import Vault__Key_Manager
        from sgit_ai.crypto.PKI__Crypto         import PKI__Crypto
        from sgit_ai.sync.Vault__Storage        import Vault__Storage
        storage        = Vault__Storage()
        pki            = PKI__Crypto()
        key_manager    = Vault__Key_Manager(vault_path=vault_path, crypto=self.crypto, pki=pki)
        branch_manager = Vault__Branch_Manager(vault_path    = vault_path,
                                                crypto        = self.crypto,
                                                key_manager   = key_manager,
                                                ref_manager   = ref_manager,
                                                storage       = storage)
        index_id = None
        indexes_dir = storage.bare_indexes_dir(directory)
        if os.path.isdir(indexes_dir):
            for name in sorted(os.listdir(indexes_dir)):
                if name.startswith('idx-pid-muw-'):
                    index_id = name
                    break
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
