"""Vault__API__Static — read-only vault transport over plain GET / open().

Productionised from scripts/spike__static_vault_transport.py (P1 of the
static-publishing pack). A sibling of Vault__API, injected at the CLI
boundary, so every action's call sites are unchanged.

Byte source is decided by the shape of base_url:
    /abs/path or file://…   ->  open()   (local or networked folder)
    http(s)://…             ->  GET      (any static file server)

The on-host layout is sniffed once on the first successful read and then
sticky — a published host may expose objects at the live-API path
(api/vault/read/{vault_id}/{file_id}) or flat ({file_id} at the root).

F5 (tabletop 11): only an HTTP 404 — or a missing local file — means an
object is ABSENT (None). A connection-level failure (refused/reset/timeout/
DNS) raises Vault__Static_Transport_Error naming the host: a dead host must
never diagnose as an empty vault, which sends operators toward re-keying
instead of restarting a server.

I2 support: with record_requests=True every URL/path touched is appended to
recorded_requests, so QA can assert no request ever carried key material —
proving the behaviour, not the absence of a line.
"""
import os
import socket
from   urllib.error    import HTTPError, URLError
from   urllib.parse    import quote
from   urllib.request  import urlopen

from   sgit_ai.network.api.Vault__API                import Vault__API
from   sgit_ai.network.api.Vault__Transport_Errors   import (Vault__Read_Only_Transport_Error,
                                                             Vault__Static_Transport_Error)
from   sgit_ai.safe_types.Enum__Published_Layout     import Enum__Published_Layout

HTTP_TIMEOUT       = 30
HTTP_WORKERS       = 8      # bounded fan-out for GET hosts
LOCAL_WORKERS      = 1      # parallelism on open() is pure overhead

LAYOUT_TEMPLATES   = { Enum__Published_Layout.API_PATH : 'api/vault/read/{vid}/{fid}',
                       Enum__Published_Layout.FLAT     : '{fid}'                      }


