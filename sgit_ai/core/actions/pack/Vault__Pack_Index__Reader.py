"""Vault__Pack_Index__Reader — find, verify and use the index packs (cli.sgit.ai dev pack
"pack indexes" 03, Phase 1: the reader).

Finding (03 §1): `sync_down` takes the index pack paired with every data pack it takes
(same folder under indexes/, same epoch and commit id) in the same batch read, and
keeps it, still encrypted, under .sg_vault/local/index/packs/<folder>/. Nothing is
listed under indexes/ unless the branch index carries the advisory 'pack-indexes'
feature, and nothing from indexes/archive/ is ever fetched.

Verifying (03 §2), in order, before anything uses an index: the header (magic, format,
decrypts under the read key, known schema, the kind and commit asked for); the
signature, with the key the header names, under the vault's commit policy (with
'signatures-required' a missing, unloadable or bad signature drops the index; without
it an unsigned index is accepted, a bad signature still drops it); the anchor (parents,
tree id and timestamp equal the commit object's, which must be local); each member's
sha256 on read. A flat map assembled from an index is anchored to the head's root tree
(one tree read) and shaped like the flat cache before the cache learns it.

Using (03 §5): a pull's fetch plan (the objects the new commits' `changes` and
`folder:*` members name, which must all be local, else the walk runs as before); the
new head's flat map (the base head's cached map plus the folder members of each
commit on the first-parent chain, no tree read); a fresh clone's first flat map (the
snapshot index's `flat`); `history log` counts and stat from `changes`.

An index is a plan, never a proof (TM-R42): a failure anywhere means the reader walks
instead, for that pack only, and says so once. Nothing an index states is written
without the named object verifying by content address.
"""
import os
from sgit_ai.core.actions.pack.Vault__Pack_Index  import (Vault__Pack_Index, PACK_INDEXES, INDEX_SCHEMA, FOLDER_SCHEMA,
                                                          CHANGES_SCHEMA, INDEXES_ENV)
from sgit_ai.core.actions.pack.Vault__Packs       import PACK_COMMITS, PACK_SNAPSHOTS, PACK_ARCHIVE
from sgit_ai.storage.Vault__Object_Store         import Vault__Object_Store
from sgit_ai.storage.Vault__Storage              import SG_VAULT_DIR
from sgit_ai.storage.Vault__Sub_Tree             import Vault__Sub_Tree, FLAT_CACHE_VERSION, OBJECT_ID_RE

READER_ENV          = 'SGIT_PACK_INDEXES_READ'                  # '0' turns the reader off (the writer keeps writing)
DELTA_CHAIN_MAX     = 2000                                      # commit indexes assembled onto one base, at most
LOCAL_PACK_FOLDERS  = ('commits', 'snapshots', 'archive')


