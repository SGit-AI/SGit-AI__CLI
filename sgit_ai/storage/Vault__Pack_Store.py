"""Vault__Pack_Store — packs kept in place; objects read from them by offset.

A pack clone made with `--pack-store` keeps every data pack it takes under
.sg_vault/bare/packs/<commits|snapshots>/<name> exactly as downloaded, and reads an
object's bytes from the pack by offset instead of extracting 300,000 files into
bare/data/ (the newsroom's clone spent its minutes on those writes; a cloud session's
disk spends longer). Where each object sits is a table in .sg_vault/local/
pack-store.sqlite (pack, object id -> offset, length), built once per pack from the
zip's central directory at intake. The table is derived: lose it and `sgit pack store
rebuild` reads the packs again.

Rules (dev pack 03 §6; architecture note of 26 Oct, §2):
- every member is verified by its content address at intake (nothing unverified is
  ever "here"), and again on every read (a kept pack is a file on disk: a flipped byte
  is caught the first time that object is read, T9);
- a member that is not a stored object under a content address is refused by its
  directory entry and never read; a pack with a refused member is kept for the rest
  but not recorded as absorbed, as the loose store does;
- loose objects (bare/data/) take precedence: a clone's own new objects stay loose
  until pushed, and the pack built by the push then takes them in;
- a pack's file handle is closed before the pack is removed or replaced (Windows
  cannot delete an open file; the handle rule), and reads use pread where the OS has
  it, so the pull's threads share one descriptor without a seek race.
"""
import io
import os
import re
import sqlite3
import struct
import threading
import zipfile
from osbot_utils.type_safe.Type_Safe                 import Type_Safe
from sgit_ai.crypto.Vault__Crypto                    import Vault__Crypto
from sgit_ai.safe_types.Safe_Str__Vault_Path         import Safe_Str__Vault_Path

PACK_STORE_DB      = 'pack-store.sqlite'                     # .sg_vault/local/
PACK_STORE_DIR     = os.path.join('bare', 'packs')           # .sg_vault/bare/packs/<folder>/<name>
PACK_STORE_SCHEMA  = 1
MEMBER_RE          = re.compile(r'^bare/data/(obj-cas-imm-[0-9a-f]{12}(?:[0-9a-f]{20})?)$')
LOCAL_HEADER_FIXED = 30
MAX_OPEN_PACKS     = 16


