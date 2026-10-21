"""Vault__Packs — pack mode: a vault whose objects travel and are stored as zips.

A pack vault (branch-index feature 'packs', normally with 'blob-deflate') keeps no
loose objects under bare/data/ on the host. Instead:

  bare/packs/commits/    <epoch_s>__<commit>__<bytes>.zip   one per push: the commit, its new trees and blobs
  bare/packs/snapshots/  <epoch_s>__<commit>__<bytes>.zip   every object reachable from <commit> (compaction)
  bare/packs/archive/    <epoch_s>__<commit>__<bytes>.zip   commit packs a snapshot absorbed; moved, never deleted

The folders are the index: a clone takes the newest snapshot and everything in
commits/; a pull lists commits/ and takes what it has not absorbed (recorded in
.sg_vault/local/packs_absorbed.json). Packs are deterministic (ZIP_STORED, sorted,
fixed timestamps: the same commit always gives the same bytes), named by commit id so
they never collide, and every member is id-verified before it is written locally.
The local store stays loose: packs are extracted on arrival, so every read path in
the CLI is unchanged. Refs, the branch index, keys and cache objects travel as today.

Routes: the existing batch write/read for small packs, presigned multipart / read-url
for large ones (falling back to the batch where a server has no S3), list and delete.
No server change. Nothing is deleted by this class except a commit pack whose copy
in archive/ has been verified.
"""
import io
import json
import os
import re
import time
import zipfile

from osbot_utils.type_safe.Type_Safe             import Type_Safe
from sgit_ai.core.Vault__Sync__Base              import Vault__Sync__Base
from sgit_ai.crypto.PKI__Crypto                  import PKI__Crypto
from sgit_ai.network.api.Vault__API              import MAX_BATCH_OPS
from sgit_ai.storage.Vault__Commit               import Vault__Commit
from sgit_ai.storage.Vault__Format               import Vault__Format, FEATURE_PACKS, FEATURE_BLOB_DEFLATE
from sgit_ai.storage.Vault__Object_Store         import Vault__Object_Store
from sgit_ai.storage.Vault__Ref_Manager          import Vault__Ref_Manager
from sgit_ai.storage.Vault__Storage              import Vault__Storage, SG_VAULT_DIR
from sgit_ai.storage.Vault__Verified_Write       import Vault__Verified_Write

PACKS_PREFIX       = 'bare/packs/'
PACK_COMMITS       = 'bare/packs/commits/'
PACK_SNAPSHOTS     = 'bare/packs/snapshots/'
PACK_ARCHIVE       = 'bare/packs/archive/'
PACK_NAME_RE       = re.compile(r'^(\d{10})__(obj-cas-imm-[0-9a-f]{12,32})__(\d+)\.zip$')
PACK_BATCH_MAX     = 3 * 1024 * 1024        # raw bytes a pack may carry through one batch op (base64 stays under the 4 MB budget)
PACK_COMPACT_COUNT = 50                      # compact when commits/ holds more packs than this ...
PACK_COMPACT_RATIO = 0.10                    # ... or more bytes than this fraction of the newest snapshot
PACK_ORPHAN_AGE_S  = 24 * 3600               # an unreachable commit pack older than this is archived
ABSORBED_FILE      = 'packs_absorbed.json'
ZIP_EPOCH          = (1980, 1, 1, 0, 0, 0)   # fixed member timestamp: determinism


