"""Vault__Cache_Repair — the recovery path for the cache layer.

The push reconcile keeps caches healed in the normal flow. Repair exists for the
cases push cannot cover: objects written by a client that then stopped pushing,
corrupt or undecryptable objects, orphans whose path was deleted by an unaware
client, and duplicate declarations that violate one-object-per-path (D4).

Divergence in a cache is silent by nature, so this ships in v1 alongside the
feature rather than after the first incident.
"""
import base64
import os

from sgit_ai.core.Vault__Sync__Base                import Vault__Sync__Base
from sgit_ai.storage.Vault__Cache_Manager          import Vault__Cache_Manager
from sgit_ai.storage.Vault__Sub_Tree               import Vault__Sub_Tree
from sgit_ai.storage.Vault__Commit                 import Vault__Commit
from sgit_ai.core.actions.push.Vault__Batch        import Vault__Batch
from sgit_ai.safe_types.Enum__Batch_Op             import Enum__Batch_Op
from sgit_ai.safe_types.Enum__Cache_Kind           import Enum__Cache_Kind


class Vault__Cache_Repair(Vault__Sync__Base):

    def repair(self, directory: str, dry_run: bool = False,
               on_progress: callable = None) -> dict:
        """Bring every cache object in line with the head; report what changed.

        Actions, in order of precedence per object:
          - duplicate (same path cached as BOTH value and pointer) → drop one (D4)
          - path no longer in the head                             → delete (orphan)
          - unreadable / drifted from the head                     → rewrite
          - already current                                        → leave
        """
        _p = on_progress or (lambda *a, **k: None)
        c  = self._init_components(directory)

        manager  = Vault__Cache_Manager(crypto=self.crypto, storage=c.storage)
        head     = self._resolve_head(directory, c)
        if not head:
            return dict(status='no_head', checked=0, repaired=0, deleted=0,
                        deduped=0, unchanged=0, dry_run=dry_run, actions=[])

        commit_id, tree_id, flat = head
        sub_tree = Vault__Sub_Tree(crypto=self.crypto, obj_store=c.obj_store)

        targets  = self._targets(manager, directory, str(c.vault_id))
        loaded   = self._load_targets(manager, directory, str(c.vault_id), targets, c.read_key)

        actions    = []
        operations = []
        deduped    = self._resolve_duplicates(loaded, flat, commit_id, actions)

        repaired = unchanged = deleted = 0
        for kind, cache_id, existing in loaded:
            if (kind, cache_id) in deduped:
                if not dry_run:
                    manager.delete(directory, kind, cache_id)
                operations.append(dict(op      = Enum__Batch_Op.DELETE.value,
                                       file_id = manager.file_id(kind, cache_id)))
                continue

            path = str(existing.path) if existing is not None else None
            if path is None:                                   # unreadable and unidentifiable
                actions.append(('unreadable-dropped', kind.value, cache_id, ''))
                if not dry_run:
                    manager.delete(directory, kind, cache_id)
                operations.append(dict(op      = Enum__Batch_Op.DELETE.value,
                                       file_id = manager.file_id(kind, cache_id)))
                deleted += 1
                continue

            rebuilt = manager.rebuild_for_path(kind=kind, path=path, commit_id=commit_id,
                                               tree_id=tree_id, flat=flat,
                                               obj_store=c.obj_store, sub_tree=sub_tree,
                                               read_key=c.read_key,
                                               mutability=existing.mutability)
            if rebuilt is None:                                # path gone from the vault
                actions.append(('orphan-deleted', kind.value, cache_id, path))
                if not dry_run:
                    manager.delete(directory, kind, cache_id)
                operations.append(dict(op      = Enum__Batch_Op.DELETE.value,
                                       file_id = manager.file_id(kind, cache_id)))
                deleted += 1
                continue

            if rebuilt.json() == existing.json():
                unchanged += 1
                continue

            actions.append(('rewritten', kind.value, cache_id, path))
            if not dry_run:
                manager.save(directory, kind, cache_id, rebuilt, c.read_key)
                ciphertext = manager.encrypt_object(rebuilt, c.read_key)
                operations.append(dict(op      = Enum__Batch_Op.WRITE.value,
                                       file_id = manager.file_id(kind, cache_id),
                                       data    = base64.b64encode(ciphertext).decode('ascii')))
            repaired += 1

        if operations and not dry_run:
            self._publish(str(c.vault_id), str(c.write_key), operations, _p)

        return dict(status    = 'ok',
                    head      = commit_id,
                    checked   = len(loaded),
                    repaired  = repaired,
                    deleted   = deleted,
                    deduped   = len(deduped),
                    unchanged = unchanged,
                    dry_run   = dry_run,
                    actions   = actions)

    # --- internals ---------------------------------------------------------

    def _resolve_head(self, directory: str, c):
        """(commit_id, tree_id, flat_map) for the working branch head, or None."""
        local_config = self._read_local_config(directory, c.storage)
        index_id     = c.branch_index_file_id
        if not index_id:
            return None
        branch_index = c.branch_manager.load_branch_index(directory, index_id, c.read_key)
        branch_id    = str(local_config.my_branch_id) if local_config.my_branch_id else ''
        meta         = (c.branch_manager.get_branch_by_id(branch_index, branch_id) if branch_id
                        else c.branch_manager.get_branch_by_name(branch_index, 'current'))
        if not meta:
            return None
        commit_id = c.ref_manager.read_ref(str(meta.head_ref_id), c.read_key)
        if not commit_id:
            return None
        vc       = Vault__Commit(crypto=self.crypto, pki=c.pki,
                                 object_store=c.obj_store, ref_manager=c.ref_manager)
        commit   = vc.load_commit(commit_id, c.read_key)
        sub_tree = Vault__Sub_Tree(crypto=self.crypto, obj_store=c.obj_store)
        flat     = sub_tree.flatten(str(commit.tree_id), c.read_key)
        return commit_id, str(commit.tree_id), flat

    def _targets(self, manager, directory: str, vault_id: str) -> list:
        """Union of local and server cache objects (server listing best-effort)."""
        targets = set(manager.list_all(directory))
        try:
            for file_id in (self.api.list_files(vault_id, 'bare/cache/') or []):
                parts = str(file_id).replace('\\', '/').strip('/').split('/')
                if len(parts) >= 4 and parts[0] == 'bare' and parts[1] == 'cache':
                    kind = manager.kind_for_dir_name(parts[2])
                    if kind and parts[3].startswith('cch-pid-'):
                        targets.add((kind, parts[3]))
        except Exception:
            pass
        return sorted(targets, key=lambda t: (t[0].value, t[1]))

    def _load_targets(self, manager, directory: str, vault_id: str,
                      targets: list, read_key: bytes) -> list:
        """[(kind, cache_id, object_or_None)] — pulls from the server when a target
        exists remotely but not in the local mirror (another client created it)."""
        out = []
        for kind, cache_id in targets:
            obj = manager.load(directory, kind, cache_id, read_key)
            if obj is None:
                obj = self._fetch_remote(manager, vault_id, kind, cache_id, read_key)
            out.append((kind, cache_id, obj))
        return out

    def _fetch_remote(self, manager, vault_id: str, kind, cache_id: str, read_key: bytes):
        try:
            file_id = manager.file_id(kind, cache_id)
            data    = self.api.batch_read(vault_id, [file_id])
            blob    = data.get(file_id)
            if blob:
                return manager.decrypt_object(blob, read_key, kind)
        except Exception:
            pass
        return None

    def _resolve_duplicates(self, loaded: list, flat: dict, head_commit: str,
                            actions: list) -> set:
        """Enforce D4 — one object per path. Returns the (kind, cache_id) set to drop.

        Rule, applied in order: keep whichever object is already fresh (its
        commit_id matches the head); if that does not decide it, keep the kind that
        is natural for the target — pointer for a folder (a folder cannot be cached
        by value at all), value for a file. Deterministic, and the user can always
        override afterwards with `sgit cache add --pointer/--value`.
        """
        by_path = {}
        for kind, cache_id, obj in loaded:
            if obj is None:
                continue
            by_path.setdefault(str(obj.path), []).append((kind, cache_id, obj))

        drop = set()
        for path, group in by_path.items():
            if len(group) < 2:
                continue
            fresh = [g for g in group if str(g[2].commit_id) == head_commit]
            if len(fresh) == 1:
                keep = fresh[0]
            else:
                natural = (Enum__Cache_Kind.VALUE if path in flat else Enum__Cache_Kind.POINTER)
                keep    = next((g for g in group if g[0] == natural), group[0])
            for kind, cache_id, _ in group:
                if (kind, cache_id) != (keep[0], keep[1]):
                    drop.add((kind, cache_id))
                    actions.append(('duplicate-dropped', kind.value, cache_id, path))
        return drop

    def _publish(self, vault_id: str, write_key: str, operations: list, _p) -> None:
        """Push repair results to the remote. Best-effort: a local repair that cannot
        publish is still a repair, and the next push will carry it."""
        try:
            batch = Vault__Batch(crypto=self.crypto, api=self.api)
            try:
                batch.execute_batch(vault_id, write_key, operations)
            except Exception:
                batch.execute_individually(vault_id, write_key, operations)
        except Exception as exc:
            _p('warning', 'Repaired locally but could not publish (next push will)', str(exc))
