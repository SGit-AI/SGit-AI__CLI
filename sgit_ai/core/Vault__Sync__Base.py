"""Shared helpers for Vault__Sync sub-classes (brief 22 — E5).

All sub-classes (Vault__Sync__Commit, Vault__Sync__Pull, etc.) inherit
from this base, gaining access to _init_components, _read_local_config,
and other cross-cutting helpers without multiple Type_Safe inheritance.
"""
import json
import os
import stat
import time
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
from   sgit_ai.storage.Vault__Path_Guard             import Vault__Path_Guard, Vault__Unreadable_File_Error
from   sgit_ai.core.Vault__Components             import Vault__Components
from   sgit_ai.core.Vault__Errors                 import Vault__Clone_Mode_Corrupt_Error
from   sgit_ai.core.actions.gc.Vault__GC                     import Vault__GC
from   sgit_ai.core.Vault__Ignore                 import Vault__Ignore
from   sgit_ai.storage.Vault__Storage                import Vault__Storage, SG_VAULT_DIR


CONFLICT_SUFFIX    = '.conflict'                 # Vault__Merge.CONFLICT_SUFFIX (a test pins them equal)
SCAN_CACHE_FILE    = 'scan-cache.json'
SCAN_CACHE_VERSION = 2                      # .sg_vault/local/: {rel path: [mtime_ns, ctime_ns, size, ino, dev, hash]};
                                            # version 1 (0.24.1, dev only) kept [mtime, size, hash] and is discarded
SCAN_CACHE_RACE_NS = 2 * 10**9              # a file touched in the last 2 s is always re-read (git's racy rule)
WINDOWS            = os.name == 'nt'                  # st_ctime is the creation time there: the change time is read by handle