class Vault__API__Static(Vault__API):
    layout            : Enum__Published_Layout = None    # sticky after first success
    record_requests   : bool                   = False
    recorded_requests : list

    def setup(self):
        if not self.base_url:
            raise ValueError('Vault__API__Static needs an explicit base_url '
                             '(a folder path or an http(s) URL)')
        return self

    # --- source shape -------------------------------------------------------

    def is_local(self) -> bool:
        base = str(self.base_url or '')
        return not (base.startswith('http://') or base.startswith('https://'))

    def _root(self) -> str:
        return str(self.base_url or '').replace('file://', '').rstrip('/')

    def _candidate_layouts(self) -> list:
        if self.layout is not None:
            return [self.layout]
        return [Enum__Published_Layout.API_PATH, Enum__Published_Layout.FLAT]

    def _location(self, layout, vault_id: str, file_id: str) -> str:
        rel = LAYOUT_TEMPLATES[layout].format(vid=vault_id, fid=file_id)
        if self.is_local():
            return os.path.join(self._root(), rel)
        safe = '/'.join(quote(part, safe='') for part in rel.split('/'))
        return f'{self._root()}/{safe}'

    def _record(self, location: str) -> None:
        if self.record_requests:
            self.recorded_requests.append(location)

    # --- the four methods that carry the read path --------------------------

    def read(self, vault_id: str, file_id: str) -> bytes:
        """One GET / open(). None means ABSENT (HTTP 404 / missing file only);
        an unreachable host raises, naming the host (F5)."""
        for layout in self._candidate_layouts():
            location = self._location(layout, vault_id, file_id)
            data     = self._fetch(location)
            if data is not None:
                self.layout = layout                     # remember what works
                return data
        return None

    def _fetch(self, location: str) -> bytes:
        """Bytes at location, or None when absent. Raises on a dead host."""
        self._record(location)
        if self.is_local():
            if not os.path.isfile(location):
                return None
            with open(location, 'rb') as f:
                return f.read()
        try:
            with urlopen(location, timeout=HTTP_TIMEOUT,
                         context=self._ssl_context(location)) as response:
                return response.read()
        except HTTPError as e:
            if e.code == 404:
                return None                              # the ONLY 'absent' answer
            raise RuntimeError(f'static host returned HTTP {e.code} {e.reason} '
                               f'for {location}') from e
        except (URLError, socket.timeout, ConnectionError, OSError) as e:
            raise Vault__Static_Transport_Error(
                f'static host unreachable: {self._root()} ({e}). '
                f'This is a transport failure, not an empty vault — '
                f'check the host/URL and that the server is up.') from e

    def batch_read(self, vault_id: str, file_ids: list, failures: dict = None) -> dict:
        """Bounded parallel GET fan-out. Per-object absence never aborts the
        run; a dead host raises before any parallel work starts."""
        from concurrent.futures import ThreadPoolExecutor
        payloads = {}
        if not file_ids:
            return payloads

        remaining = list(file_ids)
        if self.layout is None:                          # sniff once, serially
            for fid in remaining:
                data = self.read(vault_id, fid)          # raises on a dead host
                payloads[fid] = data
                if data is not None:
                    break                                # layout is now sticky
                self._record_absent(fid, failures)
            remaining = [fid for fid in file_ids if fid not in payloads]

        def fetch_one(fid):
            return fid, self._fetch(self._location(self.layout, vault_id, fid))

        if remaining and self.layout is not None:
            workers = LOCAL_WORKERS if self.is_local() else min(HTTP_WORKERS, len(remaining))
            with ThreadPoolExecutor(max_workers=workers) as executor:
                for fid, data in executor.map(fetch_one, remaining):
                    payloads[fid] = data
                    if data is None:
                        self._record_absent(fid, failures)
        else:
            for fid in remaining:                        # layout never resolved: all absent
                payloads[fid] = None
                self._record_absent(fid, failures)
        return payloads

    def _record_absent(self, file_id: str, failures: dict) -> None:
        if failures is None:
            return
        failures[file_id] = self._classify_per_file_status(file_id, 'not_found',
                                                           {'message': 'absent on static host (404)'})

    def presigned_read_url(self, vault_id: str, file_id: str) -> dict:
        """The object's OWN URL — urlopen handles file://, so the existing
        large-blob path works unmodified. Not optional: every blob over ~4 MB
        goes through this on clone."""
        for layout in self._candidate_layouts():
            location = self._location(layout, vault_id, file_id)
            if self.is_local():
                if os.path.isfile(location):
                    self._record(location)
                    return dict(url='file://' + location, expires_in=0)
            else:
                self._record(location)
                return dict(url=location, expires_in=0)
        raise Vault__Static_Transport_Error(f'not found in folder: {file_id} '
                                            f'(under {self._root()})')

    def list_files(self, vault_id: str, prefix: str = '') -> list:
        """Local: walk the folder. HTTP: enumerate via manifest.json when the
        host publishes one; a static host has no listing endpoint otherwise."""
        if self.is_local():
            root = self._root()
            base = os.path.join(root, prefix) if prefix else root
            if not os.path.isdir(base):
                return []
            return sorted(os.path.relpath(os.path.join(dir_path, name), root).replace(os.sep, '/')
                          for dir_path, _dirs, names in os.walk(base) for name in names)
        manifest = self._read_manifest()
        if not manifest:
            return []
        file_ids = [str(entry.get('file_id', '')) for entry in manifest.get('objects', [])]
        return sorted(fid for fid in file_ids if fid and fid.startswith(prefix))

    def read_root_file(self, rel_path: str) -> bytes:
        """Bytes of a file at the site ROOT (manifest.json, cover.json, the
        loader) — outside the vault-object layouts. None means absent; a dead
        host raises (F5). Used by mirror and the loader-adjacent tooling."""
        safe = '/'.join(quote(part, safe='') for part in rel_path.split('/'))
        if self.is_local():
            return self._fetch(os.path.join(self._root(), rel_path))
        return self._fetch(f'{self._root()}/{safe}')

    def _read_manifest(self) -> dict:
        import json
        try:
            data = self.read_root_file('manifest.json')
        except Vault__Static_Transport_Error:
            raise
        except Exception:
            return {}
        if not data:
            return {}
        try:
            return json.loads(data)
        except Exception:
            return {}

    # --- writes are refused structurally, not by convention -----------------

    def _read_only(self, *args, **kwargs):
        raise Vault__Read_Only_Transport_Error()

    write         = _read_only
    delete        = _read_only
    batch         = _read_only
    delete_vault  = _read_only
