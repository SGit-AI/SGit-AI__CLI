"""Vault__Pack_Ranges — a scoped clone or pull of a pack vault fetches what it holds by
byte ranges from the packs on the host, never the packs whole (dev pack 03 §5, Phase 2).

Where an object sits: each pack's central directory, read once by two ranged reads
(the tail that holds the end-of-central-directory record, then the directory itself)
and kept under .sg_vault/local/index/cd/<folder>/<name>.json; a pack this client wrote
is in path order (Vault__Packs.path_order), so one folder's objects are one range.

What a scoped clone holds, exactly as the loose scoped clone does: the commits of the
head's history (to the depth asked), the trees on the spine down to each held folder
and the held folders' trees, for every commit, and their blobs. The commit walk and the
scoped tree walk (Vault__Scoped_Tree.walk_fetch) run level by level; each level's
missing objects are located, merged into ranges (a gap under RANGE_GAP joins two),
fetched with Vault__API.read_range and written through Vault__Verified_Write: a range
is a plan, the content address is the proof. A host without the presigned route
raises Vault__Ranges_Unavailable and the caller takes the packs whole, as before.
"""
import json
import os
import struct
from sgit_ai.core.actions.pack.Vault__Packs         import Vault__Packs, PACK_COMMITS, PACK_SNAPSHOTS
from sgit_ai.storage.Vault__Object_Store           import Vault__Object_Store
from sgit_ai.storage.Vault__Storage                import SG_VAULT_DIR
from sgit_ai.storage.Vault__Verified_Write         import Vault__Verified_Write

EOCD_TAIL          = 4096                                    # the end of a zip: the EOCD record (and a small directory)
RANGE_GAP          = 64 * 1024                               # members closer than this travel in one range
RANGE_MAX          = 32 * 1024 * 1024                        # one ranged read at most
LOCAL_HEADER_FIXED = 30
LOCAL_SLACK        = 64                                      # a local header's extra field, at most (zip64: 20 bytes)
CD_DIR             = 'cd'                                    # .sg_vault/local/index/cd/


class Vault__Ranges_Unavailable(RuntimeError):
    """The host has no ranged read (no presigned route): take the packs whole."""


