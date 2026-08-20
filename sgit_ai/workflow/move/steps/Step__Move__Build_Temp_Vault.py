import json
import os
import shutil

from sgit_ai.safe_types.Safe_Str__File_Path      import Safe_Str__File_Path
from sgit_ai.safe_types.Safe_Str__Step_Name      import Safe_Str__Step_Name
from sgit_ai.schemas.workflow.move.Schema__Move__State import Schema__Move__State
from sgit_ai.workflow.Step                       import Step

SG_VAULT_NEW  = '.sg_vault_new'
MOVE_HIST     = 'move-history.json'


class Step__Move__Build_Temp_Vault(Step):
    name          = Safe_Str__Step_Name('build-temp-vault')
    input_schema  = Schema__Move__State
    output_schema = Schema__Move__State

    def execute(self, input: Schema__Move__State, workspace) -> Schema__Move__State:
        from sgit_ai.crypto.Vault__Crypto          import Vault__Crypto
        from sgit_ai.storage.Vault__Object_Store   import Vault__Object_Store
        from sgit_ai.storage.Vault__Storage        import Vault__Storage
        from sgit_ai.schemas.move.Schema__Vault_Move_Record import Schema__Vault_Move_Record
        from sgit_ai.schemas.move.Schema__Vault_Moves       import Schema__Vault_Moves
        from sgit_ai.safe_types.Safe_Str__Base_URL          import Safe_Str__Base_URL
        from sgit_ai.safe_types.Safe_Str__Vault_Id          import Safe_Str__Vault_Id
        from sgit_ai.safe_types.Safe_UInt__Vault_Version    import Safe_UInt__Vault_Version
        from sgit_ai.safe_types.Safe_Str__ISO_Timestamp     import Safe_Str__ISO_Timestamp
        from sgit_ai.safe_types.Safe_Str__Commit_Message    import Safe_Str__Commit_Message
        from sgit_ai.network.api.Vault__API                 import DEFAULT_BASE_URL
        from datetime import datetime, timezone

        directory    = str(input.directory)
        new_vault_key = str(input.new_vault_key)
        target_api   = str(input.target_api_url) if input.target_api_url else None

        storage      = Vault__Storage()
        sg_dir       = storage.sg_vault_dir(directory)
        new_sg_dir   = os.path.join(directory, SG_VAULT_NEW)

        if input.dry_run:
            state_dict = input.json()
            state_dict['temp_vault_dir'] = new_sg_dir
            return Schema__Move__State.from_json(state_dict)

        if os.path.exists(new_sg_dir):
            shutil.rmtree(new_sg_dir)

        crypto   = Vault__Crypto()
        old_keys = self._read_old_keys(directory, storage, crypto)
        new_keys = crypto.derive_keys_from_vault_key(new_vault_key)

        old_read_key = old_keys['read_key_bytes']
        new_read_key = new_keys['read_key_bytes']

        new_sg_obj_store = Vault__Object_Store(vault_path=new_sg_dir, crypto=crypto)

        self._copy_structure(sg_dir, new_sg_dir)
        id_map = self._rewrite_object_graph(sg_dir, new_sg_dir, old_read_key, new_read_key, crypto)
        self._migrate_refs_and_index(
            sg_dir, new_sg_dir, old_read_key, new_read_key,
            old_keys.get('branch_index_file_id', ''),
            new_keys.get('branch_index_file_id', ''),
            crypto, id_map,
        )
        self._reencrypt_keys(sg_dir, new_sg_dir, old_read_key, new_read_key, crypto)

        self._write_vault_key_file(new_sg_dir, new_vault_key)
        self._write_move_history(
            sg_dir, new_sg_dir,
            old_vault_id  = str(input.old_vault_id) if input.old_vault_id else '',
            new_vault_id  = str(input.new_vault_id) if input.new_vault_id else '',
            old_api_url   = str(input.old_api_url) if input.old_api_url else DEFAULT_BASE_URL,
            target_api    = target_api or (str(input.old_api_url) if input.old_api_url else DEFAULT_BASE_URL),
            key_generation = int(input.key_generation) if input.key_generation else 1,
            reason        = str(input.reason) if input.reason else '',
        )

        self._update_local_config(
            sg_dir, new_sg_dir,
            new_vault_id    = str(input.new_vault_id) if input.new_vault_id else '',
            key_generation  = int(input.key_generation) if input.key_generation else 1,
            target_api      = target_api or (str(input.old_api_url) if input.old_api_url else DEFAULT_BASE_URL),
        )

        state_dict = input.json()
        state_dict['temp_vault_dir'] = new_sg_dir
        return Schema__Move__State.from_json(state_dict)

    def _read_old_keys(self, directory, storage, crypto):
        vault_key_path = storage.vault_key_path(directory)
        with open(vault_key_path) as f:
            vault_key = f.read().strip()
        return crypto.derive_keys_from_vault_key(vault_key)

    def _copy_structure(self, sg_dir: str, new_sg_dir: str) -> None:
        # bare/cache/ is DELIBERATELY not carried across (cache-layer decision D7).
        # Every cache id is HMAC(read_key, ...) and every cache object is encrypted
        # under read_key, so a rekey invalidates the entire cache layer by
        # construction: the old ids are unreachable with the new key and the old
        # ciphertexts undecryptable. Rebuilding is `sgit cache repair`'s job — the
        # declarations are re-created against the new key, not migrated.
        for sub in ('bare/data', 'bare/refs', 'bare/indexes', 'bare/keys',
                    'bare/pending', 'local'):
            os.makedirs(os.path.join(new_sg_dir, sub), exist_ok=True)

    def _rewrite_object_graph(self, sg_dir: str, new_sg_dir: str,
                              old_key: bytes, new_key: bytes, crypto) -> dict:
        """Re-encrypt every object under the new key AND recompute its content
        address, rewriting every reference bottom-up. Returns {old_id: new_id}.

        Why the ids must change (review finding A1 / option 3): an object id IS
        sha256(ciphertext)[:12], which is what lets any reader verify an object
        with no key and no trust in the host. Re-encrypting in place under a new
        key while KEEPING the old id (what move did before) silently voids that
        invariant for the whole vault: no object hashes to its id any more, so
        strict verification has to be relaxed, and once relaxed a hostile host
        can swap two authentic objects undetectably. Rewriting the ids restores
        the content address, so the reader-side check needs no exemption and a
        moved vault is indistinguishable from a freshly-created one.

        Object TYPES are decided by REACHABILITY from the refs, never by
        sniffing the plaintext: a blob whose content happens to be JSON with a
        'schema' key would otherwise be misparsed as a tree and have its
        "entries" rewritten.

        Order is bottom-up so every reference is already mapped when the object
        holding it is re-encrypted: blobs, then trees (children first), then
        commits (parents first).
        """
        import json as _json
        data_dir     = os.path.join(sg_dir, 'bare', 'data')
        new_data_dir = os.path.join(new_sg_dir, 'bare', 'data')
        id_map       = {}
        if not os.path.isdir(data_dir):
            return id_map

        all_ids = {name for name in os.listdir(data_dir) if name.startswith('obj-cas-imm-')}

        def load_plain(object_id):                       # decrypted plaintext, or None
            path = os.path.join(data_dir, object_id)
            if not os.path.isfile(path):
                return None
            try:
                with open(path, 'rb') as f:
                    return crypto.decrypt(old_key, f.read())
            except Exception:
                return None

        def load_json(object_id):                        # parsed object, or None
            plaintext = load_plain(object_id)
            if plaintext is None:
                return None
            try:
                return _json.loads(plaintext)
            except Exception:
                return None

        def emit(object_id, plaintext):
            """Encrypt under the new key, store at the RECOMPUTED id, map it."""
            new_cipher = crypto.encrypt(new_key, plaintext)
            new_id     = crypto.compute_object_id(new_cipher)
            with open(os.path.join(new_data_dir, new_id), 'wb') as f:
                f.write(new_cipher)
            id_map[object_id] = new_id
            return new_id

        def carry_unchanged(object_id):
            """Undecryptable object: copy the bytes verbatim, keeping its id —
            which is still that object's true content address, so the CAS
            invariant holds even here."""
            with open(os.path.join(data_dir, object_id), 'rb') as f:
                data = f.read()
            with open(os.path.join(new_data_dir, object_id), 'wb') as f:
                f.write(data)
            id_map[object_id] = object_id

        commit_ids, tree_ids, blob_ids = self._classify_by_reachability(
            sg_dir, old_key, crypto, all_ids, load_json)

        for blob_id in blob_ids:                         # 1. leaves — nothing to remap
            plaintext = load_plain(blob_id)
            if plaintext is None:
                carry_unchanged(blob_id)
            else:
                emit(blob_id, plaintext)

        for tree_id in tree_ids:                         # 2. children already mapped
            tree = load_json(tree_id)
            if tree is None:
                carry_unchanged(tree_id)
                continue
            for entry in tree.get('entries', []):
                for field in ('blob_id', 'tree_id'):
                    if entry.get(field):
                        entry[field] = id_map.get(entry[field], entry[field])
                for field in ('name_enc', 'size_enc', 'content_hash_enc', 'content_type_enc'):
                    if entry.get(field):
                        try:                             # deterministic: identical trees still dedup
                            value = crypto.decrypt_metadata(old_key, entry[field])
                            entry[field] = crypto.encrypt_metadata_deterministic(new_key, value)
                        except Exception:
                            pass
            emit(tree_id, _json.dumps(tree, separators=(',', ':')).encode('utf-8'))

        for commit_id in commit_ids:                     # 3. parents already mapped
            commit = load_json(commit_id)
            if commit is None:
                carry_unchanged(commit_id)
                continue
            if commit.get('tree_id'):
                commit['tree_id'] = id_map.get(commit['tree_id'], commit['tree_id'])
            commit['parents'] = [id_map.get(parent, parent)
                                 for parent in (commit.get('parents') or [])]
            if commit.get('message_enc'):
                try:
                    value = crypto.decrypt_metadata(old_key, commit['message_enc'])
                    commit['message_enc'] = crypto.encrypt_metadata(new_key, value)
                except Exception:
                    pass
            emit(commit_id, _json.dumps(commit, separators=(',', ':')).encode('utf-8'))

        for orphan_id in sorted(all_ids - set(id_map)):   # unreachable: carried, still unreachable
            plaintext = load_plain(orphan_id)
            if plaintext is None:
                carry_unchanged(orphan_id)
            else:
                emit(orphan_id, self._reencrypt_inner_fields(plaintext, old_key, new_key, crypto))
        return id_map

    def _classify_by_reachability(self, sg_dir: str, old_key: bytes, crypto,
                                  all_ids: set, load_json) -> tuple:
        """(commit_ids, tree_ids, blob_ids) in bottom-up rewrite order.

        Roots are the commit ids named by the refs. Types come from the graph's
        own shape — a commit's tree_id is a tree, a tree entry's blob_id is a
        blob — never from guessing at the plaintext.
        """
        import json as _json
        roots    = []
        refs_dir = os.path.join(sg_dir, 'bare', 'refs')
        if os.path.isdir(refs_dir):
            for fname in sorted(os.listdir(refs_dir)):
                path = os.path.join(refs_dir, fname)
                if not os.path.isfile(path):
                    continue
                try:
                    with open(path, 'rb') as f:
                        ref = _json.loads(crypto.decrypt(old_key, f.read()))
                    commit_id = ref.get('commit_id')
                except Exception:
                    continue
                if commit_id and commit_id in all_ids and commit_id not in roots:
                    roots.append(commit_id)

        def parents_of(commit_id):
            commit = load_json(commit_id)
            if not commit:
                return []
            return [str(p) for p in (commit.get('parents') or [])
                    if str(p) and str(p) in all_ids]

        commit_ids = self._post_order(roots, parents_of)  # parents before children

        root_trees = []
        for commit_id in commit_ids:
            commit  = load_json(commit_id)
            tree_id = str(commit.get('tree_id') or '') if commit else ''
            if tree_id and tree_id in all_ids and tree_id not in root_trees:
                root_trees.append(tree_id)

        blob_ids = []

        def sub_trees_of(tree_id):
            tree     = load_json(tree_id)
            children = []
            if not tree:
                return children
            for entry in tree.get('entries', []):
                blob_id = str(entry.get('blob_id') or '')
                sub_id  = str(entry.get('tree_id')  or '')
                if blob_id and blob_id in all_ids and blob_id not in blob_ids:
                    blob_ids.append(blob_id)
                if sub_id and sub_id in all_ids:
                    children.append(sub_id)
            return children

        tree_ids = self._post_order(root_trees, sub_trees_of)   # children before parents
        return commit_ids, tree_ids, blob_ids

    def _post_order(self, roots: list, children_of) -> list:
        """Iterative post-order over a DAG: every node appears after all of its
        children. Iterative (not recursive) because a commit chain can be long."""
        order, visited, stack = [], set(), [(root, False) for root in reversed(roots)]
        while stack:
            node, expanded = stack.pop()
            if expanded:
                if node not in visited:
                    visited.add(node)
                    order.append(node)
                continue
            if node in visited:
                continue
            stack.append((node, True))
            for child in children_of(node):
                if child not in visited:
                    stack.append((child, False))
        return order

    def _reencrypt_inner_fields(self, plaintext: bytes, old_key: bytes,
                                 new_key: bytes, crypto) -> bytes:
        import json as _json
        try:
            obj = _json.loads(plaintext)
        except Exception:
            return plaintext  # blob — no inner fields

        schema = obj.get('schema', '')
        if schema == 'tree_v1':
            for entry in obj.get('entries', []):
                for field in ('name_enc', 'size_enc', 'content_hash_enc', 'content_type_enc'):
                    if entry.get(field):
                        try:
                            val = crypto.decrypt_metadata(old_key, entry[field])
                            entry[field] = crypto.encrypt_metadata_deterministic(new_key, val)
                        except Exception:
                            pass
            return _json.dumps(obj, separators=(',', ':')).encode('utf-8')
        elif schema == 'commit_v1':
            if obj.get('message_enc'):
                try:
                    val = crypto.decrypt_metadata(old_key, obj['message_enc'])
                    obj['message_enc'] = crypto.encrypt_metadata(new_key, val)
                except Exception:
                    pass
            return _json.dumps(obj, separators=(',', ':')).encode('utf-8')
        return plaintext

    def _migrate_refs_and_index(self, sg_dir: str, new_sg_dir: str,
                                old_read_key: bytes, new_read_key: bytes,
                                old_index_id: str, new_index_id: str,
                                crypto, id_map: dict = None) -> None:
        import json as _json
        id_map   = id_map or {}
        refs_src = os.path.join(sg_dir, 'bare', 'refs')
        refs_dst = os.path.join(new_sg_dir, 'bare', 'refs')
        os.makedirs(refs_dst, exist_ok=True)
        if os.path.isdir(refs_src):
            for fname in os.listdir(refs_src):
                src = os.path.join(refs_src, fname)
                dst = os.path.join(refs_dst, fname)
                if not os.path.isfile(src):
                    continue
                with open(src, 'rb') as f:
                    old_cipher = f.read()
                try:
                    plaintext = crypto.decrypt(old_read_key, old_cipher)
                    # A ref names the head COMMIT, whose id changed with the
                    # object-graph rewrite — repoint it, or the moved vault has
                    # a dangling head.
                    try:
                        ref = _json.loads(plaintext)
                        if ref.get('commit_id') in id_map:
                            ref['commit_id'] = id_map[ref['commit_id']]
                            plaintext = _json.dumps(ref).encode()
                    except Exception:
                        pass
                    new_cipher = crypto.encrypt(new_read_key, plaintext)
                except Exception:
                    new_cipher = old_cipher
                with open(dst, 'wb') as f:
                    f.write(new_cipher)

        idx_src_dir = os.path.join(sg_dir, 'bare', 'indexes')
        idx_dst_dir = os.path.join(new_sg_dir, 'bare', 'indexes')
        os.makedirs(idx_dst_dir, exist_ok=True)
        if old_index_id and new_index_id and os.path.isdir(idx_src_dir):
            idx_src = os.path.join(idx_src_dir, old_index_id)
            idx_dst = os.path.join(idx_dst_dir, new_index_id)
            if os.path.isfile(idx_src):
                with open(idx_src, 'rb') as f:
                    old_cipher = f.read()
                try:
                    plaintext  = crypto.decrypt(old_read_key, old_cipher)
                    new_cipher = crypto.encrypt(new_read_key, plaintext)
                except Exception:
                    new_cipher = old_cipher
                with open(idx_dst, 'wb') as f:
                    f.write(new_cipher)
        elif os.path.isdir(idx_src_dir):
            for fname in os.listdir(idx_src_dir):
                src = os.path.join(idx_src_dir, fname)
                dst = os.path.join(idx_dst_dir, fname)
                if os.path.isfile(src):
                    shutil.copy2(src, dst)

    def _reencrypt_keys(self, sg_dir: str, new_sg_dir: str,
                        old_key: bytes, new_key: bytes, crypto) -> None:
        keys_dir     = os.path.join(sg_dir, 'bare', 'keys')
        new_keys_dir = os.path.join(new_sg_dir, 'bare', 'keys')
        os.makedirs(new_keys_dir, exist_ok=True)
        if not os.path.isdir(keys_dir):
            return
        for fname in os.listdir(keys_dir):
            src = os.path.join(keys_dir, fname)
            dst = os.path.join(new_keys_dir, fname)
            if not os.path.isfile(src):
                continue
            with open(src, 'rb') as f:
                old_cipher = f.read()
            try:
                plaintext  = crypto.decrypt(old_key, old_cipher)
                new_cipher = crypto.encrypt(new_key, plaintext)
            except Exception:
                new_cipher = old_cipher
            with open(dst, 'wb') as f:
                f.write(new_cipher)

    def _write_vault_key_file(self, new_sg_dir: str, vault_key: str) -> None:
        from sgit_ai.crypto.Vault__Crypto import Vault__Crypto
        local_dir = os.path.join(new_sg_dir, 'local')
        os.makedirs(local_dir, exist_ok=True)
        key_path = os.path.join(local_dir, 'vault_key')
        with open(key_path, 'w') as f:
            f.write(Vault__Crypto().format_vault_key(vault_key))    # sgit_private_vault_… on disk
        try:
            import stat
            os.chmod(key_path, stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            pass

    def _write_move_history(self, sg_dir: str, new_sg_dir: str,
                             old_vault_id: str, new_vault_id: str,
                             old_api_url: str, target_api: str,
                             key_generation: int, reason: str) -> None:
        from sgit_ai.schemas.move.Schema__Vault_Move_Record import Schema__Vault_Move_Record
        from sgit_ai.schemas.move.Schema__Vault_Moves       import Schema__Vault_Moves
        from sgit_ai.safe_types.Safe_Str__Base_URL          import Safe_Str__Base_URL
        from sgit_ai.safe_types.Safe_Str__Vault_Id          import Safe_Str__Vault_Id
        from sgit_ai.safe_types.Safe_UInt__Vault_Version    import Safe_UInt__Vault_Version
        from sgit_ai.safe_types.Safe_Str__Commit_Message    import Safe_Str__Commit_Message
        from osbot_utils.type_safe.primitives.domains.identifiers.safe_int.Timestamp_Now import Timestamp_Now

        old_hist_path = os.path.join(sg_dir, 'local', MOVE_HIST)
        existing_moves = []
        if os.path.isfile(old_hist_path):
            with open(old_hist_path) as f:
                try:
                    data = json.load(f)
                    existing_moves = data.get('moves', [])
                except Exception:
                    existing_moves = []

        new_record = Schema__Vault_Move_Record(
            from_vault_id  = Safe_Str__Vault_Id(old_vault_id) if old_vault_id else None,
            to_vault_id    = Safe_Str__Vault_Id(new_vault_id) if new_vault_id else None,
            from_api       = Safe_Str__Base_URL(old_api_url),
            to_api         = Safe_Str__Base_URL(target_api),
            key_generation = Safe_UInt__Vault_Version(key_generation),
            rotated_at     = Timestamp_Now(),
            reason         = Safe_Str__Commit_Message(reason) if reason else None,
        )

        all_records_raw = existing_moves + [new_record.json()]
        local_dir = os.path.join(new_sg_dir, 'local')
        os.makedirs(local_dir, exist_ok=True)
        hist_path = os.path.join(local_dir, MOVE_HIST)
        with open(hist_path, 'w') as f:
            json.dump({'moves': all_records_raw}, f, indent=2)

    def _update_local_config(self, sg_dir: str, new_sg_dir: str,
                              new_vault_id: str, key_generation: int,
                              target_api: str) -> None:
        old_cfg_path = os.path.join(sg_dir, 'local', 'config.json')
        cfg = {}
        if os.path.isfile(old_cfg_path):
            with open(old_cfg_path) as f:
                cfg = json.load(f)
        cfg['vault_id']       = new_vault_id
        cfg['key_generation'] = key_generation
        cfg['api_url']        = target_api

        for fname in ('migrations.json',):
            src = os.path.join(sg_dir, 'local', fname)
            dst = os.path.join(new_sg_dir, 'local', fname)
            if os.path.isfile(src):
                shutil.copy2(src, dst)

        local_dir = os.path.join(new_sg_dir, 'local')
        os.makedirs(local_dir, exist_ok=True)
        with open(os.path.join(local_dir, 'config.json'), 'w') as f:
            json.dump(cfg, f, indent=2)
