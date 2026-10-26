"""Vault__Pack_Index — the index pack beside a data pack (cli.sgit.ai dev pack "pack
indexes", 26 Oct 2026, Phase 1: the writer).

  bare/packs/indexes/commits/    <epoch>__<commit>__<bytes>.zip   indexes commits/<epoch>__<commit>__*.zip
  bare/packs/indexes/snapshots/  <epoch>__<commit>__<bytes>.zip   indexes snapshots/...
  bare/packs/indexes/archive/    moved with the data pack it indexes

An index pack is a ZIP_STORED zip whose member 0 is `index/header` and whose other
members are `index/000001`, `index/000002`, ... in the order the header lists them:
the names carry no meaning, the host learns no path, type or changed folder. The
header is MAGIC + L + encrypt(read_key, deflate(canonical header JSON)), padded to a
reserved size R so the member offsets it lists are fixed before its own length is
known; the header JSON is signed by the pusher's clone key over the same canonical
form a commit is signed with, so an index has the standing of its commit. Every
other member is encrypt(read_key, deflate(member JSON)).

Members (dev pack 01 §3): a commit index carries `changes` (what the commit changed
against its first parent) and `folder:<path>` for every folder on a changed path; a
snapshot index carries `flat` (the head's flat map and folder ids, the flat cache's
own shape), `folder:<path>` for every folder, `commits:<n>` (reachable commits by
generation shard) with `commit-gen`, `blob-paths:<xx>` and `file-commits:<xx>`.

Rules (dev pack 02 §8): an index is built from the same maps the trees were built
from, never from the working copy; nothing in clear but sequence numbers; an index
upload that fails never fails the push (it is a gap, recorded locally, filled by
`sgit pack index build`). 0.24.0–0.25.0 never list bare/packs/indexes/, so they are
unaffected; the advisory feature 'pack-indexes' tells a reader to look.
"""
import base64
import hashlib
import io
import json
import os
import struct
import time
import zipfile
import zlib
from sgit_ai.core.actions.pack.Vault__Packs      import (Vault__Packs, PACK_COMMITS, PACK_SNAPSHOTS, PACK_ARCHIVE,
                                                         PACK_NAME_RE, ZIP_EPOCH)
from sgit_ai.crypto.PKI__Crypto                  import PKI__Crypto
from sgit_ai.schemas.Schema__Pack_Index__Header   import Schema__Pack_Index__Header
from sgit_ai.schemas.Schema__Pack_Index__Changes  import Schema__Pack_Index__Changes
from sgit_ai.schemas.Schema__Pack_Index__Folder   import Schema__Pack_Index__Folder
from sgit_ai.storage.Vault__Commit               import Vault__Commit
from sgit_ai.storage.Vault__Object_Store         import Vault__Object_Store
from sgit_ai.storage.Vault__Storage              import Vault__Storage, SG_VAULT_DIR
from sgit_ai.storage.Vault__Sub_Tree             import Vault__Sub_Tree, FLAT_CACHE_VERSION

PACK_INDEXES          = 'bare/packs/indexes/'
PACK_INDEX_COMMITS    = PACK_INDEXES + 'commits/'
PACK_INDEX_SNAPSHOTS  = PACK_INDEXES + 'snapshots/'
PACK_INDEX_ARCHIVE    = PACK_INDEXES + 'archive/'
INDEX_FOLDER_OF       = {PACK_COMMITS: PACK_INDEX_COMMITS, PACK_SNAPSHOTS: PACK_INDEX_SNAPSHOTS, PACK_ARCHIVE: PACK_INDEX_ARCHIVE}
INDEX_MAGIC           = b'SGIX\x00\x01\x00\x00'            # format 1; the format byte changes only with the binary layout
INDEX_HEADER_NAME     = 'index/header'
INDEX_MEMBER_PREFIX   = 'index/'
INDEX_HEADER_STEP     = 16 * 1024                           # R is a multiple of this
INDEX_HEADER_SLACK    = 4096
INDEX_HEADER_MAX      = 64 * 1024 * 1024                    # a crafted header cannot ask for more (dev pack 04)
INDEX_MEMBER_MAX      = 256 * 1024 * 1024
INDEX_SCHEMA          = 'pack_index_v1'
FOLDER_SCHEMA         = 'folder_v1'
CHANGES_SCHEMA        = 'changes_v1'
COMMITS_SHARD         = 1024                                # commits:<n> holds generations [n*1024, (n+1)*1024)
XREF_SHARDS           = 256                                 # blob-paths:<xx>, file-commits:<xx>: two hex digits
LOCAL_INDEX_DIR       = 'index'                             # .sg_vault/local/index/
GAPS_FILE             = 'gaps.json'                         # data packs this clone pushed without an index
GENERATIONS_FILE      = 'generations.json'                  # commit id -> generation, this clone's memo (derived)
INDEXES_ENV           = 'SGIT_PACK_INDEXES'                 # '0' turns the writer off (stage 1 opt-out)
LOCAL_HEADER_FIXED    = 30                                  # bytes of a zip local file header before the name
MAX_OFFSET_DIGITS     = 15