class Vault__Pack_Store(Type_Safe):
    vault_path : Safe_Str__Vault_Path = None
    crypto     : Vault__Crypto        = None
    conn       : object               = None
    lock       : object               = None
    handles    : dict                                        # pack rel path -> [fd, readers holding it, closing]

    # ------------------------------------------------------------------ where
    def db_path(self) -> str:
        return os.path.join(str(self.vault_path), 'local', PACK_STORE_DB)

    def packs_dir(self) -> str:
        return os.path.join(str(self.vault_path), PACK_STORE_DIR)

    def pack_path(self, rel: str) -> str:
        return os.path.join(self.packs_dir(), *rel.split('/'))

    def enabled(self) -> bool:
        return os.path.isfile(self.db_path())

    def setup(self, create: bool = False):
        """Open the table (creating it with `create`); None when this clone keeps no packs."""
        if self.conn is not None:
            return self
        if not create and not self.enabled():
            return None
        if self.crypto is None:
            self.crypto = Vault__Crypto()
        os.makedirs(os.path.dirname(self.db_path()), mode=0o700, exist_ok=True)
        self.lock = threading.Lock()
        self.conn = sqlite3.connect(self.db_path(), check_same_thread=False)
        with self.conn:
            self.conn.execute('CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)')
            self.conn.execute('CREATE TABLE IF NOT EXISTS packs (rel TEXT PRIMARY KEY, size INTEGER, members INTEGER)')
            self.conn.execute('CREATE TABLE IF NOT EXISTS members (rel TEXT, object_id TEXT, offset INTEGER, length INTEGER, '
                              'PRIMARY KEY (rel, object_id))')                    # every verified member of every kept pack
            self.conn.execute('CREATE INDEX IF NOT EXISTS members_by_object ON members (object_id)')
            row = self.conn.execute("SELECT value FROM meta WHERE key = 'schema'").fetchone()
            if row is None:
                self.conn.execute("INSERT INTO meta (key, value) VALUES ('schema', ?)", (str(PACK_STORE_SCHEMA),))
            elif int(row[0]) != PACK_STORE_SCHEMA:
                raise RuntimeError(f'pack store table of schema {row[0]}; this build reads {PACK_STORE_SCHEMA} '
                                   f'(run `sgit pack store rebuild`)')
        try:
            os.chmod(self.db_path(), 0o600)
        except OSError:
            pass
        return self

    def close(self) -> None:
        """Close every pack handle and the table (the handle rule)."""
        for rel in list(self.handles):
            self._close_handle(rel)
        if self.conn is not None:
            self.conn.close()
            self.conn = None

    # ------------------------------------------------------------------ intake
    def member_offsets(self, data: bytes) -> list:
        """[(object id, data offset, length, why refused)] for every member of a pack's
        bytes, from its central directory and each local header, with the checks the
        loose extraction makes on a directory entry (a stored object under a content
        address, uncompressed, within the pack). Raises on a pack that is not a zip or
        names a member twice."""
        out = []
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            infos = z.infolist()
        if len({i.filename for i in infos}) != len(infos):
            raise ValueError('duplicate member names')
        for info in infos:
            m = MEMBER_RE.fullmatch(info.filename)
            if m is None:
                out.append((info.filename, 0, 0, 'not a store object')); continue
            if info.compress_type != zipfile.ZIP_STORED or info.file_size != info.compress_size:
                out.append((m.group(1), 0, 0, 'not stored uncompressed')); continue
            ho = info.header_offset
            if ho + LOCAL_HEADER_FIXED > len(data) or data[ho:ho + 4] != b'PK\x03\x04':
                out.append((m.group(1), 0, 0, 'local header out of place')); continue
            name_len, extra_len = struct.unpack('<HH', data[ho + 26:ho + 30])
            offset = ho + LOCAL_HEADER_FIXED + name_len + extra_len
            if offset + info.file_size > len(data):
                out.append((m.group(1), 0, 0, 'declares more bytes than the pack holds')); continue
            out.append((m.group(1), offset, info.file_size, ''))
        return out

    def intake(self, data: bytes, rel: str) -> dict:
        """Keep a pack's bytes under bare/packs/<rel> and index every member whose bytes
        hash to its id; returns {extracted (members indexed), refused [...], objects [...]}
        in the loose extraction's shape. A member another kept pack also holds is indexed
        under this pack too (so removing either pack keeps the object)."""
        refused, objects, rows = [], [], []
        try:
            members = self.member_offsets(data)
        except Exception as error:
            return dict(extracted=0, refused=[f'(not a pack: {error})'], objects=[])
        for object_id, offset, length, why in members:
            if why:
                refused.append(object_id); continue
            if not self.crypto.object_id_matches(object_id, data[offset:offset + length]):
                refused.append(object_id); continue
            rows.append((object_id, rel, offset, length))
            objects.append(object_id)
        path = self.pack_path(rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + '.tmp'
        with open(tmp, 'wb') as f:
            f.write(data)
        self._close_handle(rel)                                               # replacing a kept pack: handle first
        os.replace(tmp, path)
        with self.lock, self.conn:
            self.conn.execute('INSERT OR REPLACE INTO packs (rel, size, members) VALUES (?, ?, ?)', (rel, len(data), len(rows)))
            self.conn.execute('DELETE FROM members WHERE rel = ?', (rel,))
            self.conn.executemany('INSERT OR REPLACE INTO members (object_id, rel, offset, length) VALUES (?, ?, ?, ?)', rows)
        return dict(extracted=len(rows), refused=refused, objects=objects)

    def intake_file(self, path: str, rel: str) -> dict:
        with open(path, 'rb') as f:
            return self.intake(f.read(), rel)

    # ------------------------------------------------------------------ reading
    def locate(self, object_id: str):
        with self.lock:
            row = self.conn.execute('SELECT rel, offset, length FROM members WHERE object_id = ? ORDER BY rel LIMIT 1',
                                    (object_id,)).fetchone()                  # any kept pack holding it: all verified
        return tuple(row) if row else None

    def exists(self, object_id: str) -> bool:
        return self.locate(object_id) is not None

    def size_of(self, object_id: str):
        hit = self.locate(object_id)
        return int(hit[2]) if hit else None

    def load(self, object_id: str) -> bytes:
        """The object's bytes from its pack, verified by content address on every read."""
        from sgit_ai.storage.Vault__Object_Store import Vault__Object_Missing_Error, Vault__Object_Corrupt_Error
        hit = self.locate(object_id)
        if hit is None:
            raise Vault__Object_Missing_Error(f'object {object_id} is not in the local store')
        rel, offset, length = hit
        data = self._read(rel, int(offset), int(length))
        if data is None or not self.crypto.object_id_matches(object_id, data):
            raise Vault__Object_Corrupt_Error(f'object {object_id} in pack {rel} does not hash to its id '
                                              f'(the kept pack changed on disk); `sgit pack store rebuild` re-reads it')
        return data

    def _read(self, rel: str, offset: int, length: int):
        held = self._acquire(rel)
        if held is None:
            return None
        try:
            if hasattr(os, 'pread'):
                data = os.pread(held[0], length, offset)
            else:                                                             # Windows: one reader at a time
                with self.lock:
                    os.lseek(held[0], offset, os.SEEK_SET)
                    data = os.read(held[0], length)
        finally:
            self._release(held)
        return data if len(data) == length else None

    def _acquire(self, rel: str):
        """The pack's handle ([fd, readers, closing]), held for one read: a handle in use is
        never evicted nor closed (the first version closed a descriptor under another
        thread's pread when a seventeenth pack was opened: review of 26 Oct, M1). With
        every handle in use the limit is exceeded for the duration of those reads."""
        with self.lock:
            held = self.handles.get(rel)
            if held is not None:
                held[1] += 1
                return held
            try:
                fd = os.open(self.pack_path(rel), os.O_RDONLY | getattr(os, 'O_BINARY', 0))
            except OSError:
                return None
            idle = [r for r, h in self.handles.items() if h[1] == 0]
            while len(self.handles) >= MAX_OPEN_PACKS and idle:
                old = self.handles.pop(idle.pop(0))
                self._close_fd(old[0])
            held = [fd, 1, False]
            self.handles[rel] = held
            return held

    def _release(self, held: list) -> None:
        """Release the very handle a read acquired (never the one now under that name: a
        pack closed and reopened meanwhile has a new one); the last reader of a handle
        that was closed in use closes it (second review of 26 Oct, R7)."""
        with self.lock:
            held[1] -= 1
            if held[1] == 0 and held[2]:
                self._close_fd(held[0])

    def _close_handle(self, rel: str) -> None:
        """Forget a pack's handle (before the pack is removed or replaced): closed now when
        idle, by its last reader otherwise."""
        with self.lock:
            held = self.handles.pop(rel, None)
            if held is None:
                return
            if held[1] == 0:
                self._close_fd(held[0])
            else:
                held[2] = True

    def _close_fd(self, fd: int) -> None:
        try:
            os.close(fd)
        except OSError:
            pass

    # ------------------------------------------------------------------ listing and removal
    def all_object_ids(self) -> list:
        with self.lock:
            return [r[0] for r in self.conn.execute('SELECT DISTINCT object_id FROM members ORDER BY object_id')]

    def object_count(self) -> int:
        with self.lock:
            return int(self.conn.execute('SELECT COUNT(DISTINCT object_id) FROM members').fetchone()[0])

    def packs(self) -> list:
        with self.lock:
            return [dict(rel=r[0], size=int(r[1]), members=int(r[2]))
                    for r in self.conn.execute('SELECT rel, size, members FROM packs ORDER BY rel')]

    def members_of(self, rel: str) -> list:
        with self.lock:
            return [r[0] for r in self.conn.execute('SELECT object_id FROM members WHERE rel = ?', (rel,))]

    def has_pack(self, rel: str) -> bool:
        with self.lock:
            return self.conn.execute('SELECT 1 FROM packs WHERE rel = ?', (rel,)).fetchone() is not None

    def remove_pack(self, rel: str) -> int:
        """Forget a kept pack: handle closed first, its rows dropped, file removed. An object
        another kept pack also holds stays reachable through that pack's rows. Returns the
        rows dropped."""
        self._close_handle(rel)
        with self.lock, self.conn:
            n = self.conn.execute('SELECT COUNT(*) FROM members WHERE rel = ?', (rel,)).fetchone()[0]
            self.conn.execute('DELETE FROM members WHERE rel = ?', (rel,))
            self.conn.execute('DELETE FROM packs WHERE rel = ?', (rel,))
        try:
            os.remove(self.pack_path(rel))
        except OSError:
            pass
        return int(n)

    def rebuild(self) -> dict:
        """The table from the kept pack files alone (a lost or stale table)."""
        with self.lock, self.conn:
            self.conn.execute('DELETE FROM members'); self.conn.execute('DELETE FROM packs')
        packs, objects, refused = 0, 0, []
        base = self.packs_dir()
        for folder in sorted(os.listdir(base)) if os.path.isdir(base) else []:
            sub = os.path.join(base, folder)
            if not os.path.isdir(sub):
                continue
            for name in sorted(os.listdir(sub)):
                if not name.endswith('.zip'):
                    continue
                with open(os.path.join(sub, name), 'rb') as f:
                    r = self.intake(f.read(), f'{folder}/{name}')
                packs += 1; objects += r['extracted']; refused.extend(r['refused'])
        return dict(packs=packs, objects=objects, refused=refused)

    def extract_all(self, obj_store) -> int:
        """Every packed object written loose (verified), then the packs and the table
        removed: the clone is an ordinary one from here."""
        n = 0
        for object_id in self.all_object_ids():
            if not os.path.isfile(obj_store.object_path(object_id)):
                obj_store.store_raw(object_id, self.load(object_id)); n += 1
        for pack in self.packs():
            self.remove_pack(pack['rel'])
        self.close()
        try:
            os.remove(self.db_path())
        except OSError:
            pass
        return n
