"""CLI__Cache — sgit cache add / rm / status.

Declares which vault paths carry a cache object. Creation is command-driven (D5:
the folder is the registry, there is no manifest); the push reconcile then keeps
every declared object in line with the head.
"""
import base64
import os
import sys

from osbot_utils.type_safe.Type_Safe             import Type_Safe
from sgit_ai.crypto.Vault__Crypto                import Vault__Crypto
from sgit_ai.storage.Vault__Storage              import Vault__Storage
from sgit_ai.storage.Vault__Cache_Manager        import (Vault__Cache_Manager,
                                                         CACHE_VALUE_THRESHOLD,
                                                         CACHE_VALUE_HARD_CAP)
from sgit_ai.safe_types.Enum__Cache_Kind         import Enum__Cache_Kind
from sgit_ai.safe_types.Enum__Cache_Mutability   import Enum__Cache_Mutability
from sgit_ai.safe_types.Enum__Cache_Target_Kind  import Enum__Cache_Target_Kind
from sgit_ai.safe_types.Enum__Clone_Mode         import Enum__Clone_Mode
from sgit_ai.safe_types.Safe_Str__Cache_Path     import Safe_Str__Cache_Path


class CLI__Cache(Type_Safe):

    def _components(self, directory: str):
        from sgit_ai.core.Vault__Sync import Vault__Sync
        sync    = Vault__Sync(crypto=Vault__Crypto())
        storage = Vault__Storage()
        manager = Vault__Cache_Manager(crypto=sync.crypto, storage=storage)
        keys    = sync._derive_keys_for_directory(directory)
        return sync, storage, manager, keys

    def _reject_read_only(self, sync, directory: str) -> None:
        """Caches are maintained by pushes, which a read-only clone can never do —
        declaring one here would "succeed" locally and then be unpublishable."""
        try:
            clone_mode = sync._read_clone_mode(directory)
        except Exception:
            return
        if clone_mode.mode == Enum__Clone_Mode.READ_ONLY:
            print('error: this is a read-only clone — cache declarations are published '
                  'by `sgit push`, which needs write access. Run this from a full clone.',
                  file=sys.stderr)
            sys.exit(1)

    def _head(self, sync, directory: str):
        """(commit_id, tree_id, flat_map, obj_store) for the working branch head."""
        c              = sync._init_components(directory)
        local_config   = sync._read_local_config(directory, c.storage)
        index_id       = c.branch_index_file_id
        branch_index   = c.branch_manager.load_branch_index(directory, index_id, c.read_key)
        branch_id      = str(local_config.my_branch_id) if local_config.my_branch_id else ''
        meta           = (c.branch_manager.get_branch_by_id(branch_index, branch_id)
                          if branch_id else c.branch_manager.get_branch_by_name(branch_index, 'current'))
        if not meta:
            raise RuntimeError('Could not resolve the working branch head')
        commit_id = c.ref_manager.read_ref(str(meta.head_ref_id), c.read_key)
        if not commit_id:
            raise RuntimeError('No commits yet — commit before declaring a cache')
        from sgit_ai.storage.Vault__Commit   import Vault__Commit
        from sgit_ai.storage.Vault__Sub_Tree import Vault__Sub_Tree
        vc        = Vault__Commit(crypto=sync.crypto, pki=c.pki, object_store=c.obj_store,
                                  ref_manager=c.ref_manager)
        commit    = vc.load_commit(commit_id, c.read_key)
        sub_tree  = Vault__Sub_Tree(crypto=sync.crypto, obj_store=c.obj_store)
        flat      = sub_tree.flatten(str(commit.tree_id), c.read_key)
        return commit_id, str(commit.tree_id), flat, c.obj_store, sub_tree, c.read_key

    def cmd_cache_add(self, args):
        directory = getattr(args, 'directory', None) or '.'
        path      = self._normalise_path(args.path)
        want_ptr  = getattr(args, 'pointer', False)
        want_val  = getattr(args, 'value',   False)

        sync, storage, manager, keys = self._components(directory)
        self._reject_read_only(sync, directory)
        vault_id = keys['vault_id']
        try:
            Safe_Str__Cache_Path(path)                 # the stored path must survive as-is
        except Exception:
            print(f'error: path contains control characters and cannot be cached: {path!r}',
                  file=sys.stderr)
            sys.exit(1)
        try:
            commit_id, tree_id, flat, obj_store, sub_tree, read_key = self._head(sync, directory)
        except RuntimeError as exc:
            print(f'error: {exc}', file=sys.stderr)
            sys.exit(1)

        target_kind, target_id = sub_tree.resolve_path_target(tree_id, path, read_key)
        if not target_id:
            print(f"error: path not found in the vault head: '{path}'", file=sys.stderr)
            sys.exit(1)

        entry = flat.get(path) or {}
        size  = int(entry.get('size', 0) or 0)

        # Choose the kind: explicit flag wins; otherwise folders and large files
        # become pointers, small hot records become values (contract Q2).
        if want_ptr and want_val:
            print('error: use either --pointer or --value, not both', file=sys.stderr)
            sys.exit(1)
        if want_val and target_kind == 'tree':
            print('error: a folder cannot be cached by value — use --pointer', file=sys.stderr)
            sys.exit(1)
        if want_val and size > CACHE_VALUE_HARD_CAP:
            print(f'error: {path} is {size} bytes — too large to cache by value '
                  f'(limit {CACHE_VALUE_HARD_CAP} bytes; the object must fit the '
                  f'server batch body budget). Use --pointer instead.', file=sys.stderr)
            sys.exit(1)
        kind = (Enum__Cache_Kind.POINTER if want_ptr else
                Enum__Cache_Kind.VALUE   if want_val else
                (Enum__Cache_Kind.VALUE if target_kind == 'blob' and size <= CACHE_VALUE_THRESHOLD
                 else Enum__Cache_Kind.POINTER))

        # D4: a path is cached as value OR pointer, never both. The tombstone is
        # what makes the replacement stick: without it the next push rediscovers
        # the server's copy of the old kind and resurrects it.
        other = (Enum__Cache_Kind.POINTER if kind == Enum__Cache_Kind.VALUE
                 else Enum__Cache_Kind.VALUE)
        other_id = manager.cache_id(read_key, vault_id, path, other)
        if manager.exists(directory, other, other_id):
            manager.delete(directory, other, other_id)
            manager.add_tombstone(directory, other, other_id, path)
            print(f'  (replaced existing {other.value} cache for this path)')

        cache_id = manager.cache_id(read_key, vault_id, path, kind)
        manager.clear_tombstones(directory, {(kind, cache_id)})   # re-declared after a rm
        if kind == Enum__Cache_Kind.VALUE:
            try:
                ciphertext = obj_store.load(entry['blob_id'])
            except FileNotFoundError:
                print(f"error: the content of '{path}' is not available locally "
                      f'(sparse clone?). Fetch the file first, or use --pointer.',
                      file=sys.stderr)
                sys.exit(1)
            plaintext = sync.crypto.decrypt(read_key, ciphertext)
            obj = manager.build_value(path=path, content=plaintext, commit_id=commit_id,
                                      content_type=entry.get('content_type', '') or '',
                                      content_hash=entry.get('content_hash', '') or '')
        else:
            obj = manager.build_pointer(path         = path,
                                        target_id    = target_id,
                                        target_kind  = (Enum__Cache_Target_Kind.BLOB
                                                        if target_kind == 'blob'
                                                        else Enum__Cache_Target_Kind.TREE),
                                        commit_id    = commit_id,
                                        content_type = entry.get('content_type', '') or '',
                                        size         = size,
                                        content_hash = (entry.get('content_hash') or None
                                                        if target_kind == 'blob' else None))
        manager.save(directory, kind, cache_id, obj, read_key)

        print(f'Cached  {path}')
        print(f'  Kind:      {kind.value}  ({"folder" if target_kind == "tree" else "file"})')
        print(f'  Cache ID:  {cache_id}')
        print(f'  Location:  {storage.cache_file_id(manager.kind_dir_name(kind), cache_id)}')
        print()
        print('Next:')
        print('  sgit push            — publish the cache object to the remote')

    def _normalise_path(self, path: str) -> str:
        """User-input boundary only: strip './' prefixes, trailing slashes and
        empty segments so 'media/', './media' and 'docs//readme.md' derive the
        same ids as their canonical spellings. The programmatic layers (manager,
        reader, reconcile) deliberately do NOT normalise — the contract's
        identity is the raw flatten() key."""
        p     = (path or '').replace('\\', '/')
        parts = [seg for seg in p.split('/') if seg not in ('', '.')]
        return '/'.join(parts) or p

    def cmd_cache_rm(self, args):
        directory = getattr(args, 'directory', None) or '.'
        path      = self._normalise_path(args.path)
        sync, _, manager, keys = self._components(directory)
        self._reject_read_only(sync, directory)
        read_key = keys['read_key_bytes']
        removed  = []
        for kind in (Enum__Cache_Kind.VALUE, Enum__Cache_Kind.POINTER):
            cache_id = manager.cache_id(read_key, keys['vault_id'], path, kind)
            # The tombstone is the removal: deleting only the local file lets the
            # next push rediscover the server copy via the D6 listing and
            # resurrect it. Recorded for both kinds and regardless of local
            # presence, so a clone can also retire a cache another clone declared.
            manager.add_tombstone(directory, kind, cache_id, path)
            if manager.delete(directory, kind, cache_id):
                removed.append((kind.value, cache_id))
        if not removed:
            print(f"No local cache for '{path}' — removal recorded.")
        for kind_name, cache_id in removed:
            print(f'Removed {kind_name} cache for {path}  ({cache_id})')
        print()
        print('Note: any remote copy is deleted on the next `sgit push` (or `sgit cache repair`).')

    def cmd_cache_repair(self, args):
        from sgit_ai.core.actions.cache.Vault__Cache_Repair import Vault__Cache_Repair
        from sgit_ai.network.api.Vault__API                 import Vault__API

        directory = getattr(args, 'directory', None) or '.'
        dry_run   = getattr(args, 'dry_run', False)
        as_json   = getattr(args, 'json', False)

        repair = Vault__Cache_Repair(crypto=Vault__Crypto(), api=Vault__API().setup())
        result = repair.repair(directory, dry_run=dry_run)

        if as_json:
            import json as _json
            print(_json.dumps(result, indent=2))
            return

        if result.get('status') == 'no_head':
            print('No commits yet — nothing to repair.')
            return

        if result.get('status') == 'stale_head':
            print('Local head is behind the server — repairing from stale state would '
                  'destroy caches another clone just published.')
            print('Run `sgit pull` first, then repair.')
            return

        if result['checked'] == 0 and not result['actions']:
            print('No cache objects declared — nothing to repair.')
            return

        prefix = '[dry-run] ' if dry_run else ''
        print(f"{prefix}Checked {result['checked']} cache object(s) against {result['head']}")
        for action, kind, cache_id, path in result['actions']:
            label = {'rewritten'              : 'rewrite',
                     'orphan-deleted'         : 'delete (path gone)',
                     'duplicate-dropped'      : 'delete (duplicate declaration)',
                     'unreadable-dropped'     : 'delete (unreadable)',
                     'tombstone-deleted'      : 'delete (removed by cache rm)',
                     'skipped-unrecognised'   : 'skip (unrecognised format — newer client?)',
                     'skipped-missing-content': 'skip (content not local — sparse clone)',
                     'skipped-error'          : 'skip (error rebuilding)'}.get(action, action)
            print(f'  {label:44s} [{kind}] {path or cache_id}')
        print()
        print(f"  repaired:  {result['repaired']}")
        print(f"  deleted:   {result['deleted']}")
        print(f"  duplicates:{result['deduped']}")
        print(f"  skipped:   {result.get('skipped', 0)}")
        print(f"  unchanged: {result['unchanged']}")
        if dry_run and (result['repaired'] or result['deleted'] or result['deduped']):
            print()
            print('Nothing was changed. Re-run without --dry-run to apply.')

    def cmd_cache_status(self, args):
        directory = getattr(args, 'directory', None) or '.'
        as_json   = getattr(args, 'json', False)
        sync, _, manager, keys = self._components(directory)
        read_key = keys['read_key_bytes']

        entries = []
        for kind, cache_id in manager.list_all(directory):
            obj = manager.load(directory, kind, cache_id, read_key)
            if obj is None:
                entries.append(dict(kind=kind.value, cache_id=cache_id, path='(unreadable)',
                                    commit_id='', fresh=False))
                continue
            entries.append(dict(kind      = kind.value,
                                cache_id  = cache_id,
                                path      = str(obj.path),
                                commit_id = str(obj.commit_id) if obj.commit_id else '',
                                fresh     = None))

        head_commit = ''
        try:
            head_commit, _, _, _, _, _ = self._head(sync, directory)
        except Exception:
            pass
        for e in entries:
            e['fresh'] = bool(head_commit) and e['commit_id'] == head_commit

        if as_json:
            import json as _json
            print(_json.dumps(dict(head=head_commit, entries=entries), indent=2))
            return

        if not entries:
            print('No cache objects declared.')
            print()
            print('Next:')
            print('  sgit cache add <path>   — declare a cached path')
            return

        print(f'Cache objects: {len(entries)}')
        if head_commit:
            print(f'HEAD:          {head_commit}')
        print()
        for e in sorted(entries, key=lambda x: (x['kind'], x['path'])):
            mark = 'fresh' if e['fresh'] else 'stale'
            print(f"  [{e['kind']:7s}] {mark:5s}  {e['path']}")
            print(f"             {e['cache_id']}")
        stale = [e for e in entries if not e['fresh']]
        if stale:
            print()
            print(f'{len(stale)} stale — run `sgit push` to reconcile.')