class Vault__Pack_Ranges(Vault__Packs):
    last_range_requests : int = 0
    last_range_bytes    : int = 0
    refused_packs       : list                                   # pack names a ranged member of which was refused

    # ------------------------------------------------------------------ the central directory of a pack
    def _cd_path(self, directory: str, entry: dict) -> str:
        folder = entry['file_id'][len('bare/packs/'):].split('/')[0]
        return os.path.join(directory, SG_VAULT_DIR, 'local', 'index', CD_DIR, folder, entry['name'] + '.json')

    def _range(self, vault_id: str, entry: dict, start: int, end: int) -> bytes:
        end = min(int(end), int(entry['size']) - 1)
        try:
            data = self.api.read_range(vault_id, entry['file_id'], int(start), end)
        except RuntimeError as error:
            if 'ranged reads unavailable' in str(error) or 'presigned_not_available' in str(error):
                raise Vault__Ranges_Unavailable(str(error)) from error
            raise
        self.last_range_requests += 1
        self.last_range_bytes    += len(data)
        if len(data) != end - int(start) + 1:
            raise RuntimeError(f'pack {entry["name"]}: range {start}-{end} came back {len(data)} bytes')
        return data

    def central_directory(self, directory: str, vault_id: str, entry: dict) -> dict:
        """{object id: [local header offset, name length, data length]} of a pack on the
        host, by two ranged reads (cached locally). Only stored members under a content
        address are listed, as the extraction's directory rule says."""
        path = self._cd_path(directory, entry)
        try:
            with open(path) as f:
                saved = json.load(f)
            if saved.get('size') == entry['size']:
                return {k: tuple(v) for k, v in saved['members'].items()}
        except (OSError, ValueError, KeyError, TypeError):
            pass
        size       = int(entry['size'])
        tail_start = max(0, size - EOCD_TAIL)
        tail       = self._range(vault_id, entry, tail_start, size - 1)
        cd_offset, cd_size = self._locate_directory(tail, tail_start, vault_id, entry)
        if cd_offset >= tail_start:
            cd = tail[cd_offset - tail_start: cd_offset - tail_start + cd_size]
        elif cd_offset + cd_size > tail_start:                                 # partly in the tail: read the rest only
            cd = self._range(vault_id, entry, cd_offset, tail_start - 1) + tail[:cd_offset + cd_size - tail_start]
        else:
            cd = self._range(vault_id, entry, cd_offset, cd_offset + cd_size - 1)
        members = self._parse_directory(cd, size)
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path + '.tmp', 'w') as f:
                json.dump(dict(size=size, members={k: list(v) for k, v in members.items()}), f, separators=(',', ':'))
            os.replace(path + '.tmp', path)
        except OSError:
            pass
        return members

    def _locate_directory(self, tail: bytes, tail_start: int, vault_id: str, entry: dict) -> tuple:
        """(offset, size) of the central directory from the end-of-central-directory
        record (zip64 when the plain one says 0xFFFFFFFF)."""
        i = tail.rfind(b'PK\x05\x06')
        if i < 0:
            raise ValueError(f'pack {entry["name"]}: no end-of-central-directory record')
        cd_size, cd_offset = struct.unpack('<II', tail[i + 12:i + 20])
        if cd_size != 0xFFFFFFFF and cd_offset != 0xFFFFFFFF:
            return cd_offset, cd_size
        j = tail.rfind(b'PK\x06\x07', 0, i)                                   # the zip64 locator
        if j < 0:
            raise ValueError(f'pack {entry["name"]}: zip64 without a locator')
        z64_offset = struct.unpack('<Q', tail[j + 8:j + 16])[0]
        if z64_offset >= tail_start:
            rec = tail[z64_offset - tail_start: z64_offset - tail_start + 56]
        else:
            rec = self._range(vault_id, entry, z64_offset, z64_offset + 55)
        if rec[:4] != b'PK\x06\x06':
            raise ValueError(f'pack {entry["name"]}: bad zip64 end record')
        cd_size, cd_offset = struct.unpack('<QQ', rec[40:56])
        return cd_offset, cd_size

    def _parse_directory(self, cd: bytes, pack_size: int) -> dict:
        from sgit_ai.storage.Vault__Pack_Store import MEMBER_RE
        out, pos = {}, 0
        while pos + 46 <= len(cd) and cd[pos:pos + 4] == b'PK\x01\x02':
            method = struct.unpack('<H', cd[pos + 10:pos + 12])[0]
            csize, usize = struct.unpack('<II', cd[pos + 20:pos + 28])
            nlen, xlen, clen = struct.unpack('<HHH', cd[pos + 28:pos + 34])
            lho   = struct.unpack('<I', cd[pos + 42:pos + 46])[0]
            name  = cd[pos + 46:pos + 46 + nlen].decode('utf-8', 'replace')
            extra = cd[pos + 46 + nlen:pos + 46 + nlen + xlen]
            if 0xFFFFFFFF in (csize, usize, lho):                              # zip64 extra: the wide fields, in order
                k = 0
                while k + 4 <= len(extra):
                    hid, hlen = struct.unpack('<HH', extra[k:k + 4])
                    if hid == 0x0001:
                        body, b = extra[k + 4:k + 4 + hlen], 0
                        if usize == 0xFFFFFFFF: usize = struct.unpack('<Q', body[b:b + 8])[0]; b += 8
                        if csize == 0xFFFFFFFF: csize = struct.unpack('<Q', body[b:b + 8])[0]; b += 8
                        if lho   == 0xFFFFFFFF: lho   = struct.unpack('<Q', body[b:b + 8])[0]; b += 8
                        break
                    k += 4 + hlen
            pos += 46 + nlen + xlen + clen
            m = MEMBER_RE.fullmatch(name)
            if m is None or method != 0 or csize != usize or lho + LOCAL_HEADER_FIXED + nlen + usize > pack_size:
                continue
            out[m.group(1)] = (lho, nlen, usize)
        return out

    # ------------------------------------------------------------------ locating and fetching
    def locate(self, directory: str, vault_id: str, packs: list, object_ids, located: dict, read_cds: set) -> list:
        """Fill `located` ({object id: (entry, lho, nlen, len)}) for the ids asked, reading
        the central directory of one more pack at a time, newest first, until every id
        is found or every pack was read; returns the ids still unlocated."""
        todo = [o for o in object_ids if o not in located]
        for entry in packs:
            if not todo:
                break
            if entry['name'] not in read_cds:
                members = self.central_directory(directory, vault_id, entry)
                read_cds.add(entry['name'])
                for oid, row in members.items():
                    located.setdefault(oid, (entry, row[0], row[1], row[2]))
            todo = [o for o in todo if o not in located]
        return todo

    def fetch_located(self, directory: str, vault_id: str, read_key: bytes, located: dict, object_ids, _p=None) -> dict:
        """The objects named, by merged ranges per pack, verified by content address before
        they are written loose. Returns {'written': [...], 'refused': [...]}."""
        _p      = _p or (lambda *a, **k: None)
        sg_dir  = os.path.join(directory, SG_VAULT_DIR)
        writer  = Vault__Verified_Write(crypto=self.crypto)
        store   = Vault__Object_Store(vault_path=sg_dir, crypto=self.crypto)
        by_pack = {}
        for oid in object_ids:
            if oid in located and not store.exists(oid):
                entry, lho, nlen, length = located[oid]
                by_pack.setdefault(entry['name'], (entry, []))[1].append((lho, nlen, length, oid))
        written, refused = [], []
        for name, (entry, items) in by_pack.items():
            items.sort()
            gap = min(RANGE_GAP, int(entry['size']) // 16)                      # a small pack still reads selectively
            ranges, cur = [], None
            for lho, nlen, length, oid in items:
                start, end = lho, lho + LOCAL_HEADER_FIXED + nlen + LOCAL_SLACK + length - 1
                if cur is not None and start - cur[1] <= gap and end - cur[0] < RANGE_MAX:
                    cur[1] = max(cur[1], end); cur[2].append((lho, nlen, length, oid))
                else:
                    cur = [start, end, [(lho, nlen, length, oid)]]; ranges.append(cur)
            for start, end, members in ranges:
                data = self._range(vault_id, entry, start, end)
                for lho, nlen, length, oid in members:
                    at = lho - start
                    if data[at:at + 4] != b'PK\x03\x04':
                        refused.append(oid); continue
                    name_len, extra_len = struct.unpack('<HH', data[at + 26:at + 30])
                    body = data[at + LOCAL_HEADER_FIXED + name_len + extra_len: at + LOCAL_HEADER_FIXED + name_len + extra_len + length]
                    if len(body) != length or writer.save(sg_dir, f'bare/data/{oid}', body, read_key=read_key) == writer.REFUSED:
                        refused.append(oid); continue
                    written.append(oid)
            if any(oid in refused for _, _, _, oid in items) and name not in self.refused_packs:
                self.refused_packs.append(name)                                 # never recorded as absorbed (F6)
        if refused:
            _p('warning', 'Ranged members failed the integrity check', f'{len(refused)} object(s) refused, not written')
        return dict(written=written, refused=refused)

    def _commit_or_none(self, vc, store, commit_id: str, read_key: bytes):
        if not store.exists(commit_id):
            return None
        try:
            return vc.load_commit(commit_id, read_key)
        except Exception:
            return None                                                       # refused or unreadable: not walked through

    # ------------------------------------------------------------------ what a scoped clone holds
    def scoped_fetch(self, directory: str, vault_id: str, read_key: bytes, scope, head: str, depth: int = 0,
                     on_progress=None, boundaries=None) -> dict:
        """The commits of `head`'s history (to `depth` levels), every commit's spine and
        held-folder trees for `scope`, and their blobs, by ranges; the commit walk stops at
        commits this clone already holds with their trees (a pull). Returns the sync_down
        shape: {packs, extracted, refused, requests, names, objects}."""
        from sgit_ai.storage.Vault__Scoped_Tree import Vault__Scoped_Tree
        _p       = on_progress or (lambda *a, **k: None)
        sg_dir   = os.path.join(directory, SG_VAULT_DIR)
        store    = Vault__Object_Store(vault_path=sg_dir, crypto=self.crypto)
        absorbed = set(self.load_absorbed(directory))
        packs    = ([e for e in reversed(self.list_folder(vault_id, PACK_COMMITS)) if e['name'] not in absorbed]
                    + [e for e in reversed(self.list_folder(vault_id, PACK_SNAPSHOTS))])
        requests = 2
        self.last_range_requests, self.last_range_bytes = 0, 0
        located, read_cds, objects, refused = {}, set(), [], []
        bounds   = set(boundaries or [])

        def bring(ids, what):
            ids = [i for i in ids if i and not store.exists(i)]
            if not ids:
                return
            missing = self.locate(directory, vault_id, packs, ids, located, read_cds)
            r = self.fetch_located(directory, vault_id, read_key, located, [i for i in ids if i not in missing], _p)
            objects.extend(r['written']); refused.extend(r['refused'])
            _p('scan', f'Fetching {what} by ranges', f'{len(objects)} object(s), {self.last_range_bytes / 1e6:.1f} MB')

        # 1. the commits, level by level, through what is new to this clone
        vc      = self._vault_commit(sg_dir)
        level   = [head]
        seen    = set()
        roots   = []
        level_n = 0
        while level and (not depth or level_n < depth):
            level = [c for c in level if c and c not in seen]
            if not level:
                break
            seen.update(level)
            new = [c for c in level if not store.exists(c)]
            bring(new, 'commits')
            next_level = []
            for cid in level:
                commit = self._commit_or_none(vc, store, cid, read_key)
                if commit is None:
                    continue
                tree_id = str(commit.tree_id or '')
                if tree_id:
                    roots.append(tree_id)
                if cid in bounds:
                    continue
                for pid in (list(commit.parents) if commit.parents else []):
                    pid = str(pid)
                    if cid in new or not store.exists(pid):               # new to this clone: walk on; held: stop there
                        next_level.append(pid)
            level = next_level
            level_n += 1
        # 2. the trees on the spine and in the held folders, then their blobs
        scoped = Vault__Scoped_Tree(crypto=self.crypto, obj_store=store).setup()
        walked = scoped.walk_fetch(roots, read_key, scope, on_batch_missing=lambda ids: bring(ids, 'trees'))
        bring(sorted(walked['small_blobs'] | walked['large_blobs']), 'blobs')
        names = sorted(read_cds)
        self.record_absorbed(directory, [n for n in names if n not in self.refused_packs                   # a pack with a refused
                                         and any(e['name'] == n for e in packs if e['file_id'].startswith(PACK_COMMITS))])   # member is read again
        requests += self.last_range_requests
        _p('step', 'Scoped fetch by ranges', f'{len(objects)} object(s) in {self.last_range_requests} ranged read(s), '
                                              f'{self.last_range_bytes / 1e6:.1f} MB of {sum(e["size"] for e in packs) / 1e6:.1f} MB packed')
        return dict(packs=len(names), extracted=len(objects), refused=refused, requests=requests, names=names, objects=objects)