class Vault__Pack_Index__Reader(Vault__Pack_Index):
    sig_required   : bool   = True                              # fail closed until the policy is read
    key_manager    : object = None                              # Vault__Key_Manager of the clone
    notes          : list                                       # what was dropped and why, once each
    dropped        : list                                       # index files dropped for the rest of this command
    last_seed      : str    = ''                                # 'snapshot' | 'deltas' | '' : how the last flat map came

    # ------------------------------------------------------------------ switches and policy
    def reader_enabled(self) -> bool:
        return (os.environ.get(READER_ENV, '1') not in ('0', 'false', 'no', 'off')
                and os.environ.get(INDEXES_ENV, '1') not in ('0', 'false', 'no', 'off'))

    def setup_for(self, directory: str, read_key: bytes = None, c=None, index=None, key_manager=None):
        """Bind the signature policy and the key store of one clone. `index` is the branch
        index when the caller holds it (a clone in progress has no local config yet);
        otherwise it is loaded from the clone. A policy that cannot be read is 'required'."""
        from sgit_ai.storage.Vault__Format import Vault__Format, FEATURE_SIG_REQUIRED
        if key_manager is not None:
            self.key_manager = key_manager
        elif c is not None:
            self.key_manager = c.key_manager
        else:
            from sgit_ai.crypto.PKI__Crypto          import PKI__Crypto
            from sgit_ai.crypto.Vault__Key_Manager   import Vault__Key_Manager
            self.key_manager = Vault__Key_Manager(vault_path=os.path.join(directory, SG_VAULT_DIR), crypto=self.crypto, pki=PKI__Crypto())
        if index is None:
            try:
                if c is not None:
                    index = c.branch_manager.load_branch_index(directory, c.branch_index_file_id, c.read_key)
                else:
                    keys  = self._derive_keys_for_directory(directory)
                    index = self._load_index(directory, keys['branch_index_file_id'], keys['read_key_bytes'])
            except Exception:
                index = None
        self.sig_required = True if index is None else Vault__Format().has_feature(index, FEATURE_SIG_REQUIRED)
        return self

    def usable_in(self, directory: str, index=None) -> bool:
        """Whether this clone reads indexes: the reader is on and the branch index carries
        the advisory feature (an index passed in, or the clone's own)."""
        from sgit_ai.storage.Vault__Format import Vault__Format, FEATURE_PACK_INDEXES
        if not self.reader_enabled():
            return False
        if index is not None:
            return Vault__Format().has_feature(index, FEATURE_PACK_INDEXES)
        return FEATURE_PACK_INDEXES in self.features_of_directory(directory)

    def note(self, _p, what: str, why: str) -> None:
        key = (what, why)
        if key in self.notes:
            return
        self.notes.append(key)
        (_p or (lambda *a, **k: None))('warning', what, why)

    # ------------------------------------------------------------------ finding: from the host, with the data packs
    def index_entries_for(self, vault_id: str, data_folder: str, entries: list, index_listing: list = None) -> list:
        """The index entries paired with these data entries (same epoch and commit id in the
        matching indexes/ folder). An index with no data pack is never taken."""
        listing = self.list_index_packs(vault_id, self.index_folder_of(data_folder)) if index_listing is None else index_listing
        by_key  = {(e['commit_id'], e['epoch']): e for e in listing}
        out     = []
        for entry in entries:
            hit = by_key.get((entry['commit_id'], entry['epoch']))
            if hit is not None:
                out.append(hit)
        return out

    def keep_fetched(self, directory: str, data_folder: str, index_entries: list, got: dict) -> list:
        """Write the index packs a batch read brought, as downloaded (still encrypted), under
        local/index/packs/<folder>/; returns the names kept. A byte count that does not
        match the name is not kept (the data pack's rule)."""
        kept = []
        index_folder = self.index_folder_of(data_folder)
        for e in index_entries:
            data = got.get(e['file_id'])
            if data is None or len(data) != e['size']:
                continue
            path = self.local_index_pack_path(directory, index_folder, e['name'])
            try:
                os.makedirs(os.path.dirname(path), exist_ok=True)
                tmp = path + '.tmp'
                with open(tmp, 'wb') as f:
                    f.write(data)
                os.replace(tmp, path)
                kept.append(e['name'])
            except OSError:
                pass
        return kept

    # ------------------------------------------------------------------ finding: on this clone
    def local_index_path(self, directory: str, commit_id: str, kind: str = None) -> str:
        """The newest local index pack for a commit: a snapshot index (snapshots/, then
        archive/) when kind is 'snapshot', a commit index (commits/, then archive/) when
        'commit', either when None. '' when there is none."""
        folders = {'snapshot': ('snapshots', 'archive'), 'commit': ('commits', 'archive')}.get(kind, LOCAL_PACK_FOLDERS)
        base    = os.path.join(self.local_index_dir(directory), 'packs')
        for sub in folders:
            folder = os.path.join(base, sub)
            try:
                names = sorted(os.listdir(folder), reverse=True)
            except OSError:
                continue
            for name in names:
                info = self.parse_name(name)
                if info and info['commit_id'] == commit_id:
                    path = os.path.join(folder, name)
                    if path not in self.dropped:
                        return path
        return ''

    # ------------------------------------------------------------------ verifying
    def open_index(self, directory: str, commit_id: str, read_key: bytes, kind: str = None, _p=None):
        """(bytes, header) of a verified local index pack for the commit, or None: header,
        signature policy, anchor to the local commit object. A failure drops that file for
        the rest of the command and is noted once."""
        path = self.local_index_path(directory, commit_id, kind)
        if not path:
            return None
        try:
            with open(path, 'rb') as f:
                data = f.read()
            header = self.read_header(data, read_key)
            why    = self._header_fault(directory, header, commit_id, read_key, kind)
        except Exception as error:
            why = f'{type(error).__name__}: {str(error)[:80]}'
        if why:
            self.dropped.append(path)
            self.note(_p, 'Index pack dropped (walking the trees instead)', f'{os.path.basename(path)}: {why}')
            return None
        return data, header

    def _header_fault(self, directory: str, header: dict, commit_id: str, read_key: bytes, kind: str) -> str:
        if header.get('commit_id') != commit_id:
            return 'names another commit'
        if kind and header.get('kind') != kind:
            return f'not a {kind} index'
        if header.get('kind') not in ('commit', 'snapshot'):
            return 'unknown kind'
        fault = self.signature_fault(header, read_key)
        if fault:
            return fault
        sg_dir = os.path.join(directory, SG_VAULT_DIR)
        if not Vault__Object_Store(vault_path=sg_dir, crypto=self.crypto).exists(commit_id):
            return 'its commit is not local'
        fields = self.commit_fields(sg_dir, commit_id, read_key)
        for f in ('parents', 'tree_id', 'timestamp_ms'):
            if header.get(f) != fields[f]:
                return f'{f} differs from the commit object'
        return ''

    def signature_fault(self, header: dict, read_key: bytes) -> str:
        """'' when the header passes the vault's policy. A signature that is present must
        verify with the key it names; one that is missing, or names a key this clone
        cannot load, counts as unsigned: dropped under 'signatures-required', accepted
        otherwise (the index then has the standing of an unsigned commit: TM-R42)."""
        sig    = header.get('signature')
        key_id = str(header.get('author_key_id') or '')
        public = None
        if sig and key_id and self.key_manager is not None:
            try:
                public = self.key_manager.load_public_key(key_id, read_key)
            except Exception:
                public = None
        if public is not None:
            return '' if self.verify_header_signature(header, public) else 'signature does not verify'
        return 'unsigned, and this vault requires signatures' if self.sig_required else ''

    def member(self, data: bytes, header: dict, name: str, read_key: bytes):
        """A member's JSON (sha-checked) or None when absent; a bad member raises."""
        return self.read_member(data, header, name, read_key)

    # ------------------------------------------------------------------ using: changes and folders
    def changes_of_commit(self, directory: str, commit_id: str, read_key: bytes, _p=None) -> dict:
        """{'changes': [...], 'folders': {path: tree id}, 'tree_id', 'parents', 'generation'} of
        a commit from its commit index, or None (no usable index: the caller walks)."""
        opened = self.open_index(directory, commit_id, read_key, kind='commit', _p=_p)
        if opened is None:
            return None
        data, header = opened
        try:
            doc = self.member(data, header, 'changes', read_key)
            if not isinstance(doc, dict) or doc.get('schema') != CHANGES_SCHEMA or not isinstance(doc.get('changes'), list):
                raise ValueError('changes member of another schema')
            changes = []
            for r in doc['changes']:
                if not isinstance(r, dict) or r.get('op') not in ('A', 'M', 'D') or not isinstance(r.get('path'), str):
                    raise ValueError('a change record is malformed')
                for f in ('old_blob', 'new_blob'):
                    if r.get(f) and not OBJECT_ID_RE.fullmatch(str(r[f])):
                        raise ValueError('a change names something that is not an object id')
                changes.append(r)
            folders = {}
            for name, row in self.member_table(header).items():
                if name.startswith('folder:'):
                    folders[name[len('folder:'):]] = None                   # read on demand (folder_members)
            return dict(changes=changes, folders=folders, tree_id=str(header.get('tree_id') or ''),
                        parents=list(header.get('parents') or []), generation=int(header.get('generation') or 0),
                        timestamp_ms=int(header.get('timestamp_ms') or 0))
        except Exception as error:
            self._drop(directory, commit_id, 'commit', _p, f'changes: {str(error)[:80]}')
            return None

    def folder_members(self, directory: str, commit_id: str, read_key: bytes, kind: str = None, _p=None):
        """{folder path: folder member} of an index (every folder:* member, sha-checked and
        shape-checked), with the header, or None."""
        opened = self.open_index(directory, commit_id, read_key, kind=kind, _p=_p)
        if opened is None:
            return None
        data, header = opened
        try:
            out = {}
            for name in self.member_table(header):
                if not name.startswith('folder:'):
                    continue
                path   = name[len('folder:'):]
                member = self.member(data, header, name, read_key)
                if not self._folder_ok(path, member):
                    raise ValueError(f'folder member {path!r} is malformed')
                out[path] = member
            return out, header
        except Exception as error:
            self._drop(directory, commit_id, kind, _p, str(error)[:80])
            return None

    def _folder_ok(self, path: str, m) -> bool:
        if not isinstance(m, dict) or m.get('schema') != FOLDER_SCHEMA or m.get('path') != path:
            return False
        if not OBJECT_ID_RE.fullmatch(str(m.get('tree_id') or '')):
            return False
        files, dirs = m.get('files'), m.get('dirs')
        if not isinstance(files, dict) or not isinstance(dirs, dict):
            return False
        for name, e in files.items():
            if not isinstance(name, str) or not name or '/' in name or not self._entry_ok(e):
                return False
        for name, tid in dirs.items():
            if not isinstance(name, str) or not name or '/' in name or not OBJECT_ID_RE.fullmatch(str(tid)):
                return False
        return True

    def _entry_ok(self, e) -> bool:
        return (isinstance(e, dict) and OBJECT_ID_RE.fullmatch(str(e.get('blob_id') or '')) is not None
                and isinstance(e.get('size'), int) and not isinstance(e.get('size'), bool)
                and isinstance(e.get('content_hash'), str) and isinstance(e.get('content_type'), str)
                and isinstance(e.get('large'), bool))

    def _drop(self, directory: str, commit_id: str, kind: str, _p, why: str) -> None:
        path = self.local_index_path(directory, commit_id, kind)
        if path and path not in self.dropped:
            self.dropped.append(path)
        self.note(_p, 'Index pack dropped (walking the trees instead)', f'{os.path.basename(path) or commit_id}: {why}')

    # ------------------------------------------------------------------ using: the pull's fetch plan
    def fetch_plan(self, directory: str, commit_ids: list, read_key: bytes, _p=None) -> dict:
        """What the new commits introduce, from their commit indexes: every blob an A or M
        names and every folder tree id a folder member names, plus the root trees. None
        when any commit has no usable index (the walk then runs as before)."""
        blobs, trees, by_commit = set(), set(), {}
        for cid in commit_ids:
            info = self.changes_of_commit(directory, cid, read_key, _p)
            if info is None:
                return None
            folders = self.folder_members(directory, cid, read_key, kind='commit', _p=_p)
            if folders is None:
                return None
            for r in info['changes']:
                if r.get('new_blob'):
                    blobs.add(str(r['new_blob']))
            for m in folders[0].values():
                trees.add(str(m['tree_id']))
            if info['tree_id']:
                trees.add(info['tree_id'])
            by_commit[cid] = info
        return dict(blobs=blobs, trees=trees, by_commit=by_commit)

    # ------------------------------------------------------------------ using: the head's flat map
    def seed_head_flat(self, directory: str, head_commit_id: str, read_key: bytes, sub_tree: Vault__Sub_Tree, _p=None):
        """(flat, dirs) of the head, assembled from the indexes without a tree walk, and
        remembered by the flat cache; None when the indexes cannot give it. The base is the
        first of, walking first parents from the head: a head whose map is cached, a commit
        with a snapshot index, or the root (an empty base); each commit above the base is
        applied from its commit index's folder members, touching only the folders it
        changed. The result is anchored to the head's root tree before the cache learns it."""
        self.last_seed = ''
        sg_dir = os.path.join(directory, SG_VAULT_DIR)
        store  = Vault__Object_Store(vault_path=sg_dir, crypto=self.crypto)
        chain, base, cid = [], None, head_commit_id
        while True:
            if not cid or not store.exists(cid):
                return None                                                  # a shallow boundary: no base
            fields = self._commit_fields_or_none(sg_dir, cid, read_key)
            if fields is None or not fields['tree_id']:
                return None
            cached = sub_tree._flat_cached(fields['tree_id'], read_key) if chain else None   # the head itself is not cached
            if cached is not None:
                base = cached; break
            snap = self._flat_from_snapshot(directory, cid, fields['tree_id'], read_key, sub_tree, _p)
            if snap is not None:
                if not chain:
                    sub_tree._flat_remember(fields['tree_id'], snap[0], snap[1])
                    self.last_seed = 'snapshot'
                    return {p: dict(e) for p, e in snap[0].items()}, dict(snap[1])
                base = snap; break
            chain.append(cid)
            if len(chain) > DELTA_CHAIN_MAX:
                return None
            if not fields['parents']:
                base = ({}, {}); break                                       # the root commit: everything is new
            cid = fields['parents'][0]
        state = Flat__Assembly().setup(base[0], base[1])
        for cid in reversed(chain):
            got = self.folder_members(directory, cid, read_key, kind='commit', _p=_p)
            if got is None:
                return None
            folders, header = got
            tree_id = str(header.get('tree_id') or '')
            if tree_id == state.dirs.get(''):
                continue                                                     # an empty commit: the map is the parent's
            if not state.apply(folders, tree_id):
                self._drop(directory, cid, 'commit', _p, 'its folder members do not join the parent map')
                return None
        flat, dirs = state.flat, state.dirs
        head_tree  = dirs.get('')
        if not head_tree or not sub_tree._flat_cache_matches_root(head_tree, read_key, flat, dirs):
            self._drop(directory, head_commit_id, 'commit', _p, 'the assembled map does not match the root tree')
            return None
        sub_tree._flat_remember(head_tree, flat, dirs)
        self.last_seed = 'deltas'
        return {p: dict(e) for p, e in flat.items()}, dict(dirs)

    def _flat_from_snapshot(self, directory: str, commit_id: str, tree_id: str, read_key: bytes, sub_tree, _p):
        """(flat, dirs) of a snapshot index's `flat` member: the flat cache's shape (every
        id an object id) and the root tree's entries, or None. Not remembered here: the
        caller decides (a base below the head is kept in memory only)."""
        opened = self.open_index(directory, commit_id, read_key, kind='snapshot', _p=_p)
        if opened is None:
            return None
        data, header = opened
        try:
            doc = self.member(data, header, 'flat', read_key)
            hit = sub_tree._flat_cache_check(tree_id, doc) if isinstance(doc, dict) else None
            if hit is None:
                raise ValueError('flat member is not a flat map of this tree')
            flat, dirs = hit
            if not sub_tree._flat_cache_matches_root(tree_id, read_key, flat, dirs):
                raise ValueError('flat member does not match the root tree')
        except Exception as error:
            self._drop(directory, commit_id, 'snapshot', _p, f'flat: {str(error)[:80]}')
            return None
        return flat, dirs

    def assemble(self, folders: dict, tree_id: str, base_flat: dict, base_dirs: dict):
        """(flat, dirs) of a head from its commit index's folder members over its first
        parent's map (one delta; seed_head_flat keeps one Flat__Assembly across a chain)."""
        state = Flat__Assembly().setup(base_flat, base_dirs)
        return (state.flat, state.dirs) if state.apply(folders, tree_id) else None

    # ------------------------------------------------------------------ using: history log
    def changes_provider(self, directory: str, read_key: bytes, c=None):
        """A callable (commit id) -> {'changes', 'folders', ...} | None for Vault__Inspector,
        or None when this clone does not read indexes."""
        try:
            if not self.pack_vault and not self.is_pack_vault(directory):
                return None
            if not self.usable_in(directory):
                return None
            self.setup_for(directory, read_key, c=c)
        except Exception:
            return None
        return lambda commit_id: self.changes_of_commit(directory, commit_id, read_key)


