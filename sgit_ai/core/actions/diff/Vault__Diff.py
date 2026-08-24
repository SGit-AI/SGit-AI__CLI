import difflib
import hashlib
import json
import os

from osbot_utils.type_safe.Type_Safe               import Type_Safe
from sgit_ai.crypto.Vault__Crypto                  import Vault__Crypto
from sgit_ai.crypto.PKI__Crypto                    import PKI__Crypto
from sgit_ai.storage.Vault__Object_Store           import Vault__Object_Store
from sgit_ai.storage.Vault__Ref_Manager            import Vault__Ref_Manager
from sgit_ai.storage.Vault__Commit                 import Vault__Commit
from sgit_ai.safe_types.Safe_Str__Diff_Mode        import Safe_Str__Diff_Mode
from sgit_ai.schemas.Schema__Diff_File             import Schema__Diff_File
from sgit_ai.schemas.Schema__Diff_Result           import Schema__Diff_Result
from sgit_ai.storage.Vault__Branch_Manager            import Vault__Branch_Manager
from sgit_ai.core.Vault__Components                import Vault__Components
from sgit_ai.core.Vault__Ignore                    import Vault__Ignore
from sgit_ai.crypto.Vault__Key_Manager             import Vault__Key_Manager
from sgit_ai.storage.Vault__Storage                   import Vault__Storage, SG_VAULT_DIR
from sgit_ai.storage.Vault__Sub_Tree                  import Vault__Sub_Tree
from sgit_ai.network.api.Vault__API                   import Vault__API

BINARY_CHECK_BYTES = 8192


