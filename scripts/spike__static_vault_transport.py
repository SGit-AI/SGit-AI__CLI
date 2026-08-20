"""SPIKE — 'any server I can GET from' + local/networked folder, as one transport.

STATUS: a sizing spike for the 08/17 "Static Clone" proposal round — NOT shipped
code and NOT wired into the CLI. It exists so the round can argue from running
code. Run it directly:  python scripts/spike__static_vault_transport.py

What it demonstrates, with zero changes to any CLI call site:
  * a full `clone` from a plain folder, with no network at all
  * the same clone from any dumb GET server (python -m http.server)
  * both static layouts auto-detected (objects at the web root, or at
    live-API paths api/vault/read/<vault_id>/<file_id>)
  * writes refused structurally, not by convention

Adds layout sniffing: a static host may expose objects either at the live-API
path (api/vault/read/<id>/<file_id>) or simply at <file_id> (a plain directory
server / S3 sync / USB stick). The transport probes both on the FIRST read and
sticks with whichever answers — so the user never has to know or configure it.
"""
import functools, os, shutil, sys, tempfile, threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote
from urllib.request import urlopen

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from sgit_ai.network.api.Vault__API import Vault__API


class Vault__API__Static(Vault__API):
    """Read-only vault transport over plain GET / open(). No auth, no writes.

    byte source is decided by base_url shape:
      /abs/path or file://…   -> open()      (local or networked folder)
      http(s)://…             -> GET         (any static file server)
    and the on-host LAYOUT is sniffed once, not configured.
    """
    LAYOUTS = ('api/vault/read/{vid}/{fid}', '{fid}')

    def _init_state(self):
        if not hasattr(self, '_layout'):
            self._layout = None                      # sticky after first success

    def _is_local(self):
        b = str(self.base_url or '')
        return not (b.startswith('http://') or b.startswith('https://'))

    def _root(self):
        return str(self.base_url or '').replace('file://', '').rstrip('/')

    def _candidate_urls(self, vault_id, file_id):
        self._init_state()
        layouts = [self._layout] if self._layout else list(self.LAYOUTS)
        for lay in layouts:
            rel = lay.format(vid=vault_id, fid=file_id)
            if self._is_local():
                yield lay, os.path.join(self._root(), rel)
            else:
                safe = '/'.join(quote(p, safe='') for p in rel.split('/'))
                yield lay, f'{self._root()}/{safe}'

    def read(self, vault_id: str, file_id: str) -> bytes:
        last = None
        for layout, loc in self._candidate_urls(vault_id, file_id):
            try:
                if self._is_local():
                    if not os.path.isfile(loc):
                        raise FileNotFoundError(loc)
                    data = Path(loc).read_bytes()
                else:
                    with urlopen(loc, timeout=30) as r:
                        data = r.read()
                self._layout = layout                # remember what works
                return data
            except Exception as e:
                last = e
        raise RuntimeError(f'Not found: {file_id} ({last})')

    def batch_read(self, vault_id: str, file_ids: list, failures: dict = None) -> dict:
        from concurrent.futures import ThreadPoolExecutor
        self._init_state()
        if self._layout is None and file_ids:        # sniff once, serially
            try:
                self.read(vault_id, file_ids[0])
            except Exception:
                pass

        def one(fid):
            try:
                return fid, self.read(vault_id, fid)
            except Exception:
                return fid, None
        workers = 1 if self._is_local() else 8       # bounded fan-out
        with ThreadPoolExecutor(max_workers=workers) as ex:
            return dict(ex.map(one, file_ids))

    def presigned_read_url(self, vault_id: str, file_id: str) -> dict:
        for _layout, loc in self._candidate_urls(vault_id, file_id):
            if self._is_local():
                if os.path.isfile(loc):
                    return dict(url='file://' + loc, expires_in=0)
            else:
                return dict(url=loc, expires_in=0)
        raise RuntimeError(f'Not found: {file_id}')

    def list_files(self, vault_id: str, prefix: str = '') -> list:
        if not self._is_local():
            return []                                # static hosts have no listing
        root = self._root()
        base = os.path.join(root, prefix) if prefix else root
        if not os.path.isdir(base):
            return []
        return sorted(os.path.relpath(os.path.join(dp, f), root).replace(os.sep, '/')
                      for dp, _dn, fn in os.walk(base) for f in fn)

    def _readonly(self, *a, **k):
        raise RuntimeError('Vault opened read-only (static/folder transport); '
                           'writes need the live API.')
    write = delete = batch = _readonly


def serve(directory):
    handler = functools.partial(SimpleHTTPRequestHandler, directory=directory)
    httpd   = ThreadingHTTPServer(('127.0.0.1', 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, f'http://127.0.0.1:{httpd.server_address[1]}'


def main():
    from sgit_ai.core.Vault__Sync import Vault__Sync
    from sgit_ai.crypto.Vault__Crypto import Vault__Crypto
    from sgit_ai.network.api.Vault__API__In_Memory import Vault__API__In_Memory

    tmp = tempfile.mkdtemp(prefix='spike_http_')
    try:
        api  = Vault__API__In_Memory().setup()
        sync = Vault__Sync(crypto=Vault__Crypto(), api=api)
        origin = os.path.join(tmp, 'origin')
        r = sync.init(origin)
        Path(origin, 'hello.txt').write_text('served over plain GET')
        os.makedirs(os.path.join(origin, 'docs'), exist_ok=True)
        Path(origin, 'docs', 'page.md').write_text('# Page\n')
        sync.commit(origin, 'initial'); sync.push(origin)
        vid = r['vault_id']

        # layout 1: plain directory server — bare/ at the web root
        flat = os.path.join(tmp, 'site_flat')
        shutil.copytree(os.path.join(origin, '.sg_vault'), flat)
        # layout 2: mirrors live-API paths
        api_like = os.path.join(tmp, 'site_api', 'api', 'vault', 'read', vid)
        os.makedirs(os.path.dirname(api_like), exist_ok=True)
        shutil.copytree(os.path.join(origin, '.sg_vault'), api_like)

        for label, root in (('plain dir server', flat),
                            ('live-API path layout', os.path.join(tmp, 'site_api'))):
            httpd, url = serve(root)
            try:
                st = Vault__API__Static(base_url=url); st.setup()
                dest = os.path.join(tmp, 'clone_' + label.split()[0])
                Vault__Sync(crypto=Vault__Crypto(), api=st).clone(r['vault_key'], dest)
                ok = (Path(dest, 'hello.txt').read_text() == 'served over plain GET'
                      and Path(dest, 'docs', 'page.md').read_text() == '# Page\n')
                print(f'HTTP clone [{label:22}] -> {"OK" if ok else "FAILED"}  (layout sniffed: {st._layout})')
            finally:
                httpd.shutdown()

        # and the same transport against a folder (works for a network mount too)
        st   = Vault__API__Static(base_url=flat); st.setup()
        dest = os.path.join(tmp, 'clone_folder')
        Vault__Sync(crypto=Vault__Crypto(), api=st).clone(r['vault_key'], dest)
        print(f'FOLDER clone [no network]        -> '
              f'{"OK" if Path(dest,"hello.txt").read_text()=="served over plain GET" else "FAILED"}'
              f'  (layout sniffed: {st._layout})')
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == '__main__':
    main()