class Vault__Pack_Index(Vault__Packs):
    last_index_members : int = 0
    last_index_bytes   : int = 0

    # ------------------------------------------------------------------ switches and paths
    def writer_enabled(self) -> bool:
        return os.environ.get(INDEXES_ENV, '1') not in ('0', 'false', 'no', 'off')

    def index_folder_of(self, data_folder: str) -> str:
        return INDEX_FOLDER_OF[data_folder]

    def local_index_dir(self, directory: str) -> str:
        return os.path.join(Vault__Storage().local_dir(directory), LOCAL_INDEX_DIR)

    def local_index_pack_path(self, directory: str, index_folder: str, name: str) -> str:
        sub = index_folder[len(PACK_INDEXES):].strip('/')                   # commits | snapshots | archive
        return os.path.join(self.local_index_dir(directory), 'packs', sub, name)

    # ------------------------------------------------------------------ bytes of a member
    def canonical_json(self, obj) -> bytes:
        return json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')

    def seal_member(self, read_key: bytes, plain_json: bytes) -> bytes:
        return self.crypto.encrypt(read_key, zlib.compress(plain_json, 6))

    def open_member(self, read_key: bytes, sealed: bytes) -> bytes:
        return zlib.decompress(self.crypto.decrypt(read_key, sealed))

    def member_sha(self, plain_json: bytes) -> str:
        return hashlib.sha256(plain_json).hexdigest()

    # ------------------------------------------------------------------ generations
    def _generations_path(self, sg_dir: str) -> str:
        return os.path.join(sg_dir, 'local', LOCAL_INDEX_DIR, GENERATIONS_FILE)

    def load_generations(self, sg_dir: str) -> dict:
        try:
            with open(self._generations_path(sg_dir)) as f:
                data = json.load(f)
            return {str(k): int(v) for k, v in (data.get('generations') or {}).items()}
        except Exception:
            return {}

    def save_generations(self, sg_dir: str, generations: dict) -> None:
        path = self._generations_path(sg_dir)
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            tmp = path + '.tmp'
            with open(tmp, 'w') as f:
                json.dump(dict(generations=generations), f, separators=(',', ':'))
            os.replace(tmp, path)
        except OSError:
            pass                                                            # a memo: a failure to save is nothing

    def generation_of(self, sg_dir: str, commit_id: str, read_key: bytes, memo: dict = None) -> int:
        """1 + the highest parent generation; 1 for a root. Iterative, memoised per clone
        (local/index/generations.json), so a history is walked once. A parent that is not
        local (a shallow boundary) counts as generation 0."""
        memo  = self.load_generations(sg_dir) if memo is None else memo
        store = Vault__Object_Store(vault_path=sg_dir, crypto=self.crypto)
        stack = [commit_id]
        while stack:
            cid = stack[-1]
            if cid in memo:
                stack.pop(); continue
            if not store.exists(cid):
                memo[cid] = 0; stack.pop(); continue
            parents = self.parents_of(sg_dir, cid, read_key)
            pending = [p for p in parents if p not in memo]
            if pending:
                stack.extend(pending); continue
            memo[cid] = 1 + max([memo[p] for p in parents] or [0])
            stack.pop()
        return memo[commit_id]

    # ------------------------------------------------------------------ the maps
    def _sub_tree(self, sg_dir: str) -> Vault__Sub_Tree:
        return Vault__Sub_Tree(crypto=self.crypto, obj_store=Vault__Object_Store(vault_path=sg_dir, crypto=self.crypto))

    def commit_fields(self, sg_dir: str, commit_id: str, read_key: bytes) -> dict:
        commit = self._vault_commit(sg_dir).load_commit(commit_id, read_key)
        return dict(commit_id    = commit_id,
                    parents      = [str(p) for p in (commit.parents or []) if str(p)],
                    tree_id      = str(commit.tree_id or ''),
                    timestamp_ms = int(commit.timestamp_ms) if commit.timestamp_ms else 0)

    def _commit_fields_or_none(self, sg_dir: str, commit_id: str, read_key: bytes):
        try:
            return self.commit_fields(sg_dir, commit_id, read_key)
        except Exception:
            return None

    def _changes_or_empty(self, sg_dir: str, commit_id: str, read_key: bytes) -> list:
        try:
            return self.changes_of(sg_dir, commit_id, read_key)
        except Exception:
            return []

    def changes_of(self, sg_dir: str, commit_id: str, read_key: bytes) -> list:
        """[{path, op, old_blob, new_blob, size, content_hash, content_type, large}] of a
        commit against its first parent, from the pruned tree diff (a folder whose id is
        unchanged is never opened). A merge is diffed against its first parent."""
        fields   = self.commit_fields(sg_dir, commit_id, read_key)
        sub      = self._sub_tree(sg_dir)
        old_tree = None
        if fields['parents']:
            try:
                old_tree = self.commit_fields(sg_dir, fields['parents'][0], read_key)['tree_id'] or None
            except Exception:
                old_tree = None
        diff = sub.diff_trees(fields['tree_id'], old_tree, read_key)
        out  = []
        for path, e in diff['added'].items():
            out.append(dict(path=path, op='A', new_blob=e['blob_id'], size=int(e.get('size', 0)),
                            content_hash=e.get('content_hash', ''), content_type=e.get('content_type', ''), large=bool(e.get('large', False))))
        for path, (e, o) in diff['modified'].items():
            out.append(dict(path=path, op='M', old_blob=o['blob_id'], new_blob=e['blob_id'], size=int(e.get('size', 0)),
                            content_hash=e.get('content_hash', ''), content_type=e.get('content_type', ''), large=bool(e.get('large', False))))
        for path, o in diff['deleted'].items():
            out.append(dict(path=path, op='D', old_blob=o['blob_id']))
        out.sort(key=lambda r: r['path'])
        return out

    def folder_entries(self, flat: dict, dirs: dict) -> dict:
        """{folder path: folder member dict (folder_v1)} for every folder of a head, with the
        subtree totals rolled up deepest-first. Plain dicts of the Schema__Pack_Index__Folder
        shape (a snapshot has tens of thousands)."""
        files_of = {}
        for path, entry in flat.items():
            parent, _, name = path.rpartition('/')
            files_of.setdefault(parent, {})[name] = entry
        dirs_of = {}
        for path in dirs:
            if path:
                parent, _, name = path.rpartition('/')
                dirs_of.setdefault(parent, {})[name] = dirs[path]
        totals = {}
        for path in sorted(dirs, key=lambda p: -p.count('/') if p else 1):           # deepest first; root last
            files = files_of.get(path, {})
            t     = dict(files=len(files), bytes=sum(int(e.get('size', 0)) for e in files.values()), folders=0)
            for name in dirs_of.get(path, {}):
                child = f'{path}/{name}' if path else name
                ct    = totals.get(child, dict(files=0, bytes=0, folders=0))
                t['files'] += ct['files']; t['bytes'] += ct['bytes']; t['folders'] += 1 + ct['folders']
            totals[path] = t
        return {path: dict(schema=FOLDER_SCHEMA, path=path, tree_id=dirs[path], files=files_of.get(path, {}),
                           dirs=dirs_of.get(path, {}), totals=totals[path])
                for path in dirs}

    def ancestors_of(self, path: str) -> list:
        """Every folder on the path's way up, root ('') included."""
        out, p = [], path.rpartition('/')[0]
        while True:
            out.append(p)
            if not p:
                return out
            p = p.rpartition('/')[0]

    def shard_of_blob(self, blob_id: str) -> str:
        return str(blob_id)[len('obj-cas-imm-'):][:2]

    def shard_of_path(self, path: str) -> str:
        return hashlib.sha256(path.encode('utf-8')).hexdigest()[:2]

    # ------------------------------------------------------------------ building the member sets
    def build_commit_members(self, sg_dir: str, commit_id: str, read_key: bytes) -> tuple:
        """(header fields, {member name: plain JSON bytes}) for one commit: `changes` and a
        `folder:<path>` for every folder whose tree id changed (every folder on a changed
        path, including a new one; a deleted folder has no member: it is not in the head)."""
        fields  = self.commit_fields(sg_dir, commit_id, read_key)
        sub     = self._sub_tree(sg_dir)
        memo    = self.load_generations(sg_dir)
        gen     = self.generation_of(sg_dir, commit_id, read_key, memo)
        self.save_generations(sg_dir, memo)
        changes = self.changes_of(sg_dir, commit_id, read_key)
        flat    = sub.flatten(fields['tree_id'], read_key)
        dirs    = sub.flatten_dirs(fields['tree_id'], read_key)
        old_dirs = {}
        if fields['parents']:
            try:
                old_tree = self.commit_fields(sg_dir, fields['parents'][0], read_key)['tree_id']
                old_dirs = sub.flatten_dirs(old_tree, read_key) if old_tree else {}
            except Exception:
                old_dirs = {}
        touched = set()
        for change in changes:
            touched.update(self.ancestors_of(change['path']))
        folders = self.folder_entries(flat, dirs)
        members = {}
        changed_doc = Schema__Pack_Index__Changes(schema=CHANGES_SCHEMA, commit_id=commit_id, parents=fields['parents'],
                                                  generation=gen, timestamp_ms=fields['timestamp_ms'],
                                                  tree_id=fields['tree_id'], changes=changes)   # typed at the writer ...
        doc = changed_doc.json()
        doc['changes'] = changes                                               # ... serialised lean: a D record is path, op, old_blob
        members['changes'] = self.canonical_json(doc)
        for path in sorted(touched):
            if path in dirs and dirs[path] != old_dirs.get(path):
                members[f'folder:{path}'] = self.canonical_json(Schema__Pack_Index__Folder.from_json(folders[path]).json())
        fields['generation'] = gen
        return fields, members

    def build_snapshot_members(self, sg_dir: str, head_commit_id: str, read_key: bytes, on_progress=None) -> tuple:
        """(header fields, members) for a head: flat, every folder, the reachable commits
        by generation shard, commit-gen, and the two cross-references."""
        _p      = on_progress or (lambda *a, **k: None)
        fields  = self.commit_fields(sg_dir, head_commit_id, read_key)
        sub     = self._sub_tree(sg_dir)
        memo    = self.load_generations(sg_dir)
        gen     = self.generation_of(sg_dir, head_commit_id, read_key, memo)
        flat    = sub.flatten(fields['tree_id'], read_key)
        dirs    = sub.flatten_dirs(fields['tree_id'], read_key)
        members = {}
        members['flat'] = self.canonical_json(dict(version=FLAT_CACHE_VERSION, tree_id=fields['tree_id'], flat=flat, dirs=dirs))
        for path, folder in self.folder_entries(flat, dirs).items():
            members[f'folder:{path}'] = self.canonical_json(folder)
        # the commit graph, by generation shard
        reachable = self.reachable_commits(sg_dir, head_commit_id, read_key)
        commits   = {}
        commit_gen = {}
        for cid in reachable:
            f = self._commit_fields_or_none(sg_dir, cid, read_key)
            if f is None:
                continue                                                     # a commit whose object is not local
            g = self.generation_of(sg_dir, cid, read_key, memo)
            commit_gen[cid] = g
            commits.setdefault(g // COMMITS_SHARD, {})[cid] = dict(parents=f['parents'], generation=g,
                                                                   timestamp_ms=f['timestamp_ms'], tree_id=f['tree_id'])
        self.save_generations(sg_dir, memo)
        for n, shard in commits.items():
            members[f'commits:{n}'] = self.canonical_json(shard)
        members['commit-gen'] = self.canonical_json(commit_gen)
        # cross-references: blob -> paths (the head), path -> commits that changed it (the history)
        blob_paths = {}
        for path, entry in flat.items():
            blob_paths.setdefault(self.shard_of_blob(entry['blob_id']), {}).setdefault(entry['blob_id'], []).append(path)
        for xx, shard in blob_paths.items():
            for paths in shard.values():
                paths.sort()
            members[f'blob-paths:{xx}'] = self.canonical_json(shard)
        file_commits = {}
        by_time = sorted(commit_gen, key=lambda c: (-commit_gen[c], c))        # newest first by generation
        _p('step', 'Indexing history', f'{len(by_time)} commit(s)')
        for cid in by_time:
            for change in self._changes_or_empty(sg_dir, cid, read_key):     # [] for a commit whose trees are not local
                file_commits.setdefault(self.shard_of_path(change['path']), {}).setdefault(change['path'], []).append(cid)
        for key, shard in file_commits.items():
            members[f'file-commits:{key}'] = self.canonical_json(shard)
        fields['generation'] = gen
        return fields, members

    # ------------------------------------------------------------------ the zip
    def _member_name(self, seq: int) -> str:
        return f'{INDEX_MEMBER_PREFIX}{seq:06d}'

    def layout(self, member_lengths: list, reserved: int) -> list:
        """Data offsets of member 0 (the header, `reserved` bytes) and members 1..n, for a
        zip written in that order with no extra fields: each local header is 30 bytes plus
        the name."""
        offsets = []
        pos     = LOCAL_HEADER_FIXED + len(INDEX_HEADER_NAME)
        offsets.append(pos)
        pos += reserved
        for seq, length in enumerate(member_lengths, start=1):
            pos += LOCAL_HEADER_FIXED + len(self._member_name(seq))
            offsets.append(pos)
            pos += length
        return offsets

    def write_index_pack(self, out_path: str, read_key: bytes, kind: str, fields: dict, members: dict,
                         data_packs: list, signing_key=None, author_key_id: str = '') -> int:
        """The index pack file; returns its size. `members` is {name: plain JSON bytes}."""
        names   = sorted(members)
        sealed  = [self.seal_member(read_key, members[n]) for n in names]
        shas    = [self.member_sha(members[n]) for n in names]
        lengths = [len(b) for b in sealed]
        for b in sealed:
            if len(b) > INDEX_MEMBER_MAX:
                raise RuntimeError('an index member exceeds the size a reader accepts')

        def header_doc(offsets):
            rows = [dict(name=n, seq=i + 1, offset=offsets[i + 1], length=lengths[i], sha256=shas[i]) for i, n in enumerate(names)]
            doc  = Schema__Pack_Index__Header(schema=INDEX_SCHEMA, kind=kind, commit_id=fields['commit_id'], parents=fields['parents'],
                                              generation=int(fields['generation']), tree_id=fields['tree_id'],
                                              timestamp_ms=int(fields['timestamp_ms']), data_packs=list(data_packs), members=rows,
                                              author_key_id=author_key_id or None).json()
            doc.pop('signature', None)
            body = self.canonical_json(doc)
            if signing_key is not None:
                doc['signature'] = base64.b64encode(PKI__Crypto().sign(signing_key, body)).decode('ascii')
            else:
                doc['signature'] = None
            return doc

        wide     = self.layout(lengths, 0)
        estimate = len(self.seal_member(read_key, self.canonical_json(header_doc([10 ** MAX_OFFSET_DIGITS] * len(wide)))))
        reserved = -(-(12 + estimate + INDEX_HEADER_SLACK) // INDEX_HEADER_STEP) * INDEX_HEADER_STEP
        while True:
            offsets  = self.layout(lengths, reserved)
            envelope = self.seal_member(read_key, self.canonical_json(header_doc(offsets)))
            if 12 + len(envelope) <= reserved:
                break
            reserved *= 2
            if reserved > INDEX_HEADER_MAX:
                raise RuntimeError('index header too large')
        header_bytes = INDEX_MAGIC + struct.pack('>I', len(envelope)) + envelope
        header_bytes += b'\x00' * (reserved - len(header_bytes))
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with zipfile.ZipFile(out_path, 'w', compression=zipfile.ZIP_STORED, allowZip64=True) as z:
            info = zipfile.ZipInfo(INDEX_HEADER_NAME, date_time=ZIP_EPOCH); info.compress_type = zipfile.ZIP_STORED
            z.writestr(info, header_bytes)
            for i, data in enumerate(sealed, start=1):
                info = zipfile.ZipInfo(self._member_name(i), date_time=ZIP_EPOCH); info.compress_type = zipfile.ZIP_STORED
                z.writestr(info, data)
        with zipfile.ZipFile(out_path) as z:                                   # the layout must be what the header says
            for i, data in enumerate(sealed, start=1):
                zi = z.getinfo(self._member_name(i))
                if zi.header_offset + LOCAL_HEADER_FIXED + len(zi.filename) + len(zi.extra) != offsets[i]:
                    raise RuntimeError('index pack layout mismatch')
        self.last_index_members = len(names)
        self.last_index_bytes   = os.path.getsize(out_path)
        return self.last_index_bytes

    # ------------------------------------------------------------------ reading (the writer's own checks; the reader builds on these)
    def read_header(self, data: bytes, read_key: bytes) -> dict:
        """The header JSON of an index pack's bytes, from the first local file header only
        (never the central directory): magic, L, decrypt, inflate. Raises on any defect."""
        if len(data) < LOCAL_HEADER_FIXED + len(INDEX_HEADER_NAME) + 12:
            raise ValueError('not an index pack: too short')
        if data[:4] != b'PK\x03\x04':
            raise ValueError('not a zip')
        name_len = struct.unpack('<H', data[26:28])[0]
        extra_len = struct.unpack('<H', data[28:30])[0]
        method   = struct.unpack('<H', data[8:10])[0]
        name     = data[LOCAL_HEADER_FIXED:LOCAL_HEADER_FIXED + name_len].decode('utf-8', 'replace')
        if name != INDEX_HEADER_NAME or method != 0:
            raise ValueError('not an index pack: first member is not the stored header')
        start = LOCAL_HEADER_FIXED + name_len + extra_len
        if data[start:start + 8] != INDEX_MAGIC:
            if data[start:start + 4] != INDEX_MAGIC[:4]:
                raise ValueError('not an index pack: bad magic')
            raise ValueError('index pack of another format')
        length = struct.unpack('>I', data[start + 8:start + 12])[0]
        if length > INDEX_HEADER_MAX:
            raise ValueError('index header declares more than a reader accepts')
        envelope = data[start + 12:start + 12 + length]
        header   = json.loads(self.open_member(read_key, envelope).decode('utf-8'))
        if not isinstance(header, dict) or header.get('schema') != INDEX_SCHEMA:
            raise ValueError('index header of another schema')
        return header

    def header_signing_bytes(self, header: dict) -> bytes:
        return self.canonical_json({k: v for k, v in header.items() if k != 'signature'})

    def verify_header_signature(self, header: dict, public_key) -> bool:
        sig = header.get('signature')
        if not sig:
            return False
        try:
            return PKI__Crypto().verify(public_key, base64.b64decode(str(sig)), self.header_signing_bytes(header))
        except Exception:
            return False

    def member_table(self, header: dict) -> dict:
        return {str(m['name']): m for m in (header.get('members') or []) if isinstance(m, dict) and m.get('name')}

    def read_member(self, data: bytes, header: dict, name: str, read_key: bytes):
        """The JSON of one member, checked against the header's sha256; None when absent."""
        row = self.member_table(header).get(name)
        if row is None:
            return None
        offset, length = int(row['offset']), int(row['length'])
        if length > INDEX_MEMBER_MAX or offset + length > len(data):
            raise ValueError(f'index member {name}: out of bounds')
        plain = self.open_member(read_key, data[offset:offset + length])
        if self.member_sha(plain) != str(row.get('sha256', '')):
            raise ValueError(f'index member {name}: hash mismatch')
        return json.loads(plain.decode('utf-8'))

    # ------------------------------------------------------------------ signing identity
    def signing_identity(self, directory: str, c=None) -> tuple:
        """(private key, key id) of this clone, or (None, '') when it has none."""
        try:
            c      = c or self._init_components(directory)
            config = self._read_local_config(directory, c.storage)
            index  = c.branch_manager.load_branch_index(directory, c.branch_index_file_id, c.read_key)
            meta   = c.branch_manager.get_branch_by_id(index, str(config.my_branch_id or ''))
            key_id = str(meta.public_key_id) if meta is not None and meta.public_key_id else ''
            if not key_id:
                return None, ''
            return c.key_manager.load_private_key_locally(key_id, c.storage.local_dir(directory)), key_id
        except Exception:
            return None, ''

    # ------------------------------------------------------------------ gaps
    def _gaps_path(self, directory: str) -> str:
        return os.path.join(self.local_index_dir(directory), GAPS_FILE)

    def load_gaps(self, directory: str) -> list:
        try:
            with open(self._gaps_path(directory)) as f:
                return sorted(set(json.load(f).get('packs') or []))
        except Exception:
            return []

    def record_gap(self, directory: str, data_file_id: str) -> None:
        self._save_gaps(directory, set(self.load_gaps(directory)) | {data_file_id})

    def clear_gap(self, directory: str, data_file_id: str) -> None:
        self._save_gaps(directory, set(self.load_gaps(directory)) - {data_file_id})

    def _save_gaps(self, directory: str, packs: set) -> None:
        path = self._gaps_path(directory)
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            tmp = path + '.tmp'
            with open(tmp, 'w') as f:
                json.dump(dict(packs=sorted(packs)), f, indent=1)
            os.replace(tmp, path)
        except OSError:
            pass

    # ------------------------------------------------------------------ build + upload, per data pack
    def write_for_data_pack(self, directory: str, vault_id: str, write_key: str, read_key: bytes,
                            data_folder: str, data_name: str, commit_id: str, on_progress=None, c=None) -> str:
        """Build the index pack of one data pack (commits/ -> a commit index, snapshots/ -> a
        snapshot index), upload it beside the data pack under indexes/, keep a local copy,
        and return its name. Raises on failure: the caller decides (a push records a gap)."""
        _p       = on_progress or (lambda *a, **k: None)
        sg_dir   = os.path.join(directory, SG_VAULT_DIR)
        info     = self.parse_name(data_name)
        if info is None:
            raise ValueError(f'not a pack name: {data_name}')
        work_dir = os.path.join(sg_dir, 'work', 'packs')
        os.makedirs(work_dir, exist_ok=True)
        kind     = 'snapshot' if data_folder == PACK_SNAPSHOTS else 'commit'
        if kind == 'snapshot':
            fields, members = self.build_snapshot_members(sg_dir, commit_id, read_key, _p)
        else:
            fields, members = self.build_commit_members(sg_dir, commit_id, read_key)
        signing_key, key_id = self.signing_identity(directory, c)
        tmp  = os.path.join(work_dir, f'index-{kind}-{commit_id}.zip')
        size = self.write_index_pack(tmp, read_key, kind, fields, members, data_packs=[data_name],
                                     signing_key=signing_key, author_key_id=key_id)
        name = self.pack_name(commit_id, size, epoch_s=info['epoch'])          # paired with its data pack by (folder, epoch, commit)
        index_folder = self.index_folder_of(data_folder)
        _p('step', 'Uploading index pack', f'{name} ({size / 1e3:.1f} KB, {len(members)} members)')
        self.upload_pack(vault_id, write_key, index_folder + name, tmp, on_progress)
        local = self.local_index_pack_path(directory, index_folder, name)
        os.makedirs(os.path.dirname(local), exist_ok=True)
        os.replace(tmp, local)
        self.clear_gap(directory, data_folder + data_name)
        return name

    def try_write_for_data_pack(self, directory: str, vault_id: str, write_key: str, read_key: bytes,
                                data_folder: str, data_name: str, commit_id: str, on_progress=None, c=None) -> str:
        """As write_for_data_pack, but a failure is a warning and a recorded gap, never an
        error: the data pack is on the host and the ref will move; an index is derived."""
        _p = on_progress or (lambda *a, **k: None)
        if not self.writer_enabled():
            return ''
        try:
            return self.write_for_data_pack(directory, vault_id, write_key, read_key, data_folder, data_name, commit_id, on_progress, c)
        except Exception as error:
            self.record_gap(directory, data_folder + data_name)
            _p('warning', 'Index pack not written (the data pack is on the host; a reader walks instead)',
               f'{data_name}: {type(error).__name__}: {str(error)[:120]}. `sgit pack index build` retries.')
            return ''

    # ------------------------------------------------------------------ listing
    def list_index_packs(self, vault_id: str, index_folder: str) -> list:
        return self.list_folder(vault_id, index_folder)

    def index_pack_for(self, vault_id: str, data_folder: str, entry: dict) -> dict:
        """The index pack entry paired with a data pack entry, or None."""
        for e in self.list_index_packs(vault_id, self.index_folder_of(data_folder)):
            if e['commit_id'] == entry['commit_id'] and e['epoch'] == entry['epoch']:
                return e
        return None

    # ------------------------------------------------------------------ sgit pack index build | verify | stats
    def data_packs_without_index(self, vault_id: str) -> list:
        """[(data folder, data entry)] for every pack in commits/ and snapshots/ that has
        no index pack beside it (a gap: an older client's push, or a failed upload)."""
        out = []
        for folder in (PACK_COMMITS, PACK_SNAPSHOTS):
            indexed = {(e['commit_id'], e['epoch']) for e in self.list_index_packs(vault_id, self.index_folder_of(folder))}
            for entry in self.list_folder(vault_id, folder):
                if (entry['commit_id'], entry['epoch']) not in indexed:
                    out.append((folder, entry))
        return out

    def build_missing(self, directory: str, rebuild_snapshot: bool = False, on_progress=None) -> dict:
        """`sgit pack index build [--all]`: write the index pack for every data pack that
        lacks one and whose commit this clone holds; with rebuild_snapshot, the newest
        snapshot's index is rewritten too. Adds the advisory feature to the branch index
        when it is missing. Needs the write key."""
        _p = on_progress or (lambda *a, **k: None)
        c  = self._init_components(directory)
        if not c.write_key:
            raise RuntimeError('writing index packs needs the write key (a read-only clone cannot)')
        if not self.pack_vault:
            raise RuntimeError(f'{directory} is not a pack vault')
        sg_dir  = os.path.join(directory, SG_VAULT_DIR)
        store   = Vault__Object_Store(vault_path=sg_dir, crypto=self.crypto)
        self.sync_down(directory, c.vault_id, c.read_key, _p)                 # the packs this clone has not absorbed
        todo    = self.data_packs_without_index(c.vault_id)
        if rebuild_snapshot:
            snaps = self.list_folder(c.vault_id, PACK_SNAPSHOTS)
            if snaps:
                todo.append((PACK_SNAPSHOTS, snaps[-1]))
        written, skipped = [], []
        for folder, entry in todo:
            if not store.exists(entry['commit_id']):
                skipped.append(entry['name']); continue
            try:
                name = self.write_for_data_pack(directory, c.vault_id, c.write_key, c.read_key, folder, entry['name'],
                                                entry['commit_id'], _p, c)
                written.append(name)
            except Exception as error:
                skipped.append(entry['name'])
                _p('warning', 'Index pack not written', f'{entry["name"]}: {str(error)[:120]}')
        self.ensure_feature(directory, c, _p)
        return dict(written=written, skipped=skipped, gaps=self.load_gaps(directory))

    def ensure_feature(self, directory: str, c=None, on_progress=None) -> bool:
        """The advisory 'pack-indexes' feature in the branch index (a new pack vault has it
        from init; an older one gains it on the first `pack index build`). Written through
        the format action, under the same compare-and-swap as any branch-index change."""
        from sgit_ai.storage.Vault__Format import FEATURE_PACK_INDEXES
        if FEATURE_PACK_INDEXES in self.features_of_directory(directory):
            return False
        from sgit_ai.core.actions.format.Vault__Sync__Format import Vault__Sync__Format
        Vault__Sync__Format(crypto=self.crypto, api=self.api).set_format(directory, add_features=[FEATURE_PACK_INDEXES],
                                                                         on_progress=on_progress)
        return True

    def verify_indexes(self, directory: str) -> dict:
        """`sgit pack index verify` (read-only): every index pack on the host against its data
        pack and the trees: header decrypts and names a known schema; the signature verifies
        with the key it names (or the index is reported unsigned); commit, parents, tree id
        and timestamp match the commit object; every member's sha256; `flat` equals a full
        flatten; `changes` equals the tree diff; each `folder:*` equals its tree."""
        c      = self._init_components(directory)
        sg_dir = os.path.join(directory, SG_VAULT_DIR)
        sub    = self._sub_tree(sg_dir)
        store  = Vault__Object_Store(vault_path=sg_dir, crypto=self.crypto)
        report = dict(packs=0, members=0, unsigned=[], orphans=[], gaps=[], bad=[], ok=True)
        for data_folder in (PACK_COMMITS, PACK_SNAPSHOTS, PACK_ARCHIVE):
            index_folder = self.index_folder_of(data_folder)
            data_entries = {(e['commit_id'], e['epoch']): e for e in self.list_folder(c.vault_id, data_folder)}
            index_entries = self.list_index_packs(c.vault_id, index_folder)
            seen = set()
            for entry in index_entries:
                key = (entry['commit_id'], entry['epoch'])
                seen.add(key)
                if key not in data_entries:
                    report['orphans'].append(entry['file_id']); continue
                report['packs'] += 1
                try:
                    data   = self.fetch_pack(c.vault_id, entry)
                    header = self.read_header(data, c.read_key)
                    self._verify_one(c, sg_dir, sub, store, entry, data, header, report)
                except Exception as error:
                    report['bad'].append(dict(pack=entry['file_id'], member='header', error=f'{type(error).__name__}: {str(error)[:120]}'))
            for key, entry in data_entries.items():
                if key not in seen and data_folder != PACK_ARCHIVE:
                    report['gaps'].append(entry['file_id'])
        report['ok'] = not report['bad']
        return report

    def _verify_one(self, c, sg_dir: str, sub, store, entry: dict, data: bytes, header: dict, report: dict) -> None:
        pack = entry['file_id']
        def bad(member, error):
            report['bad'].append(dict(pack=pack, member=member, error=error))
        key_id = str(header.get('author_key_id') or '')
        if not header.get('signature') or not key_id:
            report['unsigned'].append(pack)
        else:
            try:
                if not self.verify_header_signature(header, c.key_manager.load_public_key(key_id, c.read_key)):
                    bad('header', 'signature does not verify')
            except Exception:
                report['unsigned'].append(pack)                                  # a key this clone cannot load
        if header.get('commit_id') != entry['commit_id']:
            bad('header', 'names another commit than the data pack')
        fields = None
        if store.exists(entry['commit_id']):
            fields = self.commit_fields(sg_dir, entry['commit_id'], c.read_key)
            for f in ('parents', 'tree_id', 'timestamp_ms'):
                if header.get(f) != fields[f]:
                    bad('header', f'{f} differs from the commit object')
        table = self.member_table(header)
        for name in table:
            try:
                member = self.read_member(data, header, name, c.read_key)
            except Exception as error:
                bad(name, str(error)[:120]); continue
            report['members'] += 1
            if fields is None:
                continue
            try:
                if name == 'flat':
                    if member.get('flat') != sub.flatten(fields['tree_id'], c.read_key) or member.get('dirs') != sub.flatten_dirs(fields['tree_id'], c.read_key):
                        bad(name, 'differs from a full flatten of the tree')
                elif name == 'changes':
                    if member.get('changes') != self.changes_of(sg_dir, entry['commit_id'], c.read_key):
                        bad(name, 'differs from the tree diff against the first parent')
                elif name.startswith('folder:'):
                    path   = name[len('folder:'):]
                    flat   = sub.flatten(fields['tree_id'], c.read_key)
                    dirs   = sub.flatten_dirs(fields['tree_id'], c.read_key)
                    expect = self.folder_entries(flat, dirs).get(path)
                    if expect is None or member != expect:
                        bad(name, 'differs from its tree')
            except Exception as error:
                bad(name, f'could not check: {str(error)[:100]}')

    def index_stats(self, directory: str) -> dict:
        c   = self._init_components(directory)
        out = dict(vault_id=str(c.vault_id), folders={}, gaps=self.load_gaps(directory), local_gaps=0)
        for data_folder in (PACK_COMMITS, PACK_SNAPSHOTS, PACK_ARCHIVE):
            data  = self.list_folder(c.vault_id, data_folder)
            index = self.list_index_packs(c.vault_id, self.index_folder_of(data_folder))
            keys  = {(e['commit_id'], e['epoch']) for e in index}
            label = data_folder[len('bare/packs/'):].strip('/')
            out['folders'][label] = dict(data_packs=len(data), index_packs=len(index), index_bytes=sum(e['size'] for e in index),
                                         without_index=[e['name'] for e in data if (e['commit_id'], e['epoch']) not in keys])
        out['local_gaps'] = len(out['gaps'])
        gens = self.load_generations(os.path.join(directory, SG_VAULT_DIR))
        out['generations_known'] = len(gens)
        out['highest_generation'] = max(gens.values()) if gens else 0
        return out
