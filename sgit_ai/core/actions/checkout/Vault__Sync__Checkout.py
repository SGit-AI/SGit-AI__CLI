"""Vault__Sync__Checkout — `sgit checkout`: write tracked files into a selective working
copy (a clone made with --no-checkout or --sparse), from the local store when the
objects are here (a pack vault's packs brought them) and from the host otherwise.

    sgit checkout <path> [<path> ...]      a file, or a folder and everything under it
    sgit checkout --since-pull             what the last pull added or changed
    sgit checkout --changed-since <commit> what changed between that commit and HEAD
    sgit checkout --all                    everything: the clone becomes a full one

Every write goes through the same writer a pull uses (the scan cache learns the
bytes written) and is recorded in the checkout set, so a later deletion of a
checked-out file is a deletion and a file never checked out is not. `sgit fetch
<path>` is the same action under its older name.
"""
import os
from sgit_ai.core.actions.sparse.Vault__Sync__Sparse   import Vault__Sync__Sparse
from sgit_ai.storage.Vault__Checkout_Set               import Vault__Checkout_Set
from sgit_ai.storage.Vault__Sub_Tree                   import Vault__Sub_Tree

LARGE_THRESHOLD = 2 * 1024 * 1024


class Vault__Sync__Checkout(Vault__Sync__Sparse):

    def checkout(self, directory: str, paths: list = None, since_pull: bool = False, changed_since: str = None,
                 all_files: bool = False, on_progress: callable = None) -> dict:
        _p = on_progress or (lambda *a, **k: None)
        self._ensure_head_local(directory, on_progress)
        self._require_readable_tracked_ref(directory)
        flat, obj_store, read_key, vault_id, sg_dir = self._get_head_flat_map(directory)
        cset   = Vault__Checkout_Set()
        wanted, not_found = self.select(directory, flat, obj_store, read_key, paths, since_pull, changed_since, all_files)
        entries = {p: flat[p] for p in wanted if flat[p].get('blob_id')}
        to_download = [p for p, e in entries.items() if not obj_store.exists(str(e['blob_id']))]
        already     = len(entries) - len(to_download)
        if to_download:
            self._download(vault_id, sg_dir, read_key, {p: entries[p] for p in to_download}, _p)
        writable = {p: e for p, e in entries.items() if obj_store.exists(str(e['blob_id']))}
        missing  = sorted(p for p in entries if p not in writable)
        self._checkout_flat_map(directory, writable, obj_store, read_key)       # seeds the scan cache
        cset.add(directory, list(writable))
        if all_files:
            self._make_full(directory, cset)
        return dict(written=sorted(writable), fetched=len(to_download), already_local=already,
                    not_found=not_found, missing=missing, total=len(flat))

    def select(self, directory: str, flat: dict, obj_store, read_key: bytes, paths, since_pull: bool,
               changed_since: str, all_files: bool) -> tuple:
        """(paths to write, paths asked for that the head does not track)."""
        if all_files:
            return sorted(flat), []
        chosen, not_found = set(), []
        if since_pull:
            last = Vault__Checkout_Set().last_pull(directory)
            if last is None:
                raise RuntimeError('no pull has been recorded on this clone yet: run sgit pull first')
            already = set(last.get('written') or [])                       # what that pull wrote is current
            for p in list(last.get('added') or []) + list(last.get('modified') or []):
                if p in flat and p not in already:
                    chosen.add(p)
        if changed_since:
            chosen |= self._changed_since(directory, flat, obj_store, read_key, changed_since)
        for raw in (paths or []):
            path   = str(raw).strip().strip('/').replace(os.sep, '/')
            prefix = path + '/'
            hits   = [p for p in flat if p == path or p.startswith(prefix)] if path else sorted(flat)
            if not hits:
                not_found.append(path)
            chosen.update(hits)
        return sorted(chosen), not_found

    def _changed_since(self, directory: str, flat: dict, obj_store, read_key: bytes, commit_id: str) -> set:
        from sgit_ai.core.actions.pack.Vault__Packs import Vault__Packs
        c      = self._init_components(directory)
        head   = self._local_head_commit(directory, c)
        packs  = Vault__Packs(crypto=self.crypto, api=self.api)
        sg_dir = c.sg_dir
        if not head or not obj_store.exists(commit_id):
            raise RuntimeError(f'commit {commit_id} is not in this clone')
        old_tree = packs._vault_commit(sg_dir).load_commit(commit_id, read_key).tree_id
        new_tree = packs._vault_commit(sg_dir).load_commit(head, read_key).tree_id
        diff     = Vault__Sub_Tree(crypto=self.crypto, obj_store=obj_store).diff_trees(str(new_tree), str(old_tree) if old_tree else None, read_key)
        return {p for p in list(diff['added']) + list(diff['modified']) if p in flat}

    def _download(self, vault_id: str, sg_dir: str, read_key: bytes, entries: dict, _p) -> None:
        """Blobs this clone lacks (a loose sparse clone), verified before they are written."""
        small = [e for e in entries.values() if not e.get('large') and int(e.get('size', 0)) <= LARGE_THRESHOLD]
        large = [e for e in entries.values() if e.get('large') or int(e.get('size', 0)) > LARGE_THRESHOLD]
        total, done = len(entries), 0
        _p('download', 'Fetching objects', f'0/{total}')
        if small:
            fids = [f'bare/data/{e["blob_id"]}' for e in small]
            for fid, data in (self.api.batch_read(vault_id, fids) or {}).items():
                if data:
                    self._save_verified(sg_dir, fid, data, read_key)
                done += 1
                _p('download', 'Fetching objects', f'{done}/{total}')
        for e in large:
            fid  = f'bare/data/{e["blob_id"]}'
            data = self.api.read_large(vault_id, fid)
            if data:
                self._save_verified(sg_dir, fid, data, read_key)
            done += 1
            _p('download', 'Fetching objects', f'{done}/{total}')

    def _make_full(self, directory: str, cset: Vault__Checkout_Set) -> None:
        """`checkout --all`: the clone is a full one from here: no sparse flag, no record."""
        c   = self._init_components(directory)
        cfg = self._read_local_config(directory, c.storage)
        if cfg.sparse:
            cfg.sparse = False
            c.storage.write_local_config(directory, cfg.json())
        cset.remove(directory)

    def not_checked_out(self, directory: str) -> dict:
        """{'total': tracked files, 'checked_out': n, 'paths': [...]} for a selective clone."""
        flat, obj_store, read_key, vault_id, sg_dir = self._get_head_flat_map(directory)
        c      = self._init_components(directory)
        sparse = bool(self._read_local_config(directory, c.storage).sparse)
        cset   = Vault__Checkout_Set()
        paths  = cset.load(directory) if sparse else None
        absent = sorted(p for p, e in flat.items() if not cset.materialised(p, e, obj_store, sparse, paths))
        return dict(total=len(flat), checked_out=len(flat) - len(absent), paths=absent)
