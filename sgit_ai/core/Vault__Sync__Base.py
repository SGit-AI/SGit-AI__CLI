"""Shared helpers for Vault__Sync sub-classes (brief 22 — E5).

All sub-classes (Vault__Sync__Commit, Vault__Sync__Pull, etc.) inherit
from this base, gaining access to _init_components, _read_local_config,
and other cross-cutting helpers without multiple Type_Safe inheritance.
"""
import json
import os
from   osbot_utils.type_safe.Type_Safe                import Type_Safe
from   sgit_ai.network.api.Vault__API                     import Vault__API
from   sgit_ai.crypto.PKI__Crypto                 import PKI__Crypto
from   sgit_ai.storage.Vault__Commit              import Vault__Commit
from   sgit_ai.crypto.Vault__Crypto               import Vault__Crypto
from   sgit_ai.crypto.Vault__Key_Manager          import Vault__Key_Manager
from   sgit_ai.storage.Vault__Object_Store        import Vault__Object_Store
from   sgit_ai.storage.Vault__Ref_Manager         import Vault__Ref_Manager
from   sgit_ai.schemas.Schema__Clone_Mode         import Schema__Clone_Mode
from   sgit_ai.schemas.Schema__Local_Config       import Schema__Local_Config
from   sgit_ai.safe_types.Enum__Clone_Mode        import Enum__Clone_Mode
from   sgit_ai.storage.Vault__Branch_Manager         import Vault__Branch_Manager
from   sgit_ai.core.Vault__Path_Guard                import Vault__Path_Guard
from   sgit_ai.core.Vault__Components             import Vault__Components
from   sgit_ai.core.Vault__Errors                 import Vault__Clone_Mode_Corrupt_Error
from   sgit_ai.core.actions.gc.Vault__GC                     import Vault__GC
from   sgit_ai.core.Vault__Ignore                 import Vault__Ignore
from   sgit_ai.storage.Vault__Storage                import Vault__Storage, SG_VAULT_DIR


