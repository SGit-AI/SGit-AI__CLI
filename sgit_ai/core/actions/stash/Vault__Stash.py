import io
import json
import os
import time
import zipfile

from osbot_utils.type_safe.Type_Safe         import Type_Safe
from sgit_ai.crypto.Vault__Crypto            import Vault__Crypto
from sgit_ai.safe_types.Safe_UInt__Timestamp import Safe_UInt__Timestamp
from sgit_ai.schemas.Schema__Stash_Meta      import Schema__Stash_Meta
from sgit_ai.core.actions.revert.Vault__Revert              import Vault__Revert
from sgit_ai.storage.Vault__Storage             import SG_VAULT_DIR

STASH_DIR    = 'stash'
STASH_PREFIX = 'stash-'
META_FILENAME = 'stash-meta.json'


class Vault__Stash(Type_Safe):
    crypto : Vault__Crypto

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def stash(self, directory: str) -> dict:
        """Save uncommitted changes to a stash zip and revert to HEAD.

        Returns dict with status, stash_path, meta, or 'nothing_to_stash'.
        """
        revert = Vault__Revert(crypto=self.crypto)
        c      = revert._init_components(directory)

        # Check if there is anything to stash
        status = self._compute_status(directory, c, revert)
        if status['clean']:
            return dict(nothing_to_stash=True, status=status)

        # Resolve HEAD commit id for meta
        head_commit_id = revert._resolve_head_commit_id(c, directory)

        meta = Schema__Stash_Meta(
            created_at     = Safe_UInt__Timestamp(int(time.time() * 1000)),
            files_added    = status['added'],
            files_modified = status['modified'],
            files_deleted  = status['deleted'],
        )
        if head_commit_id:
            from sgit_ai.safe_types.Safe_Str__Object_Id import Safe_Str__Object_Id
            meta.base_commit = Safe_Str__Object_Id(head_commit_id)

        # Build zip with added + modified files
        stash_dir  = self._stash_dir(directory)
        os.makedirs(stash_dir, exist_ok=True)
        timestamp  = int(meta.created_at)
        zip_name   = f'{STASH_PREFIX}{timestamp}.zip'
        zip_path   = os.path.join(stash_dir, zip_name)
        meta_path  = os.path.join(stash_dir, f'{STASH_PREFIX}{timestamp}.{META_FILENAME}')

        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            for rel_path in status['added'] + status['modified']:
                full_path = os.path.join(directory, rel_path)
                if os.path.isfile(full_path):
                    zf.write(full_path, rel_path)

        with open(meta_path, 'w') as fh:
            json.dump(meta.json(), fh, indent=2)

        # Revert working copy to HEAD
        revert.revert_all_to_head(directory)

        return dict(nothing_to_stash=False, stash_path=zip_path, meta=meta,
                    status=status)

    def pop(self, directory: str) -> dict:
        """Restore the most recent stash and remove it.

        Returns dict with stash_path, applied meta, restored/deleted lists.
        """
        stash_dir = self._stash_dir(directory)
        entry     = self._find_latest_stash(stash_dir)
        if not entry:
            return dict(no_stash=True)

        zip_path, meta_path, meta = entry

        # Restore added + modified files from zip
        restored = []
        with zipfile.ZipFile(zip_path, 'r') as zf:
            for name in zf.namelist():
                full_path = os.path.join(directory, name)
                dir_part  = os.path.dirname(full_path)
                if dir_part:
                    os.makedirs(dir_part, exist_ok=True)
                with zf.open(name) as src, open(full_path, 'wb') as dst:
                    dst.write(src.read())
                restored.append(name)

        # Handle deleted files (remove them from working copy)
        deleted_applied = []
        for rel_path in meta.files_deleted:
            full_path = os.path.join(directory, rel_path)
            if os.path.isfile(full_path):
                os.remove(full_path)
                deleted_applied.append(rel_path)

        # Remove the stash files
        os.remove(zip_path)
        if os.path.isfile(meta_path):
            os.remove(meta_path)

        return dict(no_stash=False, stash_path=zip_path, meta=meta,
                    restored=restored, deleted=deleted_applied)

    def list_stashes(self, directory: str) -> list:
        """Return list of stash entries sorted newest-first.

        Each entry is a dict with keys: zip_path, meta_path, meta, timestamp.
        """
        stash_dir = self._stash_dir(directory)
        if not os.path.isdir(stash_dir):
            return []
        entries = []
        for filename in os.listdir(stash_dir):
            if filename.startswith(STASH_PREFIX) and filename.endswith('.zip'):
                zip_path  = os.path.join(stash_dir, filename)
                meta_path = self._meta_path_for_zip(stash_dir, filename)
                meta      = self._load_meta(meta_path)
                timestamp = self._timestamp_from_zip_name(filename)
                entries.append(dict(zip_path=zip_path, meta_path=meta_path,
                                    meta=meta, timestamp=timestamp))
        entries.sort(key=lambda e: e['timestamp'], reverse=True)
        return entries

    def drop(self, directory: str) -> dict:
        """Drop (remove) the most recent stash without applying it."""
        stash_dir = self._stash_dir(directory)
        entry     = self._find_latest_stash(stash_dir)
        if not entry:
            return dict(no_stash=True)
        zip_path, meta_path, meta = entry
        os.remove(zip_path)
        if os.path.isfile(meta_path):
            os.remove(meta_path)
        return dict(no_stash=False, dropped_path=zip_path, meta=meta)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _stash_dir(self, directory: str) -> str:
        return os.path.join(directory, SG_VAULT_DIR, 'local', STASH_DIR)

    def _find_latest_stash(self, stash_dir: str):
        """Return (zip_path, meta_path, meta) for the most recent stash, or None."""
        if not os.path.isdir(stash_dir):
            return None
        entries = self.list_stashes(os.path.dirname(
            os.path.dirname(os.path.dirname(stash_dir))))
        if not entries:
            return None
        e = entries[0]
        return e['zip_path'], e['meta_path'], e['meta']

    def _compute_status(self, directory: str, c, revert: Vault__Revert) -> dict:
        """Compute added/modified/deleted using the same logic as Vault__Sync.status."""
        from sgit_ai.storage.Vault__Sub_Tree import Vault__Sub_Tree
        from sgit_ai.storage.Vault__Commit import Vault__Commit

        storage        = c.storage
        branch_manager = c.branch_manager
        ref_manager    = c.ref_manager
        read_key       = c.read_key
        obj_store      = c.obj_store
        pki            = c.pki
        sg_dir         = c.sg_dir

        local_config = revert._read_local_config(directory, storage)
        branch_id    = str(local_config.my_branch_id)

        index_id = c.branch_index_file_id
        if not index_id:
            return dict(added=[], modified=[], deleted=[], clean=True)

        branch_index = branch_manager.load_branch_index(directory, index_id, read_key)
        branch_meta  = branch_manager.get_branch_by_id(branch_index, branch_id)
        if not branch_meta:
            return dict(added=[], modified=[], deleted=[], clean=True)

        ref_id    = str(branch_meta.head_ref_id)
        parent_id = ref_manager.read_ref(ref_id, read_key)

        old_entries = {}
        if parent_id:
            vault_commit = Vault__Commit(crypto=self.crypto, pki=pki,
                                         object_store=obj_store, ref_manager=ref_manager)
            old_commit   = vault_commit.load_commit(parent_id, read_key)
            sub_tree     = Vault__Sub_Tree(crypto=self.crypto, obj_store=obj_store)
            old_entries  = sub_tree.flatten(str(old_commit.tree_id), read_key)

        ignore       = __import__('sgit_ai.sync.Vault__Ignore', fromlist=['Vault__Ignore']).Vault__Ignore
        vault_ignore = ignore().load_gitignore(directory)
        new_file_map = {}
        import os as _os
        for root, dirs, files in _os.walk(directory):
            rel_root = _os.path.relpath(root, directory).replace(_os.sep, '/')
            if rel_root == '.':
                rel_root = ''
            dirs[:] = [d for d in dirs
                       if not vault_ignore.should_ignore_dir(
                           f'{rel_root}/{d}' if rel_root else d)]
            for filename in files:
                rel_path = f'{rel_root}/{filename}' if rel_root else filename
                if vault_ignore.should_ignore_file(rel_path):
                    continue
                new_file_map[rel_path] = True

        old_paths = set(old_entries.keys())
        new_paths = set(new_file_map.keys())

        added    = sorted(new_paths - old_paths)
        deleted  = sorted(old_paths - new_paths)
        modified = []
        for path in sorted(old_paths & new_paths):
            local_file = _os.path.join(directory, path)
            with open(local_file, 'rb') as fh:
                content = fh.read()
            old_entry = old_entries[path]
            old_hash  = old_entry.get('content_hash', '')
            file_hash = self.crypto.content_hash(content)
            if old_hash and old_hash != file_hash:
                modified.append(path)
            elif not old_hash and len(content) != old_entry.get('size', -1):
                modified.append(path)

        return dict(added=added, modified=modified, deleted=deleted,
                    clean=not added and not modified and not deleted)

    def _meta_path_for_zip(self, stash_dir: str, zip_filename: str) -> str:
        base = zip_filename[:-4]  # strip .zip
        return os.path.join(stash_dir, f'{base}.{META_FILENAME}')

    def _load_meta(self, meta_path: str) -> Schema__Stash_Meta:
        if not os.path.isfile(meta_path):
            return Schema__Stash_Meta()
        with open(meta_path, 'r') as fh:
            data = json.load(fh)
        return Schema__Stash_Meta.from_json(data)

    def _timestamp_from_zip_name(self, zip_filename: str) -> int:
        # stash-{timestamp}.zip
        try:
            name = zip_filename[len(STASH_PREFIX):-4]  # strip prefix + .zip
            return int(name)
        except ValueError:
            return 0
