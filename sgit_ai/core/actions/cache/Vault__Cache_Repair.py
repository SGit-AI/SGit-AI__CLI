"""Vault__Cache_Repair — the recovery path for the cache layer.

The push reconcile keeps caches healed in the normal flow. Repair exists for the
cases push cannot cover: objects written by a client that then stopped pushing,
corrupt or undecryptable objects, orphans whose path was deleted by an unaware
client, and duplicate declarations that violate one-object-per-path (D4).

Divergence in a cache is silent by nature, so this ships in v1 alongside the
feature rather than after the first incident.

Two safety rules (review 08/14):
  - repair REFUSES to run from a head that is behind the server (#4): rewriting
    or deleting caches from stale state would un-heal what another client just
    published. The caller pulls first.
  - one broken object never aborts the run (#5): every per-object step is
    guarded, and objects that merely cannot be handled are reported as skipped.
"""
import base64
import os

from sgit_ai.core.Vault__Sync__Base                import Vault__Sync__Base
from sgit_ai.storage.Vault__Cache_Manager          import (Vault__Cache_Manager,
                                                           Vault__Cache_Blob_Missing_Error)
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
          - removal recorded by `cache rm` (tombstone)          → delete remote copy
          - duplicate (same path cached as BOTH value and pointer) → drop one (D4)
          - undecryptable (garbage / foreign key)                → delete (corrupt)
          - decrypts but does not parse (newer client's schema?) → SKIP, never delete
          - path no longer in the head                           → delete (orphan)
          - drifted from the head                                → rewrite
          - already current                                      → leave
        """
        _p = on_progress or (lambda *a, **k: None)
        c  = self._init_components(directory)

        manager  = Vault__Cache_Manager(crypto=self.crypto, storage=c.storage)
        head     = self._resolve_head(directory, c)
        if not head:
            return dict(status='no_head', checked=0, repaired=0, deleted=0,
                        deduped=0, unchanged=0, skipped=0, dry_run=dry_run, actions=[])

        if self._local_head_is_behind_server(directory, c):
            return dict(status='stale_head', checked=0, repaired=0, deleted=0,
                        deduped=0, unchanged=0, skipped=0, dry_run=dry_run, actions=[])

        commit_id, tree_id, flat = head
        sub_tree = Vault__Sub_Tree(crypto=self.crypto, obj_store=c.obj_store)

        tombstoned = manager.tombstoned_ids(directory)
        targets    = self._targets(manager, directory, str(c.vault_id))

        actions    = []
        operations = []
        cleared    = set()

        # Tombstoned ids: `cache rm` recorded the intent — delete the remote
        # copy rather than treating it as a foreign declaration to re-heal.
        deleted = 0
        for kind, cache_id in [t for t in targets if t in tombstoned]:
            actions.append(('tombstone-deleted', kind.value, cache_id, ''))
            if not dry_run:
                manager.delete(directory, kind, cache_id)
            operations.append(dict(op      = Enum__Batch_Op.DELETE.value,
                                   file_id = manager.file_id(kind, cache_id)))
            cleared.add((kind, cache_id))
            deleted += 1
        cleared |= set(t for t in tombstoned if t not in targets)

        live_targets = [t for t in targets if t not in tombstoned]
        loaded       = self._load_targets(manager, directory, str(c.vault_id),
                                          live_targets, c.read_key)

        deduped = set()
        for kind, cache_id, path in manager.resolve_duplicates(
                [(k, cid, obj) for k, cid, obj, _status in loaded], flat, commit_id):
            deduped.add((kind, cache_id))
            actions.append(('duplicate-dropped', kind.value, cache_id, path))

        blob_fetcher = self._make_blob_fetcher(str(c.vault_id))
        repaired = unchanged = skipped = 0
        for kind, cache_id, existing, status in loaded:
            if (kind, cache_id) in deduped:
                if not dry_run:
                    manager.delete(directory, kind, cache_id)
                operations.append(dict(op      = Enum__Batch_Op.DELETE.value,
                                       file_id = manager.file_id(kind, cache_id)))
                continue

            if status == 'unparseable':
                # Decrypted under our read_key, so a key holder wrote it — most
                # likely a newer client's schema. Deleting it would destroy that
                # client's valid object (review 08/14 M2). Leave it alone.
                actions.append(('skipped-unrecognised', kind.value, cache_id, ''))
                skipped += 1
                continue

            if existing is None:                               # undecryptable / vanished
                actions.append(('unreadable-dropped', kind.value, cache_id, ''))
                if not dry_run:
                    manager.delete(directory, kind, cache_id)
                operations.append(dict(op      = Enum__Batch_Op.DELETE.value,
                                       file_id = manager.file_id(kind, cache_id)))
                deleted += 1
                continue

            path = str(existing.path or '')
            if not path:
                # Parseable but carries no identity — treat like an unrecognised
                # format rather than executing it as an orphan of path ''.
                actions.append(('skipped-unrecognised', kind.value, cache_id, ''))
                skipped += 1
                continue
            try:
                rebuilt = manager.rebuild_for_path(kind=kind, path=path, commit_id=commit_id,
                                                   tree_id=tree_id, flat=flat,
                                                   obj_store=c.obj_store, sub_tree=sub_tree,
                                                   read_key=c.read_key,
                                                   mutability=existing.mutability,
                                                   blob_fetcher=blob_fetcher)
            except Vault__Cache_Blob_Missing_Error:
                actions.append(('skipped-missing-content', kind.value, cache_id, path))
                skipped += 1
                continue
            except Exception:                                  # one bad object never aborts the run
                actions.append(('skipped-error', kind.value, cache_id, path))
                skipped += 1
                continue

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

        published = True
        if operations and not dry_run:
            published = self._publish(str(c.vault_id), str(c.write_key), operations, _p)

        if cleared and not dry_run and published:
            manager.clear_tombstones(directory, cleared)       # only once the deletes landed

        return dict(status    = 'ok',
                    head      = commit_id,
                    checked   = len(loaded),
                    repaired  = repaired,
                    deleted   = deleted,
                    deduped   = len(deduped),
                    unchanged = unchanged,
                    skipped   = skipped,
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

    def _local_head_is_behind_server(self, directory: str, c) -> bool:
        """True when the server's named ref differs from the local one — repairing
        from that state would destroy caches another client just published (#4).
        Unverifiable (offline) counts as NOT behind: a publish that cannot reach
        the server cannot destroy anything there either."""
        try:
            branch_index = c.branch_manager.load_branch_index(directory,
                                                              c.branch_index_file_id,
                                                              c.read_key)
            named_meta   = c.branch_manager.get_branch_by_name(branch_index, 'current')
            if not named_meta:
                return False
            named_ref_id = str(named_meta.head_ref_id)
            local_named  = c.ref_manager.read_ref(named_ref_id, c.read_key)
            server_named = self._server_named_commit_id(str(c.vault_id), named_ref_id,
                                                        c.read_key)
            return bool(server_named) and server_named != local_named
        except Exception:
            return False

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
        """[(kind, cache_id, object_or_None, status)] with status from
        classify_ciphertext, plus 'missing' when no bytes exist anywhere.
        Pulls from the server when a target exists remotely but not in the
        local mirror (another client created it)."""
        out = []
        for kind, cache_id in targets:
            raw = None
            local_path = manager.storage.cache_path(directory, manager.kind_dir_name(kind),
                                                    cache_id)
            if os.path.isfile(local_path):
                try:
                    with open(local_path, 'rb') as f:
                        raw = f.read()
                except OSError:
                    raw = None
            if raw is None:
                try:
                    file_id = manager.file_id(kind, cache_id)
                    raw     = self.api.batch_read(vault_id, [file_id]).get(file_id)
                except Exception:
                    raw = None
            if not raw:
                out.append((kind, cache_id, None, 'missing'))
                continue
            obj, status = manager.classify_ciphertext(raw, read_key, kind)
            out.append((kind, cache_id, obj, status))
        return out

    def _publish(self, vault_id: str, write_key: str, operations: list, _p) -> bool:
        """Push repair results to the remote. Best-effort: a local repair that cannot
        publish is still a repair, and the next push will carry it. The return value
        gates tombstone clearing — an unpublished delete must keep its tombstone."""
        try:
            batch = Vault__Batch(crypto=self.crypto, api=self.api)
            try:
                batch.execute_batch(vault_id, write_key, operations)
            except Exception:
                batch.execute_individually(vault_id, write_key, operations)
            return True
        except Exception as exc:
            _p('warning', 'Repaired locally but could not publish (next push will)', str(exc))
            return False