class Vault__Sync__Base(Type_Safe):
    """Shared helpers for all Vault__Sync sub-classes; inject crypto + api per call."""
    crypto     : Vault__Crypto = None
    api        : Vault__API    = None
    pack_vault : bool          = False        # set from the branch index on every _init_components: feature 'packs'

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
        return self.crypto.derive_keys_from_vault_key(vault_key)

    def _fetch_cache_object(self, manager, vault_id: str, kind, cache_id: str, read_key: bytes):
        """Fetch and decrypt a cache object from the server, or None.

        Needed because a clone only mirrors cache objects it created itself: a
        target discovered from the server listing (one another client declared)
        has no local copy. Without this, such objects are discovered and then
        silently skipped, so cross-client healing (D6) never happens.
        """
        try:
            file_id = manager.file_id(kind, cache_id)
            data    = self.api.batch_read(str(vault_id), [file_id])
            blob    = data.get(file_id)
            if blob:
                return manager.decrypt_object(blob, read_key, kind)
        except Exception:
            pass
        return None

    def _make_blob_fetcher(self, vault_id: str) -> callable:
        """blob_id -> ciphertext bytes from the server, or None. Feeds cache
        rebuilds on sparse clones, whose object store lacks unfetched blobs."""
        def fetch(blob_id: str):
            try:
                return self.api.read(str(vault_id), f'bare/data/{blob_id}') or None
            except Exception:
                return None
        return fetch

    def _require_readable_server_ref(self, vault_id: str, named_ref_id: str, read_key: bytes) -> None:
        """Raise Vault__Unreadable_Ref_Error when the server holds the named ref but it does
        not decrypt with this vault's key. Offline or absent is not an error here. Only pull
        reported it: status said "in sync", and push and fetch exited 0 (review eed8084 F3)."""
        from sgit_ai.core.Vault__Errors import Vault__Unreadable_Ref_Error
        try:
            data = self.api.read(str(vault_id), f'bare/refs/{named_ref_id}')
        except Exception:
            return
        if not data:
            return
        try:
            if json.loads(self.crypto.decrypt(read_key, data)).get('commit_id'):
                return
        except Exception:
            pass
        raise Vault__Unreadable_Ref_Error(self._unreadable_ref_message(named_ref_id))

    def _require_readable_tracked_ref(self, directory: str) -> None:
        """`_require_readable_server_ref` for the named branch this clone tracks."""
        c = self._init_components(directory)
        if not c.branch_index_file_id:
            return
        index = c.branch_manager.load_branch_index(directory, c.branch_index_file_id, c.read_key)
        cfg   = self._read_local_config(directory, c.storage)
        named = c.branch_manager.tracked_named_branch(index, str(cfg.my_branch_id))
        if named is not None and named.head_ref_id:
            self._require_readable_server_ref(c.vault_id, str(named.head_ref_id), c.read_key)

    def _unreadable_ref_message(self, named_ref_id: str) -> str:
        return (f'the server\'s ref for this branch (bare/refs/{named_ref_id}) does not decrypt with this '
                f'vault\'s key (damaged, or replaced by the host); nothing was changed')

    def _server_named_commit_id(self, vault_id: str, named_ref_id: str, read_key: bytes):
        """Commit id in the SERVER's copy of the named ref, or None if unreadable.

        The cache reconcile must not run rewrites/deletes computed from a local
        head that is behind the server (review 08/14 #2): a stale clone would
        delete or downgrade caches another client just published. None means
        "could not verify" — offline or transient — which callers treat per
        their own risk profile.
        """
        try:
            data = self.api.read(str(vault_id), f'bare/refs/{named_ref_id}')
            if not data:
                return None
            return json.loads(self.crypto.decrypt(read_key, data)).get('commit_id')
        except Exception:
            return None

    def _read_last_remote_head(self, directory: str, storage: Vault__Storage) -> str:
        try:
            cfg = self._read_local_config(directory, storage)
            return str(cfg.last_remote_head) if cfg.last_remote_head else ''
        except Exception:
            return ''

    def _write_last_remote_head(self, directory: str, storage: Vault__Storage, commit_id: str) -> None:
        """Record the remote named head this clone has accepted; every later remote
        head must descend from it or the pull is a rewind. Local-only, never pushed."""
        import json as _json
        try:
            path = storage.local_config_path(directory)
            with open(path) as f:
                raw = _json.load(f)
            if raw.get('last_remote_head') == commit_id:
                return
            raw['last_remote_head'] = commit_id or None
            storage.write_local_config(directory, raw)
        except Exception:
            pass

    # ── remote baselines: the last remote head this clone ACCEPTED, per named branch ──
    # Only a guarded pull or merge, an accepted rewind, or this clone's own successful
    # push moves a baseline. Observing the server (status, fetch, switch) never does:
    # a lease or rewind check against a baseline that status had refreshed passed
    # where it must fail (review B2), and one shared baseline that switch rebuilt from
    # an unguarded local ref let a rewind through a branch round trip (review B3).

    REMOTE_BASELINES_FILE = 'remote_heads.json'

    def _remote_baselines(self, directory: str, storage: Vault__Storage) -> dict:
        """{named ref id: commit id}. A clone from before per-branch baselines has the
        single `last_remote_head`: it belongs to the branch the clone tracks (and is
        cleared once the per-branch file exists, so it can never come back stale).
        An unreadable file refuses (review d3b8eef L1): read as empty, the next pull
        accepted any head, rewinds included."""
        import json as _json
        from sgit_ai.core.Vault__Errors import Vault__Ref_Rewind_Error
        path = os.path.join(storage.local_dir(directory), self.REMOTE_BASELINES_FILE)
        if os.path.isfile(path):
            try:
                with open(path) as f:
                    data = _json.load(f)
                if not isinstance(data, dict):
                    raise ValueError('not an object')
                return {str(k): str(v) for k, v in data.items() if k and v}
            except Exception:
                raise Vault__Ref_Rewind_Error(
                    f'this clone\'s record of the heads it accepted ({self.REMOTE_BASELINES_FILE}) is unreadable, '
                    f'so it cannot tell a rewind from a move forward; nothing was changed. If you trust the '
                    f'server\'s current history, run: sgit pull --accept-rewind')
        if self._remote_heads_file_recorded(directory, storage):
            raise Vault__Ref_Rewind_Error(
                f'this clone\'s record of the heads it accepted ({self.REMOTE_BASELINES_FILE}) is missing, '
                f'so it cannot tell a rewind from a move forward; nothing was changed. If you trust the '
                f'server\'s current history, run: sgit pull --accept-rewind')
        legacy = self._read_last_remote_head(directory, storage)
        if not legacy:
            return {}
        ref_id = self._tracked_named_ref_id(directory)
        return {ref_id: legacy} if ref_id else {}

    def _save_remote_baselines(self, directory: str, storage: Vault__Storage, baselines: dict) -> None:
        import json as _json
        from sgit_ai.crypto.Vault__Secret_File import Vault__Secret_File
        path = os.path.join(storage.local_dir(directory), self.REMOTE_BASELINES_FILE)
        Vault__Secret_File().write(path, _json.dumps(baselines, indent=2, sort_keys=True))   # unique temp, fsync, rename
        self._mark_remote_heads_file(directory, storage)                         # the per-branch file is now the record

    def _remote_heads_file_recorded(self, directory: str, storage: Vault__Storage) -> bool:
        import json as _json
        try:
            with open(storage.local_config_path(directory)) as f:
                return bool(_json.load(f).get('remote_heads_file'))
        except Exception:
            return False

    def _mark_remote_heads_file(self, directory: str, storage: Vault__Storage) -> None:
        """From now on a missing remote_heads.json is a loss (L1), and the legacy single
        baseline, no longer updated, is cleared so it can never come back stale."""
        import json as _json
        path = storage.local_config_path(directory)
        try:
            with open(path) as f:
                raw = _json.load(f)
        except Exception:
            return
        if raw.get('remote_heads_file') and not raw.get('last_remote_head'):
            return
        raw['remote_heads_file'] = True
        raw['last_remote_head']  = None
        storage.write_local_config(directory, raw)

    def _forget_remote_baselines(self, directory: str, storage: Vault__Storage) -> None:
        """The user destroyed the server copy (delete-on-remote): there is no accepted head
        left to compare with, so the record goes, and its marker with it, so that a missing
        file is not read as a loss. The next push is then a genuine first push (TM-F34)."""
        import json as _json
        path = os.path.join(storage.local_dir(directory), self.REMOTE_BASELINES_FILE)
        if os.path.isfile(path):
            os.remove(path)
        cfg_path = storage.local_config_path(directory)
        try:
            with open(cfg_path) as f:
                raw = _json.load(f)
        except Exception:
            return
        if raw.get('remote_heads_file') or raw.get('last_remote_head'):
            raw['remote_heads_file'] = False
            raw['last_remote_head']  = None
            storage.write_local_config(directory, raw)

    def _read_remote_baseline(self, directory: str, storage: Vault__Storage, ref_id: str) -> str:
        return self._remote_baselines(directory, storage).get(str(ref_id or ''), '')

    def _accepted_head(self, directory: str, storage: Vault__Storage, accept_rewind: bool, ref_id: str) -> str:
        """The head this clone last accepted for a named branch ('' if never). A record that
        is unreadable, or missing once it existed, refuses (review d3b8eef L1) unless the
        caller is accepting a rewind deliberately."""
        from sgit_ai.core.Vault__Errors import Vault__Ref_Rewind_Error
        try:
            return self._read_remote_baseline(directory, storage, ref_id)
        except Vault__Ref_Rewind_Error:
            if not accept_rewind:
                raise
            return ''

    def _write_remote_baseline(self, directory: str, storage: Vault__Storage, ref_id: str, commit_id: str) -> None:
        from sgit_ai.core.Vault__Errors import Vault__Ref_Rewind_Error
        if not ref_id:
            return
        try:
            baselines = self._remote_baselines(directory, storage)
        except Vault__Ref_Rewind_Error:
            baselines = {}                                       # reached only after an accepted head: start afresh
        if baselines.get(str(ref_id)) == (commit_id or ''):
            if os.path.isfile(os.path.join(storage.local_dir(directory), self.REMOTE_BASELINES_FILE)):
                return
        if commit_id:
            baselines[str(ref_id)] = str(commit_id)
        else:
            baselines.pop(str(ref_id), None)
        self._save_remote_baselines(directory, storage, baselines)

    def _materialize_remote_baselines(self, directory: str, storage: Vault__Storage) -> None:
        """Write the per-branch file now (migrating the legacy single baseline to the
        branch it belongs to) — before anything changes which branch is tracked."""
        path = os.path.join(storage.local_dir(directory), self.REMOTE_BASELINES_FILE)
        if not os.path.isfile(path):
            self._save_remote_baselines(directory, storage, self._remote_baselines(directory, storage))

    def _tracked_named_ref_id(self, directory: str) -> str:
        try:
            c      = self._init_components(directory)
            config = self._read_local_config(directory, c.storage)
            index  = c.branch_manager.load_branch_index(directory, c.branch_index_file_id, c.read_key)
            meta   = c.branch_manager.tracked_named_branch(index, str(config.my_branch_id or ''))
            return str(meta.head_ref_id) if meta and meta.head_ref_id else ''
        except Exception:
            return ''

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
          - crypto.derive_keys_from_vault_key()  (full / headless clones)
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

    def _apply_vault_format(self, directory: str, index_id: str, read_key: bytes,
                            branch_manager, obj_store) -> None:
        """Read the gate from the local branch index: refuse a vault this client is
        too old for (Vault__Client_Too_Old_Error) and set the object-id width new
        objects are written at. A clone with no index yet stays at format 1."""
        from sgit_ai.storage.Vault__Format import Vault__Format, Vault__Client_Too_Old_Error
        if not index_id:
            return
        try:
            index = branch_manager.load_branch_index(directory, index_id, read_key)   # checks the gate
        except Vault__Client_Too_Old_Error:
            raise
        except Exception:
            return
        obj_store.id_hex_len = Vault__Format().id_hex_len(index)
        from sgit_ai.storage.Vault__Format import FEATURE_BLOB_DEFLATE, FEATURE_PACKS
        self.crypto.deflate_blobs = Vault__Format().has_feature(index, FEATURE_BLOB_DEFLATE)   # pack vaults: deflate before encrypt
        self.pack_vault           = Vault__Format().has_feature(index, FEATURE_PACKS)

    def _is_pack_vault(self, c) -> bool:
        """The flag set by _init_components, or (on an instance that never ran it, e.g.
        a status helper built inside a pull step) the branch index of the components."""
        if self.pack_vault:
            return True
        from sgit_ai.storage.Vault__Format import Vault__Format, FEATURE_PACKS
        try:
            directory = os.path.dirname(os.path.abspath(c.sg_dir))
            index     = c.branch_manager.load_branch_index(directory, c.branch_index_file_id, c.read_key)
            return Vault__Format().has_feature(index, FEATURE_PACKS)
        except Exception:
            return False

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
        self._apply_vault_format(directory, keys['branch_index_file_id'], keys['read_key_bytes'],
                                 branch_manager, obj_store)
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

    def _stat_key(self, st, full_path: str = None):
        """(mtime_ns, change time ns, size, inode, device) of a stat — git's index key —
        or None when it cannot be formed, which means "do not cache this file".
        `st_ctime` is the inode change time on POSIX; on Windows it is the creation
        time (until Python 3.14), which a restored mtime does not move, so there the
        NTFS ChangeTime is read through the file handle (QA round 2, note 2); when
        that read fails the file is hashed every time rather than trusted."""
        if WINDOWS:
            change = self._windows_change_time_ns(full_path) if full_path else None
            if change is None:
                return None
            return (st.st_mtime_ns, change, st.st_size, st.st_ino, st.st_dev)
        return (st.st_mtime_ns, st.st_ctime_ns, st.st_size, st.st_ino, st.st_dev)

    def _windows_change_time_ns(self, full_path: str):
        """NTFS ChangeTime of the file at full_path (not followed if a link), in FILETIME
        ticks ×100 (ns since 1601; equality is all the cache compares), or None."""
        try:
            import ctypes
            from ctypes import wintypes
            class FILE_BASIC_INFO(ctypes.Structure):
                _fields_ = [('CreationTime', ctypes.c_longlong), ('LastAccessTime', ctypes.c_longlong),
                            ('LastWriteTime', ctypes.c_longlong), ('ChangeTime', ctypes.c_longlong),
                            ('FileAttributes', wintypes.DWORD)]
            k32 = ctypes.windll.kernel32
            k32.CreateFileW.restype = wintypes.HANDLE
            share  = 0x1 | 0x2 | 0x4                                     # read, write, delete: never block anyone
            flags  = 0x02000000 | 0x00200000                             # BACKUP_SEMANTICS (folders), OPEN_REPARSE_POINT
            handle = k32.CreateFileW(full_path, 0, share, None, 3, flags, None)   # 0 access: metadata only; OPEN_EXISTING
            if handle in (None, wintypes.HANDLE(-1).value, -1):
                return None
            try:
                info = FILE_BASIC_INFO()
                ok   = k32.GetFileInformationByHandleEx(handle, 0, ctypes.byref(info), ctypes.sizeof(info))   # FileBasicInfo
                return int(info.ChangeTime) * 100 if ok else None
            finally:
                k32.CloseHandle(handle)
        except Exception:
            return None

    def _scan_cache_path(self, directory: str) -> str:
        return os.path.join(Vault__Storage().local_dir(directory), SCAN_CACHE_FILE)

    def _scan_cache_load(self, directory: str) -> dict:
        """{path: [mtime_ns, ctime_ns, size, ino, dev, hash]} — git's index key (ctime
        catches a restored mtime; no user-space call sets ctime back; the inode and
        device catch a same-size file moved over another). An older format, or
        anything malformed, is discarded whole (QA review of 26 Oct, finding 1)."""
        try:
            with open(self._scan_cache_path(directory)) as f:
                data = json.load(f)
            if not isinstance(data, dict) or data.get('version') != SCAN_CACHE_VERSION:
                return {}
            files = data.get('files')
            if not isinstance(files, dict):
                return {}
            return {k: v for k, v in files.items()
                    if isinstance(v, list) and len(v) == 6
                    and all(isinstance(x, int) and not isinstance(x, bool) for x in v[:5]) and isinstance(v[5], str)}
        except Exception:
            return {}

    def _scan_cache_save(self, directory: str, files: dict) -> None:
        """Written whole after every scan (a cache: a failure to write is ignored)."""
        try:
            path = self._scan_cache_path(directory)
            os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
            tmp = path + '.tmp'
            fd  = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, 'w') as f:
                f.write(json.dumps(dict(version=SCAN_CACHE_VERSION, files=files), separators=(',', ':')))
            os.replace(tmp, path)
        except OSError:
            pass

    def _scan_local_directory(self, directory: str, warn_links: bool = False, linked_out: list = None,
                              unreadable_out: list = None, conflict_out: list = None, verify: set = None) -> dict:
        """{rel path: {size, content_hash}} of the working copy's files. Symlinks are
        never followed (sgit stores no links: a followed link was committed as a copy of
        its target, secrets included). A link at a path the head tracks, or a linked
        folder holding tracked paths, keeps the committed entries: it reads as unchanged,
        never as deleted, so a commit cannot delete those files for everyone. A FIFO,
        socket or device at a tracked path is kept the same way.

        A file that cannot be opened (permission denied, held open by another program,
        EIO) is never "deleted" either (review eed8084 B2): with `unreadable_out` (status)
        it is listed there and keeps its committed entry; without it the scan raises
        Vault__Unreadable_File_Error naming the file, so commit, pull and switch refuse.

        `verify`: paths read and hashed whatever the scan cache says (the pull's dirty-tree
        guard passes the files the incoming merge would change: a handful, and the one
        place a missed edit destroys data)."""
        ignore = Vault__Ignore().load_gitignore(directory).load_tracked_from_vault(directory, crypto=self.crypto)
        guard  = Vault__Path_Guard()
        result = {}
        links  = []
        kept_as_is = []                                           # FIFOs/devices, and unreadable files (status only)
        scan_cache = self._scan_cache_load(directory)             # rel path -> [mtime, ctime, size, ino, dev, hash]
        fresh      = {}
        scan_start = time.time_ns()                               # an entry is trusted, and recorded, only for a
        racy_limit = scan_start - SCAN_CACHE_RACE_NS              # file last modified before this moment less 2 s
        verify     = verify or set()

        def unlistable(error):                                    # a folder that cannot be listed: its files are not
            rel = os.path.relpath(error.filename or directory, directory).replace(os.sep, '/')   # "deleted" (3e099ee N2)
            if unreadable_out is None:
                raise Vault__Unreadable_File_Error(rel + '/', error.strerror or type(error).__name__)
            unreadable_out.append(rel + '/')
            kept_as_is.append(rel)

        base_prefix = os.path.join(directory, '')                 # os.walk roots start with it: a slice
        for root, dirs, files in os.walk(directory, onerror=unlistable):   # replaces a relpath per folder
            if root == directory:
                rel_root = ''
            elif root.startswith(base_prefix):
                rel_root = root[len(base_prefix):].replace(os.sep, '/')
            else:
                rel_root = os.path.relpath(root, directory).replace(os.sep, '/')
            dirs[:] = [d for d in dirs
                       if not ignore.should_ignore_dir(f'{rel_root}/{d}' if rel_root else d)]
            for d in [d for d in dirs if guard.is_link(os.path.join(root, d))]:
                links.append(f'{rel_root}/{d}' if rel_root else d)
                dirs.remove(d)                                     # os.walk would not descend; be explicit
            for filename in files:
                rel_path = f'{rel_root}/{filename}' if rel_root else filename
                if conflict_out is not None and filename.endswith(CONFLICT_SUFFIX):   # before the ignore rules,
                    conflict_out.append(rel_path)                                     # as Vault__Merge.has_conflicts
                if ignore.should_ignore_file(rel_path):
                    continue
                full_path = os.path.join(root, filename)
                try:
                    st = os.lstat(full_path)                        # one lstat per file: the link check
                except OSError:                                     # and the cache check share it
                    st = None
                if guard.is_link(full_path, st):
                    links.append(rel_path)
                    continue
                # git's index rule: a regular file whose mtime, ctime, size, inode and device are
                # what the last scan recorded, modified more than two seconds before this scan
                # began, has the hash the last scan computed; nothing else is read. The newsroom's
                # 2.7 GB working tree was read and hashed on every status (report of 26 Oct).
                known = scan_cache.get(rel_path)
                if known is not None and rel_path not in verify:
                    key = self._stat_key(st, full_path) if st is not None else None
                    if (key is not None and stat.S_ISREG(st.st_mode)
                            and key == tuple(known[:5]) and known[0] < racy_limit):
                        result[rel_path] = dict(size=known[2], content_hash=known[5])
                        fresh[rel_path]  = known
                        continue
                try:
                    content = guard.read_regular(full_path, rel_path)   # O_NOFOLLOW, never a FIFO or device (L4)
                except Vault__Unreadable_File_Error:
                    if unreadable_out is None:
                        raise                                       # never recorded as deleted (B2)
                    unreadable_out.append(rel_path)
                    kept_as_is.append(rel_path)
                    continue
                if content is None:
                    if os.path.lexists(full_path):                  # not gone: a FIFO, socket or device
                        kept_as_is.append(rel_path)
                    continue
                content_hash     = self.crypto.content_hash(content)
                result[rel_path] = dict(size=len(content), content_hash=content_hash)
                # Recorded under the stat taken BEFORE the read, and only if the stat after the
                # read is the same (a save that lands between read and stat would pair the old
                # hash with the new size and mtime) and the file was not modified within the
                # racy window (two same-size writes in one timestamp tick of a coarse
                # filesystem would keep the first hash for good). Otherwise the hash is used
                # this time and not cached (QA review of 26 Oct, finding 2).
                try:
                    after = os.lstat(full_path)
                except OSError:
                    after = None
                key = self._stat_key(st, full_path) if st is not None else None
                if (key is not None and after is not None and stat.S_ISREG(st.st_mode)
                        and key == self._stat_key(after, full_path) and len(content) == st.st_size):
                    if st.st_mtime_ns < racy_limit:
                        fresh[rel_path] = [*key, content_hash]
                    elif known is not None and tuple(known[:5]) == key and known[5] == content_hash:
                        fresh[rel_path] = known                     # racy, but a seed (clone, pull) this read confirms
        self._scan_cache_save(directory, fresh)
        if kept_as_is:
            self._keep_tracked_under_links(directory, kept_as_is, result)    # their committed entries stand
        if links:
            kept = self._keep_tracked_under_links(directory, links, result)
            if linked_out is not None:                     # tracked paths a link hides: status and pull name
                linked_out.extend(kept)                    # them, never "clean" (review d3b8eef L3)
            if warn_links:
                import sys
                for rel in links:
                    print(f'  warning: skipped symlink {rel} (sgit does not store links; '
                          f'a tracked file there keeps its committed version)', file=sys.stderr)
        return result

    def _keep_tracked_under_links(self, directory: str, links: list, result: dict) -> list:
        from sgit_ai.core.Vault__Head_Paths import Vault__Head_Paths
        head = Vault__Head_Paths(crypto=self.crypto).flat(directory)
        kept = []
        for path, entry in head.items():
            if path in result or not isinstance(entry, dict):
                continue
            if any(path == link or path.startswith(link + '/') for link in links):
                result[path] = dict(size=entry.get('size', 0), content_hash=entry.get('content_hash', ''))
                kept.append(path)
        return sorted(kept)

    def _linked_tracked_paths(self, directory: str) -> list:
        """Tracked paths the working copy holds as (or under) a symlink: sgit neither
        follows nor replaces them, so they no longer follow the vault. A walk that only
        looks for links (no file is opened or hashed): pull used to re-hash the whole
        working copy for this (review 0a0707d F6)."""
        from sgit_ai.core.Vault__Head_Paths import Vault__Head_Paths
        guard = Vault__Path_Guard()
        links = []
        try:
            for root, dirs, files in os.walk(directory):
                rel_root = os.path.relpath(root, directory).replace(os.sep, '/')
                rel_root = '' if rel_root == '.' else rel_root
                if rel_root == '' and '.sg_vault' in dirs:
                    dirs.remove('.sg_vault')
                for name in list(dirs) + files:
                    if guard.is_link(os.path.join(root, name)):
                        links.append(f'{rel_root}/{name}' if rel_root else name)
                dirs[:] = [d for d in dirs if not guard.is_link(os.path.join(root, d))]
            if not links:
                return []
            tracked = Vault__Head_Paths(crypto=self.crypto).paths(directory)
        except Exception:
            return []
        return sorted(p for p in tracked if any(p == link or p.startswith(link + '/') for link in links))
    def _checkout_flat_map(self, directory: str, flat_map: dict,
                           obj_store: Vault__Object_Store, read_key: bytes, failed: dict = None) -> dict:
        """Write all files from a flat {path: dict} map to the working directory, and
        record each one in the scan cache under the hash of the bytes written: the
        next status, commit or pull stats them instead of reading them back (the
        newsroom's first status on a fresh 4.2 GB clone read every file: 18 minutes
        on a cloud session's disk, 26 Oct field report).

        Returns {path: content hash} of the files actually written. A file that could
        not be written (a folder or a file in the way, a full disk, no permission, an
        object that does not decrypt) is not in it, and with `failed` its reason is
        recorded there: a caller that records or relies on what reached the disk must
        use this, never the map it asked for (second review of 26 Oct, R2)."""
        guard   = Vault__Path_Guard()
        written = {}
        for path, entry in sorted(flat_map.items()):
            blob_id = entry.get('blob_id')
            if not blob_id:
                continue
            if guard.is_protected(path):               # never write into .git/ or vault internals (A2)
                import sys
                print(f'  warning: refusing to write structural path from vault data: {path}',
                      file=sys.stderr)
                continue
            try:
                # path comes from decrypted vault data; contain it before writing.
                full_path  = guard.safe_join(directory, path)
                ciphertext = obj_store.load(blob_id)
                plaintext  = self.crypto.decrypt(read_key, ciphertext)
                os.makedirs(os.path.dirname(full_path), exist_ok=True)
                with open(full_path, 'wb') as f:
                    f.write(plaintext)
                written[path] = self.crypto.content_hash(plaintext)   # the real hash, never the entry's claim
            except Exception as error:
                from sgit_ai.storage.Vault__Path_Guard import Vault__Unsafe_Path_Error
                if failed is not None and not isinstance(error, Vault__Unsafe_Path_Error):
                    failed[path] = (getattr(error, 'strerror', None) or type(error).__name__)
                                                       # a path the guard refuses (a planted name, a tracked file under
                                                       # a link) is skipped on purpose and named elsewhere, as before
        self._scan_cache_seed(directory, written)
        return written

    def _scan_cache_seed(self, directory: str, hashes: dict) -> None:
        """Record {rel path: content hash} of files sgit itself just wrote, under the stat
        taken now. A cache: a path that cannot be stat'ed, or is not a regular file, is
        skipped; a failure to write the cache is ignored. The racy rule still applies when
        the entry is read (a scan within two seconds of the write reads the file)."""
        if not hashes:
            return
        try:
            files = self._scan_cache_load(directory)
            for rel_path, content_hash in hashes.items():
                full_path = os.path.join(directory, rel_path)
                try:
                    st = os.lstat(full_path)
                except OSError:
                    continue
                key = self._stat_key(st, full_path) if stat.S_ISREG(st.st_mode) else None
                if key is not None:
                    files[rel_path] = [*key, content_hash]
            self._scan_cache_save(directory, files)
        except Exception:
            return

    def _remove_deleted_flat(self, directory: str, old_map: dict, new_map: dict) -> None:
        """Remove files present in old_map but not in new_map, then prune empty dirs."""
        guard = Vault__Path_Guard()
        for path in set(old_map.keys()) - set(new_map.keys()):
            if not guard.is_writable(directory, path): # never delete outside the working copy, nor .git / .sg_vault
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
