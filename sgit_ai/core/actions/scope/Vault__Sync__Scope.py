"""Vault__Sync__Scope — widen a scoped clone, deepen a shallow one, guard the rest.

  widen(directory, folder)  — add a folder to the clone's scope: fetch its trees
                              and blobs from the HEAD commit, write its files,
                              record it. Only the spine down to it and the
                              folder itself are fetched.
  unshallow(directory)      — fetch the commits behind every boundary down to
                              the roots (commit objects only on a scoped clone;
                              everything, via the store listing, on a
                              whole-vault clone — so history commands then
                              have the trees and blobs they need) and clear
                              the boundaries.
  require_whole(directory)  — raise Vault__Scoped_Clone_Error for commands
                              that need the whole vault (fsck, dump, publish,
                              vault move …) on a partial clone.
"""
import json
import os
from   sgit_ai.core.Vault__Sync__Base             import Vault__Sync__Base
from   sgit_ai.core.Vault__Errors                 import Vault__Scoped_Clone_Error
from   sgit_ai.core.scope.Vault__Scope            import Vault__Scope
from   sgit_ai.crypto.PKI__Crypto                 import PKI__Crypto
from   sgit_ai.storage.Vault__Commit              import Vault__Commit
from   sgit_ai.storage.Vault__Scoped_Tree         import Vault__Scoped_Tree
from   sgit_ai.storage.Vault__Verified_Write      import Vault__Verified_Write