class Vault__Diff(Type_Safe):
    crypto : Vault__Crypto
    api    : Vault__API = None       # optional: enables read-only on-demand object fetch (A3)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def diff_vs_head(self, directory: str) -> Schema__Diff_Result:
        """Compare working copy vs last local commit (HEAD)."""
        c = self._init_components(directory)
        committed_files = self._read_head_files(c)
        working_files   = self._scan_working_files(directory, c)
        diff_files      = self.diff_files(working_files, committed_files)
        return self._build_result(directory, 'head', '', diff_files)

    def diff_vs_remote(self, directory: str) -> Schema__Diff_Result:
        """Compare working copy vs named branch HEAD."""
        c = self._init_components(directory)
        committed_files = self._read_named_branch_files(c, directory)
        working_files   = self._scan_working_files(directory, c)
        diff_files      = self.diff_files(working_files, committed_files)
        return self._build_result(directory, 'remote', '', diff_files)

    def diff_vs_commit(self, directory: str, commit_id: str) -> Schema__Diff_Result:
        """Compare working copy vs a specific commit."""
        c = self._init_components(directory)
        committed_files = self._read_commit_files(c, commit_id)
        working_files   = self._scan_working_files(directory, c)
        diff_files      = self.diff_files(working_files, committed_files)
        return self._build_result(directory, 'commit', commit_id, diff_files)

    def diff_commits(self, directory: str, commit_a: str, commit_b: str) -> Schema__Diff_Result:
        """Compare two specific commits directly (commit_a = before, commit_b = after)."""
        c        = self._init_components(directory)
        files_a  = self._read_commit_files(c, commit_a)
        files_b  = self._read_commit_files(c, commit_b)
        # diff_files(working=NEW, committed=OLD): before=OLD=files_a, after=NEW=files_b
        diff_files = self.diff_files(files_b, files_a)
        result = self._build_result(directory, 'commits', commit_a, diff_files)
        result.commit_id_b = commit_b
        return result

    def show_commit(self, directory: str, commit_id: str) -> tuple:
        """Return (commit_info dict, Schema__Diff_Result) for a specific commit vs its parent.

        commit_info keys: commit_id, timestamp_ms, message, parent_id, branch_id
        If the commit has no parent, diffs against an empty tree.
        """
        import datetime
        c            = self._init_components(directory)
        pki          = c.pki
        obj_store    = c.obj_store
        ref_manager  = c.ref_manager
        read_key     = c.read_key

        vault_commit = Vault__Commit(crypto=self.crypto, pki=pki,
                                     object_store=obj_store, ref_manager=ref_manager)
        commit_obj   = vault_commit.load_commit(commit_id, read_key)

        # Decrypt commit message
        message = ''
        if commit_obj.message_enc:
            try:
                message = self.crypto.decrypt_metadata(read_key, str(commit_obj.message_enc))
            except Exception:
                message = '(encrypted — could not decrypt)'

        ts_ms     = int(commit_obj.timestamp_ms) if commit_obj.timestamp_ms else 0
        ts_str    = datetime.datetime.fromtimestamp(ts_ms / 1000,
                                                     tz=datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
        parent_id = str(commit_obj.parents[0]) if commit_obj.parents else None

        commit_info = dict(commit_id  = commit_id,
                           timestamp  = ts_str,
                           timestamp_ms = ts_ms,
                           message    = message,
                           parent_id  = parent_id,
                           branch_id  = str(commit_obj.branch_id) if commit_obj.branch_id else '')

        files_before = self._read_commit_files(c, parent_id) if parent_id else {}
        files_after  = self._read_commit_files(c, commit_id)
        # diff_files(working=NEW=files_after, committed=OLD=files_before)
        diff_files   = self.diff_files(files_after, files_before)
        result       = self._build_result(directory, 'commits', parent_id or '', diff_files)
        result.commit_id_b = commit_id

        return commit_info, result

    def log_file(self, directory: str, file_path: str, limit: int = 0) -> list:
        """Return commits that touched file_path, newest first.

        Each entry: {commit_id, timestamp_ms, timestamp, message, parent_id, status}
        status: 'added' | 'modified' | 'deleted'
        Compares blob_ids only — no blob content decryption.
        limit=0 means no limit (walk entire local history).
        """
        import datetime
        c         = self._init_components(directory)
        obj_store = c.obj_store
        read_key  = c.read_key
        pki       = c.pki
        ref_manager = c.ref_manager

        vault_commit = Vault__Commit(crypto=self.crypto, pki=pki,
                                     object_store=obj_store, ref_manager=ref_manager)
        sub_tree = Vault__Sub_Tree(crypto=self.crypto, obj_store=obj_store)

        def _blob_id_in_tree(tree_id):
            if not tree_id:
                return None
            try:
                flat = sub_tree.flatten(tree_id, read_key)
                entry = flat.get(file_path)
                return entry['blob_id'] if entry else None
            except Exception:
                return None

        # Resolve HEAD commit
        from sgit_ai.storage.Vault__Storage import Vault__Storage
        from sgit_ai.storage.Vault__Branch_Manager import Vault__Branch_Manager
        from sgit_ai.schemas.Schema__Local_Config import Schema__Local_Config
        import json as _json

        storage        = c.storage
        branch_manager = c.branch_manager
        sg_dir         = c.sg_dir
        dir_           = os.path.dirname(sg_dir)

        config_path = storage.local_config_path(dir_)
        with open(config_path, 'r') as f:
            config_data = _json.load(f)
        local_config = Schema__Local_Config.from_json(config_data)
        branch_id    = str(local_config.my_branch_id)

        index_id     = c.branch_index_file_id
        branch_index = branch_manager.load_branch_index(dir_, index_id, read_key)
        branch_meta  = branch_manager.get_branch_by_id(branch_index, branch_id)
        if not branch_meta:
            return []

        current_id = ref_manager.read_ref(str(branch_meta.head_ref_id), read_key)
        if not current_id:
            return []

        results = []
        count   = 0
        while current_id:
            if not obj_store.exists(current_id):
                break
            try:
                commit_obj = vault_commit.load_commit(current_id, read_key)
            except Exception:
                break

            tree_id   = str(commit_obj.tree_id) if commit_obj.tree_id else None
            parents   = [str(p) for p in commit_obj.parents] if commit_obj.parents else []
            parent_id = parents[0] if parents else None

            blob_now    = _blob_id_in_tree(tree_id)
            parent_tree = None
            if parent_id and obj_store.exists(parent_id):
                try:
                    parent_obj  = vault_commit.load_commit(parent_id, read_key)
                    parent_tree = str(parent_obj.tree_id) if parent_obj.tree_id else None
                except Exception:
                    pass
            blob_before = _blob_id_in_tree(parent_tree)

            if blob_now != blob_before:
                if blob_before is None:
                    status = 'added'
                elif blob_now is None:
                    status = 'deleted'
                else:
                    status = 'modified'

                message = ''
                if commit_obj.message_enc:
                    try:
                        message = self.crypto.decrypt_metadata(read_key, str(commit_obj.message_enc))
                    except Exception:
                        message = '(encrypted)'

                ts_ms  = int(commit_obj.timestamp_ms) if commit_obj.timestamp_ms else 0
                ts_str = datetime.datetime.fromtimestamp(ts_ms / 1000,
                                                          tz=datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
                results.append(dict(commit_id    = current_id,
                                    timestamp_ms = ts_ms,
                                    timestamp    = ts_str,
                                    message      = message,
                                    parent_id    = parent_id,
                                    status       = status))
                count += 1
                if limit and count >= limit:
                    break

            current_id = parent_id

        return results

    # ------------------------------------------------------------------
    # Range-based history
    # ------------------------------------------------------------------

    def commits_in_range(self, directory: str, from_commit: str = '',
                         to_commit: str = '') -> list:
        """Return commit IDs in <from>..<to>, oldest-first.

        <from> is exclusive; <to> is inclusive. Empty <to> → HEAD.
        Empty <from> → walk to root. Raises RuntimeError if <from> is
        provided but not an ancestor of <to>.
        """
        c            = self._init_components(directory)
        obj_store    = c.obj_store
        ref_manager  = c.ref_manager
        read_key     = c.read_key
        vault_commit = Vault__Commit(crypto=self.crypto, pki=c.pki,
                                     object_store=obj_store, ref_manager=ref_manager)

        resolved_to = to_commit or self._resolve_head_commit(c, directory)
        if not resolved_to:
            return []

        resolved_from = from_commit  # may be empty (open-ended)

        collected  = []
        current_id = resolved_to
        found_from = not resolved_from

        while current_id:
            if not obj_store.exists(current_id):
                break
            if current_id == resolved_from:
                found_from = True
                break
            try:
                commit_obj = vault_commit.load_commit(current_id, read_key)
            except Exception:
                break
            collected.append(current_id)
            parents    = [str(p) for p in commit_obj.parents] if commit_obj.parents else []
            current_id = parents[0] if parents else None

        if resolved_from and not found_from:
            raise RuntimeError(
                f'{from_commit!r} is not an ancestor of '
                f'{to_commit or "HEAD"!r}'
            )

        collected.reverse()
        return collected

    def log_range_with_details(self, directory: str, from_commit: str = '',
                               to_commit: str = '', include_files: bool = False,
                               include_patch: bool = False, limit: int = None):
        """Return Schema__History_Log_Result for commits in <from>..<to>.

        Used by JSON output and human-readable --files/--patch modes. When ``limit``
        is set, only the most recent ``limit`` commits in the range are returned
        (so `-n/--limit` behaves the same as on the plain log).
        """
        import datetime
        from sgit_ai.schemas.history.Schema__History_Log_Result       import Schema__History_Log_Result
        from sgit_ai.schemas.history.Schema__History_Log_Commit_Entry import Schema__History_Log_Commit_Entry

        commit_ids = self.commits_in_range(directory, from_commit, to_commit)
        if limit and limit > 0:
            commit_ids = commit_ids[-limit:]            # most recent N (commits are oldest-first)

        # Resolve actual to_commit (HEAD if not specified)
        resolved_to = to_commit
        if not resolved_to:
            c           = self._init_components(directory)
            resolved_to = self._resolve_head_commit(c, directory) or ''

        entries = []
        for cid in commit_ids:
            commit_info, diff_result = self.show_commit(directory, cid)

            ts_ms = commit_info['timestamp_ms']
            ts_iso = (datetime.datetime.fromtimestamp(ts_ms / 1000, tz=datetime.timezone.utc)
                      .strftime('%Y-%m-%dT%H:%M:%SZ')) if ts_ms else ''

            parent_ids     = [commit_info['parent_id']] if commit_info['parent_id'] else []
            files_added    = []
            files_modified = []
            files_deleted  = []

            if include_files or include_patch:
                for f in diff_result.files:
                    status = str(f.status) if f.status else ''
                    path   = str(f.path)   if f.path   else ''
                    if status == 'added':
                        files_added.append(path)
                    elif status == 'modified':
                        files_modified.append(path)
                    elif status == 'deleted':
                        files_deleted.append(path)

            patch_text = ''
            if include_patch:
                parts = []
                for f in diff_result.files:
                    if str(f.status) not in ('added', 'modified', 'deleted'):
                        continue
                    dt = str(f.diff_text) if f.diff_text else ''
                    if dt:
                        parts.append(dt)
                patch_text = ''.join(parts)

            entries.append(Schema__History_Log_Commit_Entry(
                commit_id      = cid,
                parent_ids     = parent_ids,
                timestamp_ms   = ts_ms,
                timestamp_iso  = ts_iso,
                message        = commit_info['message'] or '',
                branch_id      = commit_info['branch_id'] or '',
                files_added    = files_added,
                files_modified = files_modified,
                files_deleted  = files_deleted,
                patch          = patch_text or '',
            ))

        return Schema__History_Log_Result(
            schema       = 'history_log_v1',
            from_commit  = from_commit,
            to_commit    = resolved_to,
            commit_count = len(entries),
            commits      = entries,
        )

    def diff_range(self, directory: str, from_commit: str,
                   to_commit: str, include_patch: bool = True):
        """Return Schema__History_Diff_Result for aggregate diff between two commits."""
        from sgit_ai.schemas.history.Schema__History_Diff_Result import Schema__History_Diff_Result
        from sgit_ai.schemas.history.Schema__History_Diff_File   import Schema__History_Diff_File

        diff_result = self.diff_commits(directory, from_commit, to_commit)

        files_added    = []
        files_modified = []
        files_deleted  = []
        patch_parts    = []

        for f in diff_result.files:
            status = str(f.status) if f.status else ''
            path   = str(f.path)   if f.path   else ''
            if status == 'added':
                files_added.append(path)
            elif status == 'modified':
                la = 0
                lr = 0
                if f.diff_text:
                    for line in str(f.diff_text).splitlines():
                        if line.startswith('+') and not line.startswith('+++'):
                            la += 1
                        elif line.startswith('-') and not line.startswith('---'):
                            lr += 1
                files_modified.append(Schema__History_Diff_File(
                    path=path, lines_added=la, lines_removed=lr))
                if include_patch and f.diff_text:
                    patch_parts.append(str(f.diff_text))
            elif status == 'deleted':
                files_deleted.append(path)

        if include_patch:
            for f in diff_result.files:
                if str(f.status) == 'added' and f.diff_text:
                    patch_parts.append(str(f.diff_text))

        return Schema__History_Diff_Result(
            schema         = 'history_diff_v1',
            from_commit    = from_commit,
            to_commit      = to_commit,
            files_added    = files_added,
            files_modified = files_modified,
            files_deleted  = files_deleted,
            patch          = ''.join(patch_parts) if include_patch else '',
        )

    # ------------------------------------------------------------------
    # Private range helpers
    # ------------------------------------------------------------------

    def _resolve_head_commit(self, c, directory: str) -> str:
        """Return HEAD commit ID for the local branch, or '' if not found."""
        from sgit_ai.schemas.Schema__Local_Config import Schema__Local_Config
        import json as _json

        storage        = c.storage
        branch_manager = c.branch_manager
        ref_manager    = c.ref_manager
        read_key       = c.read_key

        config_path = storage.local_config_path(directory)
        try:
            with open(config_path, 'r') as f:
                config_data = _json.load(f)
        except Exception:
            return ''

        local_config = Schema__Local_Config.from_json(config_data)
        branch_id    = str(local_config.my_branch_id)
        index_id     = c.branch_index_file_id

        try:
            branch_index = branch_manager.load_branch_index(directory, index_id, read_key)
            branch_meta  = branch_manager.get_branch_by_id(branch_index, branch_id)
            if not branch_meta:
                return ''
            commit_id = ref_manager.read_ref(str(branch_meta.head_ref_id), read_key)
            return commit_id or ''
        except Exception:
            return ''

    def diff_files(self, working_files: dict, committed_files: dict) -> list:
        """Core diff logic: compare two {path: bytes} dicts.

        Returns list[Schema__Diff_File].
        """
        all_paths = set(working_files.keys()) | set(committed_files.keys())
        result    = []
        for path in sorted(all_paths):
            before = committed_files.get(path)
            after  = working_files.get(path)
            result.append(self.diff_single_file(path, before, after))
        return result

    def diff_single_file(self, path: str, before, after) -> Schema__Diff_File:
        """Diff one file. before/after are bytes or None."""
        if before is None and after is None:
            return Schema__Diff_File(path=path, status='unchanged')

        if before is None:
            # added
            return Schema__Diff_File(
                path        = path,
                status      = 'added',
                is_binary   = self._is_binary(after),
                size_before = 0,
                size_after  = len(after),
                hash_before = None,
                hash_after  = self._sha256(after),
                diff_text   = None,
            )

        if after is None:
            # deleted
            return Schema__Diff_File(
                path        = path,
                status      = 'deleted',
                is_binary   = self._is_binary(before),
                size_before = len(before),
                size_after  = 0,
                hash_before = self._sha256(before),
                hash_after  = None,
                diff_text   = None,
            )

        # both exist — check if changed
        hash_before = self._sha256(before)
        hash_after  = self._sha256(after)

        if hash_before == hash_after:
            return Schema__Diff_File(
                path        = path,
                status      = 'unchanged',
                is_binary   = self._is_binary(before),
                size_before = len(before),
                size_after  = len(after),
                hash_before = hash_before,
                hash_after  = hash_after,
                diff_text   = None,
            )

        # modified
        is_binary = self._is_binary(before) or self._is_binary(after)
        diff_text = None
        if not is_binary:
            diff_text = self._unified_diff(path, before, after)

        return Schema__Diff_File(
            path        = path,
            status      = 'modified',
            is_binary   = is_binary,
            size_before = len(before),
            size_after  = len(after),
            hash_before = hash_before,
            hash_after  = hash_after,
            diff_text   = diff_text,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _is_binary(self, data: bytes) -> bool:
        return b'\x00' in data[:BINARY_CHECK_BYTES]

    def _sha256(self, data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    def _unified_diff(self, path: str, before: bytes, after: bytes) -> str:
        before_text = before.decode('utf-8', errors='replace').splitlines(keepends=True)
        after_text  = after.decode('utf-8',  errors='replace').splitlines(keepends=True)
        lines = list(difflib.unified_diff(
            before_text,
            after_text,
            fromfile=f'a/{path}',
            tofile=f'b/{path}',
        ))
        return ''.join(lines)

    def _build_result(self, directory: str, mode: str, commit_id: str,
                      diff_file_list: list) -> Schema__Diff_Result:
        added    = sum(1 for f in diff_file_list if f.status == 'added')
        modified = sum(1 for f in diff_file_list if f.status == 'modified')
        deleted  = sum(1 for f in diff_file_list if f.status == 'deleted')
        return Schema__Diff_Result(
            directory      = directory,
            mode           = mode,
            commit_id      = commit_id or None,
            files          = diff_file_list,
            added_count    = added,
            modified_count = modified,
            deleted_count  = deleted,
        )

    def _read_clone_mode_safe(self, directory: str):
        """Load clone_mode.json if present and parseable; else None (full clone).

        Defensive: any read/parse error falls through to the vault_key path so a
        full clone with a missing/corrupt clone_mode.json behaves exactly as before.
        """
        try:
            cm_path = Vault__Storage().clone_mode_path(directory)
            if not os.path.isfile(cm_path):
                return None
            from sgit_ai.schemas.Schema__Clone_Mode import Schema__Clone_Mode
            with open(cm_path) as f:
                return Schema__Clone_Mode.from_json(json.load(f))
        except Exception:
            return None

    def _resolve_keys(self, directory: str) -> tuple:
        """Clone-mode-aware key derivation for the diff/show/log read path.

        Read-only clone (clone_mode.json, READ_ONLY, with read_key+vault_id) → keys
        from `import_read_key` and an empty vault_key (read-only clones never write
        local/vault_key — see the 06/04 read-only-clone contract). Everything else
        (full/headless clone) → the existing vault_key derivation, unchanged.
        """
        from sgit_ai.safe_types.Enum__Clone_Mode import Enum__Clone_Mode
        cm = self._read_clone_mode_safe(directory)
        if cm is not None and cm.mode == Enum__Clone_Mode.READ_ONLY and cm.read_key and cm.vault_id:
            return self.crypto.import_read_key(str(cm.read_key), str(cm.vault_id)), ''
        vault_key_path = os.path.join(directory, SG_VAULT_DIR, 'local', 'vault_key')
        with open(vault_key_path, 'r') as f:
            vault_key = f.read().strip()
        return self.crypto.derive_keys_from_vault_key(vault_key), vault_key

    def _init_components(self, directory: str) -> Vault__Components:
        keys, vault_key = self._resolve_keys(directory)   # clone-mode-aware (full + read-only clones)
        sg_dir  = os.path.join(directory, SG_VAULT_DIR)
        storage = Vault__Storage()
        pki     = PKI__Crypto()

        obj_store      = Vault__Object_Store(vault_path=sg_dir, crypto=self.crypto)
        ref_manager    = Vault__Ref_Manager(vault_path=sg_dir,  crypto=self.crypto)
        key_manager    = Vault__Key_Manager(vault_path=sg_dir,  crypto=self.crypto, pki=pki)
        branch_manager = Vault__Branch_Manager(vault_path    = sg_dir,
                                               crypto        = self.crypto,
                                               key_manager   = key_manager,
                                               ref_manager   = ref_manager,
                                               storage       = storage)
        return Vault__Components(
            vault_key            = vault_key,
            vault_id             = keys['vault_id'],
            read_key             = keys['read_key_bytes'],
            write_key            = keys['write_key'],
            ref_file_id          = keys['ref_file_id'],
            branch_index_file_id = keys['branch_index_file_id'],
            sg_dir               = sg_dir,
            storage              = storage,
            pki                  = pki,
            obj_store            = obj_store,
            ref_manager          = ref_manager,
            key_manager          = key_manager,
            branch_manager       = branch_manager,
        )

    def _read_local_config(self, directory: str, storage: Vault__Storage):
        from sgit_ai.schemas.Schema__Local_Config import Schema__Local_Config
        config_path = storage.local_config_path(directory)
        with open(config_path, 'r') as f:
            data = json.load(f)
        return Schema__Local_Config.from_json(data)

    def _flatten_commit(self, c: Vault__Components, commit_id: str) -> dict:
        """Return flat {path: bytes} for a given commit_id."""
        pki          = c.pki
        obj_store    = c.obj_store
        ref_manager  = c.ref_manager
        read_key     = c.read_key

        vault_commit = Vault__Commit(crypto=self.crypto, pki=pki,
                                     object_store=obj_store, ref_manager=ref_manager)
        commit_obj   = vault_commit.load_commit(commit_id, read_key)
        sub_tree     = Vault__Sub_Tree(crypto=self.crypto, obj_store=obj_store)
        flat_map     = sub_tree.flatten(str(commit_obj.tree_id), read_key)

        result = {}
        for path, entry in flat_map.items():
            blob_id    = entry.get('blob_id')
            if not blob_id:
                continue
            ciphertext = obj_store.load(blob_id)
            plaintext  = self.crypto.decrypt(read_key, ciphertext)
            result[path] = plaintext
        return result

    # ------------------------------------------------------------------
    # Three-way conflict view (A4) — classify each conflicted path against
    # the merge base persisted in Schema__Merge_State (lca / ours / theirs).
    # ------------------------------------------------------------------

    def three_way_conflict_view(self, directory: str, lca_id: str, ours_id: str,
                                theirs_id: str, conflict_paths: list) -> list:
        """Classify each conflicted path against the 3-way merge base.

        verdict:
          'genuine'           both sides changed vs base, to DIFFERENT content
          'identical'         both sides changed vs base, to the SAME content
          'one-sided-ours'    only our side changed vs base
          'one-sided-theirs'  only their side changed vs base
          'no-change'         neither side changed vs base

        Only 'genuine' is a real conflict. The merge engine auto-merges one-sided
        changes, so any other verdict appearing as a conflict means the merge base
        was likely stale/wrong — surfaced as suspect so the user (and we) can spot
        a bad LCA instead of silently dropping a collaborator's content.
        """
        c          = self._init_components(directory)
        read_key   = c.read_key
        obj_store  = c.obj_store
        base_map   = self._commit_blob_map(c, lca_id)    if lca_id    else {}
        ours_map   = self._commit_blob_map(c, ours_id)   if ours_id   else {}
        theirs_map = self._commit_blob_map(c, theirs_id) if theirs_id else {}

        rows = []
        for path in conflict_paths:
            base_bid       = base_map.get(path)
            ours_bid       = ours_map.get(path)
            theirs_bid     = theirs_map.get(path)
            ours_changed   = ours_bid   != base_bid
            theirs_changed = theirs_bid != base_bid
            if ours_changed and theirs_changed:
                verdict = 'identical' if ours_bid == theirs_bid else 'genuine'
            elif ours_changed:
                verdict = 'one-sided-ours'
            elif theirs_changed:
                verdict = 'one-sided-theirs'
            else:
                verdict = 'no-change'
            ours_text,   ours_bin   = self._decode_blob(obj_store, read_key, ours_bid)
            theirs_text, theirs_bin = self._decode_blob(obj_store, read_key, theirs_bid)
            rows.append(dict(path           = path,
                             verdict        = verdict,
                             ours_changed   = ours_changed,
                             theirs_changed = theirs_changed,
                             base_present   = base_bid   is not None,
                             ours_present   = ours_bid   is not None,
                             theirs_present = theirs_bid is not None,
                             ours_text      = ours_text,
                             theirs_text    = theirs_text,
                             is_binary      = bool(ours_bin or theirs_bin)))
        return rows

    def _commit_blob_map(self, c: Vault__Components, commit_id: str) -> dict:
        """Return {path: blob_id} for a commit's tree (no blob decryption)."""
        vc         = Vault__Commit(crypto=self.crypto, pki=c.pki,
                                   object_store=c.obj_store, ref_manager=c.ref_manager)
        commit_obj = vc.load_commit(commit_id, c.read_key)
        flat       = Vault__Sub_Tree(crypto=self.crypto, obj_store=c.obj_store).flatten(
                         str(commit_obj.tree_id), c.read_key)
        return {path: entry.get('blob_id')
                for path, entry in flat.items() if entry.get('blob_id')}

    def _decode_blob(self, obj_store, read_key: bytes, blob_id: str):
        """Return (utf8_text_or_None, is_binary); (None, False) when blob absent."""
        if not blob_id or not obj_store.exists(blob_id):
            return None, False
        plaintext = self.crypto.decrypt(read_key, obj_store.load(blob_id))
        try:
            return plaintext.decode('utf-8'), False
        except UnicodeDecodeError:
            return None, True

    def ensure_commit_local(self, directory: str, commit_id: str) -> bool:
        """Read-only on-demand fetch (A3): download any objects for <commit_id>
        (and the ancestors needed to diff it) that are missing locally.

        Lets `history show`/`diff` inspect a commit whose objects were never
        cloned, WITHOUT forcing a `sgit pull` (which would merge). No ref writes,
        no merge, no working-copy changes — only content-addressed blobs/trees/
        commits are downloaded into bare/data. Returns False when no api is wired.
        """
        if self.api is None:
            return False
        from sgit_ai.core.actions.pull.Vault__Sync__Pull import Vault__Sync__Pull
        c      = self._init_components(directory)
        puller = Vault__Sync__Pull(crypto=self.crypto, api=self.api)
        puller._fetch_missing_objects(str(c.vault_id), commit_id, c.obj_store,
                                      c.read_key, c.sg_dir, include_blobs=True)
        return True

    def _read_head_files(self, c: Vault__Components) -> dict:
        """Return flat {path: bytes} for clone branch HEAD."""
        storage        = c.storage
        branch_manager = c.branch_manager
        ref_manager    = c.ref_manager
        read_key       = c.read_key

        # Need directory from sg_dir
        sg_dir    = c.sg_dir
        directory = os.path.dirname(sg_dir)

        local_config = self._read_local_config(directory, storage)
        branch_id    = str(local_config.my_branch_id)

        index_id = c.branch_index_file_id
        if not index_id:
            return {}
        branch_index = branch_manager.load_branch_index(directory, index_id, read_key)
        branch_meta  = branch_manager.get_branch_by_id(branch_index, branch_id)
        if not branch_meta:
            return {}

        ref_id    = str(branch_meta.head_ref_id)
        commit_id = ref_manager.read_ref(ref_id, read_key)
        if not commit_id:
            return {}

        return self._flatten_commit(c, commit_id)

    def _read_named_branch_files(self, c: Vault__Components, directory: str) -> dict:
        """Return flat {path: bytes} for named branch HEAD (e.g., 'current')."""
        branch_manager = c.branch_manager
        ref_manager    = c.ref_manager
        read_key       = c.read_key

        index_id = c.branch_index_file_id
        if not index_id:
            return {}
        branch_index = branch_manager.load_branch_index(directory, index_id, read_key)
        named_meta   = branch_manager.get_branch_by_name(branch_index, 'current')
        if not named_meta:
            return {}

        ref_id    = str(named_meta.head_ref_id)
        commit_id = ref_manager.read_ref(ref_id, read_key)
        if not commit_id:
            return {}

        return self._flatten_commit(c, commit_id)

    def _read_commit_files(self, c: Vault__Components, commit_id: str) -> dict:
        """Return flat {path: bytes} for a specific commit_id."""
        if not commit_id:
            return {}
        return self._flatten_commit(c, commit_id)

    def _scan_working_files(self, directory: str, c: Vault__Components) -> dict:
        """Walk working directory, return {path: bytes}."""
        ignore = Vault__Ignore().load_gitignore(directory).load_tracked_from_vault(directory, crypto=self.crypto)
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
                with open(full_path, 'rb') as f:
                    result[rel_path] = f.read()
        return result