class Vault__Packs(Vault__Sync__Base):
    tree_memo : dict = None                  # (sg_dir, tree id) -> frozenset of the objects under it; trees are shared
    blob_memo : dict = None                  # (sg_dir, tree id) -> frozenset of the blobs under it; same walk
                                             # between commits, so a history is walked once per distinct tree
    # ------------------------------------------------------------------ names
    def pack_name(self, commit_id: str, nbytes: int, epoch_s: int = None) -> str:
        epoch_s = int(time.time()) if epoch_s is None else int(epoch_s)
        return f'{epoch_s:010d}__{commit_id}__{int(nbytes)}.zip'

    def parse_name(self, name: str) -> dict:
        m = PACK_NAME_RE.match(str(name).rsplit('/', 1)[-1])
        if not m:
            return None
        return dict(name=m.group(0), epoch=int(m.group(1)), commit_id=m.group(2), size=int(m.group(3)))

    # ------------------------------------------------------------------ the flag
    def features_of_directory(self, directory: str) -> list:
        """The branch-index features of a local clone ([] when there is no index yet)."""
        try:
            keys  = self._derive_keys_for_directory(directory)
            index = self._load_index(directory, keys['branch_index_file_id'], keys['read_key_bytes'])
            return Vault__Format().features_of(index) if index is not None else []
        except Exception as error:
            from sgit_ai.storage.Vault__Format import Vault__Client_Too_Old_Error
            if isinstance(error, Vault__Client_Too_Old_Error):
                raise
            return []

    def is_pack_vault(self, directory: str) -> bool:
        return FEATURE_PACKS in self.features_of_directory(directory)

    def _load_index(self, directory: str, index_id: str, read_key: bytes):
        from sgit_ai.storage.Vault__Branch_Manager import Vault__Branch_Manager
        from sgit_ai.crypto.Vault__Key_Manager     import Vault__Key_Manager
        sg_dir  = os.path.join(directory, SG_VAULT_DIR)
        storage = Vault__Storage()
        if not index_id or not os.path.isfile(storage.index_path(directory, index_id)):
            return None
        bm = Vault__Branch_Manager(vault_path=sg_dir, crypto=self.crypto,
                                   key_manager=Vault__Key_Manager(vault_path=sg_dir, crypto=self.crypto, pki=PKI__Crypto()),
                                   ref_manager=Vault__Ref_Manager(vault_path=sg_dir, crypto=self.crypto),
                                   storage=storage)
        return bm.load_branch_index(directory, index_id, read_key)

    def index_is_pack_vault(self, index) -> bool:
        return Vault__Format().has_feature(index, FEATURE_PACKS)

    def pack_features(self, deflate: bool = True) -> list:
        return [FEATURE_PACKS, FEATURE_BLOB_DEFLATE] if deflate else [FEATURE_PACKS]

    # ------------------------------------------------------------------ object sets
    def _vault_commit(self, sg_dir: str) -> Vault__Commit:
        store = Vault__Object_Store(vault_path=sg_dir, crypto=self.crypto)
        return Vault__Commit(crypto=self.crypto, pki=PKI__Crypto(), object_store=store,
                             ref_manager=Vault__Ref_Manager(vault_path=sg_dir, crypto=self.crypto))

    def objects_of_commit(self, sg_dir: str, commit_id: str, read_key: bytes) -> set:
        """The commit object plus every tree and blob its root tree reaches (local store).
        Memoised per tree: the comms vault's 1,227 commits share most of their 16k
        trees, and a snapshot that walked every commit's tree afresh took minutes."""
        objects = {commit_id}
        try:
            commit = self._vault_commit(sg_dir).load_commit(commit_id, read_key)
        except Exception:
            return objects
        if commit.tree_id:
            objects |= self.tree_objects(sg_dir, str(commit.tree_id), read_key)
        return objects

    def tree_objects(self, sg_dir: str, tree_id: str, read_key: bytes) -> frozenset:
        """Every object under a tree (the tree itself, its blobs, its sub-trees recursively),
        computed once per distinct tree id and kept on this instance."""
        if self.tree_memo is None:
            self.tree_memo, self.blob_memo = {}, {}
        key = (sg_dir, tree_id)
        if key in self.tree_memo:
            return self.tree_memo[key]
        vc      = self._vault_commit(sg_dir)
        objects = {tree_id}
        blobs   = set()
        try:
            tree = vc.load_tree(tree_id, read_key)
        except Exception:
            tree = None                                              # fail-soft per object
        for entry in (tree.entries if tree is not None else []) or []:
            if entry.blob_id:
                objects.add(str(entry.blob_id)); blobs.add(str(entry.blob_id))
            elif entry.tree_id:
                sub = str(entry.tree_id)
                objects |= self.tree_objects(sg_dir, sub, read_key)
                blobs   |= self.blob_memo[(sg_dir, sub)]
        self.tree_memo[key] = frozenset(objects)
        self.blob_memo[key] = frozenset(blobs)
        return self.tree_memo[key]

    def tree_blobs(self, sg_dir: str, tree_id: str, read_key: bytes) -> frozenset:
        self.tree_objects(sg_dir, tree_id, read_key)
        return self.blob_memo[(sg_dir, tree_id)]

    def parents_of(self, sg_dir: str, commit_id: str, read_key: bytes) -> list:
        try:
            commit = self._vault_commit(sg_dir).load_commit(commit_id, read_key)
            return [str(p) for p in (commit.parents or []) if str(p)]
        except Exception:
            return []

    def objects_introduced(self, sg_dir: str, commit_id: str, read_key: bytes) -> list:
        """What this commit added: the commit, and every tree and blob of its tree that
        its first parent's tree does not hold at the same path (a pruned diff, as git
        does it: a folder whose id is unchanged is not opened, so the cost follows the
        change, not the vault). A merge's second parent is already on the host: this
        clone pulled it from there. Deterministic for a given commit, so a pack can
        always be rebuilt."""
        try:
            commit = self._vault_commit(sg_dir).load_commit(commit_id, read_key)
        except Exception:
            return [commit_id]
        parents = [str(p) for p in (commit.parents or []) if str(p)]
        if not parents:
            return sorted(self.objects_of_commit(sg_dir, commit_id, read_key))
        try:
            parent_tree = str(self._vault_commit(sg_dir).load_commit(parents[0], read_key).tree_id)
        except Exception:
            parent_tree = None
        return sorted({commit_id} | self.tree_diff(sg_dir, str(commit.tree_id), parent_tree, read_key))

    def tree_diff(self, sg_dir: str, new_tree_id: str, old_tree_id: str, read_key: bytes) -> set:
        """Objects under new_tree_id that old_tree_id does not hold at the same path.
        Entries are matched by their deterministic encrypted name (no decryption)."""
        if not new_tree_id or new_tree_id == old_tree_id:
            return set()
        if not old_tree_id:
            return set(self.tree_objects(sg_dir, new_tree_id, read_key))
        vc = self._vault_commit(sg_dir)
        try:
            new_tree = vc.load_tree(new_tree_id, read_key)
        except Exception:
            return {new_tree_id}
        try:
            old_entries = {str(e.name_enc): e for e in (vc.load_tree(old_tree_id, read_key).entries or [])}
        except Exception:
            old_entries = {}
        objects = {new_tree_id}
        for entry in (new_tree.entries or []):
            old = old_entries.get(str(entry.name_enc))
            if entry.blob_id:
                if old is None or str(old.blob_id or '') != str(entry.blob_id):
                    objects.add(str(entry.blob_id))
            elif entry.tree_id:
                objects |= self.tree_diff(sg_dir, str(entry.tree_id), str(old.tree_id) if old is not None and old.tree_id else None, read_key)
        return objects

    def reachable_objects(self, sg_dir: str, head_commit_id: str, read_key: bytes) -> list:
        """Every object reachable from a head: the commits along every parent, their
        trees and blobs (a snapshot)."""
        seen, objects, queue = set(), set(), [head_commit_id]
        while queue:
            cid = queue.pop()
            if not cid or cid in seen:
                continue
            seen.add(cid)
            objects |= self.objects_of_commit(sg_dir, cid, read_key)
            queue.extend(self.parents_of(sg_dir, cid, read_key))
        return sorted(objects)

    def reachable_commits(self, sg_dir: str, head_commit_id: str, read_key: bytes) -> set:
        seen, queue = set(), [head_commit_id]
        while queue:
            cid = queue.pop()
            if not cid or cid in seen:
                continue
            seen.add(cid)
            queue.extend(self.parents_of(sg_dir, cid, read_key))
        return seen

    # ------------------------------------------------------------------ zip bytes
    def write_pack(self, sg_dir: str, object_ids: list, out_path: str) -> int:
        """A deterministic ZIP_STORED zip of the objects (members bare/data/<id>)."""
        store = Vault__Object_Store(vault_path=sg_dir, crypto=self.crypto)
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with zipfile.ZipFile(out_path, 'w', compression=zipfile.ZIP_STORED, allowZip64=True) as pack:
            for object_id in sorted(set(object_ids)):
                if not store.exists(object_id):
                    continue
                info = zipfile.ZipInfo(f'bare/data/{object_id}', date_time=ZIP_EPOCH)
                info.compress_type = zipfile.ZIP_STORED
                pack.writestr(info, store.load(object_id))
        return os.path.getsize(out_path)

    def build_commit_pack(self, sg_dir: str, commit_id: str, read_key: bytes, work_dir: str) -> tuple:
        """(path, name) of the pack for one commit; the name carries its size."""
        tmp  = os.path.join(work_dir, f'commit-{commit_id}.zip')
        size = self.write_pack(sg_dir, self.objects_introduced(sg_dir, commit_id, read_key), tmp)
        return tmp, self.pack_name(commit_id, size)

    def build_snapshot_pack(self, sg_dir: str, head_commit_id: str, read_key: bytes, work_dir: str) -> tuple:
        tmp  = os.path.join(work_dir, f'snapshot-{head_commit_id}.zip')
        size = self.write_pack(sg_dir, self.reachable_objects(sg_dir, head_commit_id, read_key), tmp)
        return tmp, self.pack_name(head_commit_id, size)

    def members_of(self, data: bytes) -> list:
        with zipfile.ZipFile(io.BytesIO(data)) as pack:
            return [n.rsplit('/', 1)[-1] for n in pack.namelist() if n.startswith('bare/data/')]

    def extract_pack(self, data: bytes, sg_dir: str, read_key: bytes = None) -> dict:
        """Write every member into the loose store, id-verified; a corrupt member is
        refused and reported, never written."""
        writer    = Vault__Verified_Write(crypto=self.crypto)
        extracted = 0
        refused   = []
        try:
            opened = zipfile.ZipFile(io.BytesIO(data))
        except zipfile.BadZipFile as error:                                  # not a zip: nothing is written
            return dict(extracted=0, refused=[f'(not a zip: {error})'])
        with opened as pack:
            for member in sorted(pack.namelist()):
                if not member.startswith('bare/data/'):
                    refused.append(member)
                    continue
                if writer.save(sg_dir, member, pack.read(member), read_key=read_key) == writer.REFUSED:
                    refused.append(member)
                else:
                    extracted += 1
        return dict(extracted=extracted, refused=refused)

    # ------------------------------------------------------------------ the host
    def upload_pack(self, vault_id: str, write_key: str, file_id: str, path: str, on_progress=None) -> None:
        """A small pack through the batch route; a large one by presigned multipart,
        or the batch when the server has no S3 (no Lambda limit there)."""
        import base64
        from sgit_ai.core.actions.push.Vault__Batch import Vault__Batch
        batch = Vault__Batch(crypto=self.crypto, api=self.api)
        with open(path, 'rb') as f:
            data = f.read()
        if len(data) > PACK_BATCH_MAX and batch._upload_large(vault_id, file_id, data, write_key, on_progress):
            return
        batch.execute_batch(vault_id, write_key,
                            [dict(op='write', file_id=file_id, data=base64.b64encode(data).decode('ascii'))])

    def list_folder(self, vault_id: str, prefix: str) -> list:
        """Pack entries under a folder, oldest first: [{name, epoch, commit_id, size, file_id}]."""
        names = self.api.list_files(vault_id, prefix) or []
        out   = []
        for fid in names:
            fid  = str(fid)
            info = self.parse_name(fid)
            if info and fid.startswith(prefix):
                info['file_id'] = fid
                out.append(info)
        return sorted(out, key=lambda e: (e['epoch'], e['name']))

    def fetch_pack(self, vault_id: str, entry: dict) -> bytes:
        fid  = entry['file_id']
        if entry['size'] > PACK_BATCH_MAX:
            data = self.api.read_large(vault_id, fid, size=entry['size'])
        else:
            data = (self.api.batch_read(vault_id, [fid]) or {}).get(fid)
        if data is None or len(data) != entry['size']:
            raise RuntimeError(f'pack {entry["name"]}: expected {entry["size"]} bytes, got '
                               f'{"nothing" if data is None else len(data)}')
        return data

    def fetch_packs(self, vault_id: str, entries: list) -> dict:
        """{name: bytes}; small packs grouped into batch reads of up to MAX_BATCH_OPS."""
        out   = {}
        small = [e for e in entries if e['size'] <= PACK_BATCH_MAX]
        large = [e for e in entries if e['size'] >  PACK_BATCH_MAX]
        for i in range(0, len(small), MAX_BATCH_OPS):
            chunk  = small[i:i + MAX_BATCH_OPS]
            budget = sum(e['size'] for e in chunk)
            if budget > PACK_BATCH_MAX:                                   # keep each batch under the response budget
                for e in chunk:
                    out[e['name']] = self.fetch_pack(vault_id, e)
                continue
            got = self.api.batch_read(vault_id, [e['file_id'] for e in chunk]) or {}
            for e in chunk:
                data = got.get(e['file_id'])
                if data is None or len(data) != e['size']:
                    raise RuntimeError(f'pack {e["name"]}: expected {e["size"]} bytes')
                out[e['name']] = data
        for e in large:
            out[e['name']] = self.fetch_pack(vault_id, e)
        return out

    # ------------------------------------------------------------------ absorbed
    def _absorbed_path(self, directory: str) -> str:
        return os.path.join(Vault__Storage().local_dir(directory), ABSORBED_FILE)

    def load_absorbed(self, directory: str) -> set:
        try:
            with open(self._absorbed_path(directory)) as f:
                return set(json.load(f).get('packs', []))
        except Exception:
            return set()

    def record_absorbed(self, directory: str, names) -> None:
        path = self._absorbed_path(directory)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        current = self.load_absorbed(directory) | set(names)
        with open(path, 'w') as f:
            json.dump(dict(packs=sorted(current)), f, indent=1)

    # ------------------------------------------------------------------ down and up
    def sync_down(self, directory: str, vault_id: str, read_key: bytes, on_progress=None) -> dict:
        """Bring the packs this clone lacks into its loose store: the newest snapshot
        when this clone has not absorbed it (a fresh clone, or a clone so far behind
        that compaction archived the commit packs it needed), then every commit pack
        not yet absorbed. A snapshot whose head commit is already local is recorded
        as absorbed without a download. Returns counts and the requests made."""
        _p       = on_progress or (lambda *a, **k: None)
        sg_dir   = os.path.join(directory, SG_VAULT_DIR)
        absorbed = self.load_absorbed(directory)
        fetched, extracted, refused, requests = [], 0, [], 0
        entries  = []
        snapshots = self.list_folder(vault_id, PACK_SNAPSHOTS); requests += 1
        if snapshots and snapshots[-1]['name'] not in absorbed:
            newest = snapshots[-1]
            store  = Vault__Object_Store(vault_path=sg_dir, crypto=self.crypto)
            if store.exists(newest['commit_id']) and self.load_absorbed(directory):   # its history is here already
                self.record_absorbed(directory, [newest['name']])
            else:
                entries.append(newest)
        commits = self.list_folder(vault_id, PACK_COMMITS); requests += 1
        entries.extend(e for e in commits if e['name'] not in absorbed)
        if not entries:
            return dict(packs=0, extracted=0, refused=[], requests=requests, names=[])
        _p('step', 'Fetching packs', f'{len(entries)} pack(s), {sum(e["size"] for e in entries) / 1e6:.1f} MB')
        got = self.fetch_packs(vault_id, entries)
        requests += sum(1 for e in entries if e['size'] > PACK_BATCH_MAX) + max(1, -(-len([e for e in entries if e['size'] <= PACK_BATCH_MAX]) // MAX_BATCH_OPS))
        for e in entries:
            result = self.extract_pack(got[e['name']], sg_dir, read_key)
            extracted += result['extracted']
            if result['refused']:
                refused.extend(result['refused'])
                _p('warning', 'Pack had members that failed the integrity check', f'{e["name"]}: {len(result["refused"])}')
            else:
                fetched.append(e['name'])
        self.record_absorbed(directory, fetched)
        _p('step', 'Packs extracted', f'{len(fetched)} pack(s), {extracted} object(s)')
        return dict(packs=len(fetched), extracted=extracted, refused=refused, requests=requests, names=fetched)

    def push_packs(self, directory: str, vault_id: str, write_key: str, read_key: bytes,
                   commit_ids: list, on_progress=None) -> list:
        """One pack per commit (oldest first), uploaded to commits/ and recorded as absorbed."""
        _p       = on_progress or (lambda *a, **k: None)
        sg_dir   = os.path.join(directory, SG_VAULT_DIR)
        work_dir = os.path.join(sg_dir, 'work', 'packs')
        os.makedirs(work_dir, exist_ok=True)
        names = []
        for cid in commit_ids:
            path, name = self.build_commit_pack(sg_dir, cid, read_key, work_dir)
            _p('step', 'Uploading pack', f'{name} ({os.path.getsize(path) / 1e6:.2f} MB)')
            self.upload_pack(vault_id, write_key, PACK_COMMITS + name, path, on_progress)
            os.remove(path)
            names.append(name)
        self.record_absorbed(directory, names)
        return names

    def push_snapshot(self, directory: str, vault_id: str, write_key: str, read_key: bytes,
                      head_commit_id: str, on_progress=None) -> str:
        _p       = on_progress or (lambda *a, **k: None)
        sg_dir   = os.path.join(directory, SG_VAULT_DIR)
        work_dir = os.path.join(sg_dir, 'work', 'packs')
        os.makedirs(work_dir, exist_ok=True)
        path, name = self.build_snapshot_pack(sg_dir, head_commit_id, read_key, work_dir)
        _p('step', 'Uploading snapshot pack', f'{name} ({os.path.getsize(path) / 1e6:.2f} MB)')
        self.upload_pack(vault_id, write_key, PACK_SNAPSHOTS + name, path, on_progress)
        os.remove(path)
        self.record_absorbed(directory, [name])
        return name