class Vault__Sync__Base(Type_Safe):
    """Shared helpers for all Vault__Sync sub-classes; inject crypto + api per call."""
    crypto : Vault__Crypto = None
    api    : Vault__API    = None

    def _read_vault_key(self, directory: str) -> str:
        storage        = Vault__Storage()
        vault_key_path = storage.vault_key_path(directory)
        if not os.path.isfile(vault_key_path):
            legacy_path = os.path.join(directory, SG_VAULT_DIR, 'VAULT-KEY')
            if os.path.isfile(legacy_path):
                vault_key_path = legacy_path
        with open(vault_key_path, 'r') as f:
            return f.read().strip()

    def _get_read_key(self, directory: str) -> bytes:
        vault_key = self._read_vault_key(directory)
        keys      = self._derive_keys_from_stored_key(vault_key)
        return keys['read_key_bytes']

    def _derive_keys_from_stored_key(self, vault_key: str) -> dict:
        from sgit_ai.crypto.simple_token.Simple_Token import Simple_Token
        if Simple_Token.is_simple_token(vault_key):
            return self.crypto.derive_keys_from_simple_token(vault_key)
        return self.crypto.derive_keys_from_vault_key(vault_key)

    def _read_local_config(self, directory: str, storage: Vault__Storage) -> Schema__Local_Config:
        config_path = storage.local_config_path(directory)
        with open(config_path, 'r') as f:
            data = json.load(f)
        return Schema__Local_Config.from_json(data)

    def _read_clone_mode(self, directory: str) -> Schema__Clone_Mode:
        """Load and validate clone_mode.json. Returns an empty schema for full clones.

        Fail-closed: a present-but-unparseable clone_mode.json, or a READ_ONLY
        clone missing read_key/vault_id, raises Vault__Clone_Mode_Corrupt_Error.
        """
        storage         = Vault__Storage()
        clone_mode_path = storage.clone_mode_path(directory)
        if not os.path.isfile(clone_mode_path):
            return Schema__Clone_Mode()
        try:
            with open(clone_mode_path) as f:
                raw = json.load(f)
            clone_mode = Schema__Clone_Mode.from_json(raw)
        except Exception:
            raise Vault__Clone_Mode_Corrupt_Error()
        if clone_mode.mode == Enum__Clone_Mode.READ_ONLY:
            if not clone_mode.read_key or not clone_mode.vault_id:
                raise Vault__Clone_Mode_Corrupt_Error()
        return clone_mode

    def _derive_keys_for_directory(self, directory: str) -> dict:
        """Return a uniform keys dict for the directory, regardless of clone mode.

        Single source of truth for the clone-mode key-derivation dispatch
        (architect contract §4.1). Every Step__*__Derive_Keys and _init_components
        routes through this so the logic lives in exactly one place.

        Returns the union-keyed dict produced by either:
          - crypto.import_read_key()             (read-only clones)
          - crypto.derive_keys_from_vault_key()  (full / headless / simple-token clones)
        """
        clone_mode = self._read_clone_mode(directory)
        if clone_mode.mode == Enum__Clone_Mode.READ_ONLY:
            return self.crypto.import_read_key(str(clone_mode.read_key), str(clone_mode.vault_id))
        vault_key = self._read_vault_key(directory)
        return self._derive_keys_from_stored_key(vault_key)

    def _tracked_branch_name(self, directory: str) -> str:
        """Return the named branch a clone tracks (architect contract Q7).

        Reads branch_name from clone_mode.json, falling back to 'current' when
        unset or for non-read-only clones.
        """
        try:
            clone_mode = self._read_clone_mode(directory)
        except Exception:
            return 'current'
        if clone_mode.branch_name:
            return str(clone_mode.branch_name)
        return 'current'

    def _resolve_working_branch(self, config: Schema__Local_Config, branch_index,
                                branch_manager, branch_name: str = 'current'):
        """Resolve the working branch for a clone (architect contract §5.1).

        my_branch_id set  -> the clone branch named by my_branch_id
        my_branch_id None -> the named branch (default 'current') from the index

        The named-branch fallback fires only when my_branch_id is None/empty (the
        read-only clone case), exactly as the §5.1 pseudocode specifies. A clone
        whose my_branch_id is set but absent from the index resolves to None, so a
        genuinely-corrupt full clone still surfaces rather than silently retargeting.
        """
        branch_id = str(config.my_branch_id) if config.my_branch_id else ''
        if branch_id:
            return branch_manager.get_branch_by_id(branch_index, branch_id)
        return branch_manager.get_branch_by_name(branch_index, branch_name or 'current')

    def _init_components(self, directory: str) -> Vault__Components:
        sg_dir  = os.path.join(directory, SG_VAULT_DIR)
        storage = Vault__Storage()

        clone_mode = self._read_clone_mode(directory)
        keys       = self._derive_keys_for_directory(directory)              # single source of truth (§4.2)
        if clone_mode.mode == Enum__Clone_Mode.READ_ONLY:
            vault_key = ''
        else:
            vault_key = self._read_vault_key(directory)

        pki         = PKI__Crypto()
        obj_store   = Vault__Object_Store(vault_path=sg_dir, crypto=self.crypto)
        ref_manager = Vault__Ref_Manager(vault_path=sg_dir, crypto=self.crypto)
        key_manager = Vault__Key_Manager(vault_path=sg_dir, crypto=self.crypto, pki=pki)
        branch_manager = Vault__Branch_Manager(vault_path=sg_dir, crypto=self.crypto,
                                               key_manager=key_manager, ref_manager=ref_manager,
                                               storage=storage)
        return Vault__Components(vault_key              = vault_key,
                                 vault_id               = keys['vault_id'],
                                 read_key               = keys['read_key_bytes'],
                                 write_key              = keys.get('write_key', ''),
                                 ref_file_id            = keys['ref_file_id'],
                                 branch_index_file_id   = keys['branch_index_file_id'],
                                 sg_dir                 = sg_dir,
                                 storage                = storage,
                                 pki                    = pki,
                                 obj_store              = obj_store,
                                 ref_manager            = ref_manager,
                                 key_manager            = key_manager,
                                 branch_manager         = branch_manager)

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

    def _checkout_flat_map(self, directory: str, flat_map: dict,
                           obj_store: Vault__Object_Store, read_key: bytes) -> None:
        """Write all files from a flat {path: dict} map to the working directory."""
        guard = Vault__Path_Guard()
        for path, entry in sorted(flat_map.items()):
            blob_id = entry.get('blob_id')
            if not blob_id:
                continue
            try:
                # path comes from decrypted vault data; contain it before writing.
                full_path  = guard.safe_join(directory, path)
                ciphertext = obj_store.load(blob_id)
                plaintext  = self.crypto.decrypt(read_key, ciphertext)
                os.makedirs(os.path.dirname(full_path), exist_ok=True)
                with open(full_path, 'wb') as f:
                    f.write(plaintext)
            except Exception:
                pass

    def _remove_deleted_flat(self, directory: str, old_map: dict, new_map: dict) -> None:
        """Remove files present in old_map but not in new_map, then prune empty dirs."""
        guard = Vault__Path_Guard()
        for path in set(old_map.keys()) - set(new_map.keys()):
            if not guard.is_safe(directory, path):     # never delete outside the working copy
                continue
            full_path = os.path.join(directory, path)
            if os.path.isfile(full_path):
                os.remove(full_path)
        self._remove_empty_dirs(directory)

    def _remove_empty_dirs(self, directory: str) -> list:
        """Remove empty dirs after deletions; walks bottom-up, skips .sg_vault."""
        removed = []
        for root, dirs, files in os.walk(directory, topdown=False):
            rel = os.path.relpath(root, directory)
            if rel == '.':
                continue
            parts = rel.replace('\\', '/').split('/')
            if any(p.startswith('.') for p in parts):
                continue
            if not os.listdir(root):
                try:
                    os.rmdir(root)
                    removed.append(rel)
                except OSError:
                    pass
        return removed

    def _walk_commit_ids(self, obj_store, read_key: bytes, start: str,
                         limit: int = 200) -> set:
        """Return the set of all commit IDs reachable from start (inclusive)."""
        pki     = PKI__Crypto()
        vc      = Vault__Commit(crypto=self.crypto, pki=pki,
                                object_store=obj_store, ref_manager=Vault__Ref_Manager())
        visited = set()
        queue   = [start] if start else []
        while queue and len(visited) < limit:
            cid = queue.pop(0)
            if not cid or cid in visited:
                continue
            visited.add(cid)
            try:
                commit  = vc.load_commit(cid, read_key)
                parents = list(commit.parents) if commit.parents else []
                queue.extend(str(p) for p in parents if str(p))
            except Exception:
                pass
        return visited

    def _count_unique_commits(self, obj_store, read_key: bytes,
                              from_head: str, stop_head: str,
                              limit: int = 200) -> int:
        """Count commits reachable from from_head that are NOT reachable from stop_head."""
        if not from_head:
            return 0
        stop_ancestors = self._walk_commit_ids(obj_store, read_key, stop_head, limit)
        from_ancestors = self._walk_commit_ids(obj_store, read_key, from_head, limit)
        return len(from_ancestors - stop_ancestors)

    def _count_commits_from(self, obj_store, read_key: bytes,
                            start: str, limit: int = 200) -> int:
        """Count commits reachable from start (i.e. entire chain length)."""
        if not start:
            return 0
        return len(self._walk_commit_ids(obj_store, read_key, start, limit))

    def _clear_push_state(self, path: str) -> None:
        if os.path.isfile(path):
            os.remove(path)

    def fetch_tree_lazy(self, directory: str, tree_id: str) -> bool:
        """Download a single tree object and its blobs if not already present locally.

        Returns True if any objects were fetched, False if everything was already local.
        Downloads are logged to .sg_vault/local/lazy-fetch.log.
        """
        import datetime
        from sgit_ai.storage.Vault__Object_Store import Vault__Object_Store
        from sgit_ai.storage.Vault__Sub_Tree     import Vault__Sub_Tree
        from sgit_ai.storage.Vault__Storage      import Vault__Storage

        storage  = Vault__Storage()
        c        = self._init_components(directory)
        sg_dir   = storage.sg_vault_dir(directory)
        read_key = c.read_key
        obj_store = Vault__Object_Store(vault_path=sg_dir, crypto=self.crypto)

        if not c.vault_id:
            return False

        vault_id = c.vault_id
        fetched  = []

        # Fetch tree object itself if missing
        if not obj_store.exists(tree_id):
            try:
                data = self.api.read(vault_id, f'bare/data/{tree_id}')
                if data:
                    local_path = os.path.join(sg_dir, 'bare', 'data', tree_id)
                    os.makedirs(os.path.dirname(local_path), exist_ok=True)
                    with open(local_path, 'wb') as f:
                        f.write(data)
                    fetched.append(tree_id)
            except Exception:
                return False

        # Fetch missing blobs reachable from this tree
        try:
            from sgit_ai.storage.Vault__Commit import Vault__Commit
            from sgit_ai.crypto.PKI__Crypto    import PKI__Crypto
            pki = PKI__Crypto()
            vc  = Vault__Commit(crypto=self.crypto, pki=pki,
                                object_store=obj_store, ref_manager=None)
            tree     = vc.load_tree(tree_id, read_key)
            blob_ids = [str(e.blob_id) for e in tree.entries
                        if e.blob_id and not obj_store.exists(str(e.blob_id))]
            if blob_ids:
                result = self.api.batch_read(vault_id,
                                             [f'bare/data/{b}' for b in blob_ids])
                for fid, data in result.items():
                    if data:
                        oid        = fid.replace('bare/data/', '')
                        local_path = os.path.join(sg_dir, 'bare', 'data', oid)
                        os.makedirs(os.path.dirname(local_path), exist_ok=True)
                        with open(local_path, 'wb') as f:
                            f.write(data)
                        fetched.append(oid)
        except Exception:
            pass

        if fetched:
            log_path = os.path.join(storage.local_dir(directory), 'lazy-fetch.log')
            ts       = datetime.datetime.utcnow().isoformat(timespec='seconds')
            with open(log_path, 'a') as lf:
                for oid in fetched:
                    lf.write(f'{ts} {oid}\n')

        return bool(fetched)

    def _auto_gc_drain(self, directory: str) -> None:
        """Drain any pending GC packs. Calls Vault__GC directly; safe to call from any sub-class."""
        try:
            storage     = Vault__Storage()
            pending_dir = os.path.join(storage.local_dir(directory), 'packs')
            if not os.path.isdir(pending_dir):
                return
            if not any(d.startswith('pack-') for d in os.listdir(pending_dir)):
                return
            c            = self._init_components(directory)
            local_config = self._read_local_config(directory, c.storage)
            gc           = Vault__GC(crypto=self.crypto, storage=c.storage)
            gc.drain_pending(directory, c.read_key, str(local_config.my_branch_id),
                             branch_index_file_id=c.branch_index_file_id)
        except Exception:
            pass