class Flat__Assembly:
    """A head's (flat, dirs) built from a base map by applying commit indexes' folder
    members, each delta touching only the folders it names: a folder with a member is
    replaced by the member (its files and its children); a child folder the member
    no longer lists is removed with its subtree; a child without a member must be the
    map's at that path with the same id (checked), else the delta does not join. Plain
    dicts and sets, one copy of the base, no per-delta rebuild (the first version
    rebuilt the whole 229,000-entry map per delta: 12 s of a 19 s seed)."""

    def setup(self, base_flat: dict, base_dirs: dict):
        self.flat        = {p: dict(e) for p, e in base_flat.items()}
        self.dirs        = dict(base_dirs)
        self.files_under = {}                                                # folder -> its file paths
        self.children    = {}                                                # folder -> its child folders
        for path in self.flat:
            self.files_under.setdefault(path.rpartition('/')[0], set()).add(path)
        for path in self.dirs:
            if path:
                self.children.setdefault(path.rpartition('/')[0], set()).add(path)
        return self

    def apply(self, folders: dict, tree_id: str) -> bool:
        root = folders.get('')
        if root is None or str(root['tree_id']) != tree_id:
            return False
        stack = [('', root)]
        while stack:
            path, m = stack.pop()
            for old in self.files_under.get(path, ()):
                self.flat.pop(old, None)
            new_files = {(f'{path}/{name}' if path else name): dict(e) for name, e in m['files'].items()}
            self.flat.update(new_files)
            self.files_under[path] = set(new_files)
            self.dirs[path] = str(m['tree_id'])
            new_children = {(f'{path}/{name}' if path else name): str(tid) for name, tid in m['dirs'].items()}
            for gone in self.children.get(path, set()) - set(new_children):
                self._remove_subtree(gone)
            self.children[path] = set(new_children)
            for child, tid in new_children.items():
                member = folders.get(child)
                if member is not None:
                    if str(member['tree_id']) != tid:
                        return False
                    stack.append((child, member))
                elif self.dirs.get(child) != tid:
                    return False                                             # unchanged by the index, unknown to the map
        return True

    def _remove_subtree(self, path: str) -> None:
        stack = [path]
        while stack:
            folder = stack.pop()
            for p in self.files_under.pop(folder, ()):
                self.flat.pop(p, None)
            self.dirs.pop(folder, None)
            stack.extend(self.children.pop(folder, ()))