class Vault__Sync__Scope(Vault__Sync__Base):

    # ------------------------------------------------------------- queries
    def scope_of(self, directory: str) -> Vault__Scope:
        c = self._init_components(directory)
        return Vault__Scope().from_local_config(self._read_local_config(directory, c.storage))

    def require_whole(self, directory: str, command: str) -> None:
        scope = self.scope_of(directory)
        if scope.is_partial():
            raise Vault__Scoped_Clone_Error(
                f'`{command}` needs the whole vault, and this clone holds only part of it '
                f'({scope.describe()}). Run it from a full clone, or widen this one: '
                f'`sgit fetch <folder>` adds a folder, `sgit fetch --unshallow` fetches the history.')

    # --------------------------------------------------------------- widen
    def widen(self, directory: str, folder: str, on_progress: callable = None) -> dict:
        _p    = on_progress or (lambda *a, **k: None)
        c     = self._init_components(directory)
        cfg   = self._read_local_config(directory, c.storage)
        scope = Vault__Scope().from_local_config(cfg)
        if not scope.is_scoped():
            raise Vault__Scoped_Clone_Error('this clone already holds the whole vault; nothing to widen')
        folder = scope.normalise(folder)
        if scope.contains_path(folder):
            return dict(folder=folder, already_held=True, fetched=0, written=0)

        head = self._local_head_commit_id(directory, c, cfg)
        if not head:
            raise RuntimeError('no local HEAD commit to widen from')
        vc     = Vault__Commit(crypto=self.crypto, pki=PKI__Crypto(), object_store=c.obj_store, ref_manager=c.ref_manager)
        commit = vc.load_commit(head, c.read_key)
        wider  = Vault__Scope().with_paths(scope.folders() + [folder]).with_boundaries(scope.boundary_ids())
        only   = Vault__Scope().with_paths([folder])
        scoped = Vault__Scoped_Tree(crypto=self.crypto, obj_store=c.obj_store)
        writer = Vault__Verified_Write(crypto=self.crypto)
        vault_id = str(c.vault_id)
        fetched  = [0]

        def download(ids):
            _p('scan', f'Fetching {folder}', f'{len(ids)} tree(s)')
            for fid, blob in self.api.batch_read(vault_id, [f'bare/data/{i}' for i in ids]).items():
                if blob and writer.save(c.sg_dir, fid, blob, read_key=c.read_key) == writer.VERIFIED:
                    fetched[0] += 1

        walked = scoped.walk_fetch([str(commit.tree_id)], c.read_key, only, on_batch_missing=download)
        blobs  = [b for b in sorted(walked['small_blobs'] | walked['large_blobs']) if not c.obj_store.exists(b)]
        if blobs:
            _p('download', f'Fetching {folder}', f'0/{len(blobs)}')
            done = 0
            for i in range(0, len(blobs), 50):
                chunk = blobs[i:i + 50]
                for fid, blob in self.api.batch_read(vault_id, [f'bare/data/{b}' for b in chunk]).items():
                    if blob and writer.save(c.sg_dir, fid, blob, read_key=c.read_key) == writer.VERIFIED:
                        fetched[0] += 1
                done += len(chunk)
                _p('download', f'Fetching {folder}', f'{done}/{len(blobs)}')

        flat, _ = scoped.flatten(str(commit.tree_id), c.read_key, only)
        flat    = {p: e for p, e in flat.items() if not scope.contains_path(p)}   # already held: leave as is
        # Never overwrite local work: a file already on disk under the new folder
        # (untracked from this clone's point of view) is kept unless its bytes
        # already equal what HEAD holds.
        clashes = []
        for path in sorted(flat):
            local_path = os.path.join(directory, path)
            if os.path.isfile(local_path):
                with open(local_path, 'rb') as fh:
                    local_hash = self.crypto.content_hash(fh.read())
                if local_hash != flat[path].get('content_hash', ''):
                    clashes.append(path)
        if clashes:
            shown = ', '.join(clashes[:5]) + (f' (+{len(clashes) - 5} more)' if len(clashes) > 5 else '')
            raise Vault__Scoped_Clone_Error(
                f'cannot widen to {folder}: files already on disk there differ from the vault and '
                f'would be overwritten: {shown}. Move them aside first; nothing was changed.')
        self._checkout_flat_map(directory, flat, c.obj_store, c.read_key)

        cfg.scope_paths = wider.folders()
        self._write_local_config(directory, c.storage, cfg)
        return dict(folder=folder, already_held=False, fetched=fetched[0], written=len(flat),
                    scope_paths=wider.folders())

    # ----------------------------------------------------------- unshallow
    def unshallow(self, directory: str, on_progress: callable = None) -> dict:
        _p    = on_progress or (lambda *a, **k: None)
        c     = self._init_components(directory)
        cfg   = self._read_local_config(directory, c.storage)
        scope = Vault__Scope().from_local_config(cfg)
        if not scope.is_shallow():
            return dict(fetched=0, already_full=True)
        vault_id = str(c.vault_id)
        writer   = Vault__Verified_Write(crypto=self.crypto)
        vc       = Vault__Commit(crypto=self.crypto, pki=PKI__Crypto(), object_store=c.obj_store, ref_manager=c.ref_manager)
        fetched  = 0

        if scope.is_scoped():
            # commits only: history for log/status; trees and blobs stay scoped
            queue   = scope.boundary_ids()
            visited = set()
            level   = 0
            while queue:
                level += 1
                parents = []
                for cid in queue:
                    if cid in visited:
                        continue
                    visited.add(cid)
                    try:
                        parents += [str(pp) for pp in (vc.load_commit(cid, c.read_key).parents or []) if str(pp)]
                    except Exception:
                        pass
                missing = [pid for pid in set(parents) if not c.obj_store.exists(pid)]
                if missing:
                    _p('scan', 'Fetching history', f'level {level}: {len(missing)} commit(s)')
                    for fid, blob in self.api.batch_read(vault_id, [f'bare/data/{m}' for m in missing]).items():
                        if blob and writer.save(c.sg_dir, fid, blob, read_key=c.read_key) == writer.VERIFIED:
                            fetched += 1
                queue = [pid for pid in set(parents) if pid not in visited]
        else:
            # whole-vault clone: everything, in one sweep (history commands need trees and blobs too)
            from sgit_ai.workflow.clone.Step__Clone__Bulk_Fetch import Step__Clone__Bulk_Fetch
            step = Step__Clone__Bulk_Fetch()
            class _WS:                                             # the step's workspace surface
                sync_client = self
                obj_store   = c.obj_store
                def progress(self_, *a, **k): _p(*a, **k)
                def save_file(self_, sg_dir, fid, data, read_key=None):
                    return writer.save(sg_dir, fid, data, read_key=read_key) == writer.VERIFIED
            ids = step.list_object_ids(_WS(), vault_id)
            if ids is None:
                raise RuntimeError('the server cannot list the store; cannot unshallow a whole-vault clone this way')
            wanted  = [oid for oid in ids if not c.obj_store.exists(oid)]
            fetched = step.fetch_all(_WS(), vault_id, c.sg_dir, c.read_key, wanted)

        cfg.shallow_boundaries = []
        self._write_local_config(directory, c.storage, cfg)
        return dict(fetched=fetched, already_full=False)

    # ------------------------------------------------------------- helpers
    def _local_head_commit_id(self, directory: str, c, cfg) -> str:
        index_id = c.branch_index_file_id
        if not index_id:
            return ''
        branch_index = c.branch_manager.load_branch_index(directory, index_id, c.read_key)
        branch_id    = str(cfg.my_branch_id) if cfg.my_branch_id else ''
        meta         = (c.branch_manager.get_branch_by_id(branch_index, branch_id) if branch_id
                        else c.branch_manager.get_branch_by_name(branch_index, 'current'))
        return c.ref_manager.read_ref(str(meta.head_ref_id), c.read_key) or '' if meta else ''

    def _write_local_config(self, directory: str, storage, cfg) -> None:
        config_path = storage.local_config_path(directory)
        with open(config_path, 'w') as f:
            json.dump(cfg.json(), f, indent=2)
