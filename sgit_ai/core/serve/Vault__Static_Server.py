"""Vault__Static_Server — `sgit vault serve` (P3 of the static-publishing pack).

Why this command exists: browsers give every file:// document an OPAQUE
ORIGIN, so a loader opened by double-click cannot fetch the objects beside it.
This is the fix — a deliberately dumb local file server. The product's claim
is that no server is needed; this one is a convenience and must look like it:
stdlib only, read-only, no directory listing, bound to 127.0.0.1 by default.

It performs the COMPOSED view virtually (r9): requests under
/api/vault/read/<vault_id>/bare/* are routed to .sg_vault/bare/* on disk —
the store is never copied. Everything else is served from the published
surface folder.

Security posture:
  SP-8 — every resolved path (including the virtual bare route) goes through
         Vault__Path_Guard; traversal and encoded variants are refused.
  SP-9 — when bound to loopback, the Host header must be 127.0.0.1/localhost
         (DNS-rebinding defence); any other value is refused with 403.
  Read-only: any method other than GET/HEAD gets 405.

Placement note: the pack names sgit_ai/network/serve/ for this file, but the
repo's layer rules forbid network → storage imports and the path guard lives
in storage — so the server lives in core, which may import both.
"""
import functools
import mimetypes
import os
import threading
from   http.server                                import BaseHTTPRequestHandler, ThreadingHTTPServer
from   urllib.parse                               import unquote, urlsplit

from   osbot_utils.type_safe.Type_Safe            import Type_Safe
from   sgit_ai.safe_types.Safe_Str__Bind_Address  import Safe_Str__Bind_Address
from   sgit_ai.safe_types.Safe_Str__Vault_Id      import Safe_Str__Vault_Id
from   sgit_ai.safe_types.Safe_Str__Vault_Path    import Safe_Str__Vault_Path
from   sgit_ai.safe_types.Safe_UInt__Port         import Safe_UInt__Port
from   sgit_ai.storage.Vault__Path_Guard          import Vault__Path_Guard, Vault__Unsafe_Path_Error

LOOPBACK_HOSTS = {'127.0.0.1', 'localhost', '::1', '[::1]'}


class _Serve_Handler(BaseHTTPRequestHandler):
    """Request handler bound to a Vault__Static_Server via functools.partial."""
    server_config = None      # set per-server through the factory
    quiet         = False

    def log_message(self, format, *args):                        # noqa: A002 — stdlib signature
        if not self.quiet:
            import sys
            print(f'  {self.command} {self.path}   {format % args}', file=sys.stderr)

    # --- read-only: everything but GET/HEAD is 405 --------------------------

    def do_GET(self):
        self._serve(send_body=True)

    def do_HEAD(self):
        self._serve(send_body=False)

    def _refuse_write(self):
        self.send_response(405, 'Method Not Allowed')
        self.send_header('Allow', 'GET, HEAD')
        self.end_headers()

    do_POST = do_PUT = do_DELETE = do_PATCH = do_OPTIONS = _refuse_write

    # --- resolution ---------------------------------------------------------

    def _serve(self, send_body: bool) -> None:
        config = self.server_config
        if not self._host_header_allowed():
            self._error(403, 'Forbidden: unexpected Host header (DNS-rebinding defence). '
                             'Use http://127.0.0.1 or http://localhost.')
            return
        try:
            file_path = self._resolve(config)
        except Vault__Unsafe_Path_Error:
            self._error(403, 'Forbidden: path escapes the served folder')
            return
        if file_path is None or not os.path.isfile(file_path):
            self._error(404, 'Not found')
            return
        content_type = mimetypes.guess_type(file_path)[0] or 'application/octet-stream'
        with open(file_path, 'rb') as f:
            body = f.read()
        self.send_response(200)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        if send_body:
            self.wfile.write(body)

    def _host_header_allowed(self) -> bool:
        config = self.server_config
        if str(config.bind) not in LOOPBACK_HOSTS:               # widened deliberately (--bind):
            return True                                          # the warning was printed at start
        host = (self.headers.get('Host') or '').strip()
        if not host:
            return False
        if host.startswith('['):                                 # [::1]:port
            host = host.split(']')[0] + ']'
        else:
            host = host.split(':')[0]
        return host in LOOPBACK_HOSTS

    def _resolve(self, config) -> str:
        raw_path = urlsplit(self.path).path
        path     = unquote(raw_path)
        if '\x00' in path:
            raise Vault__Unsafe_Path_Error('refusing NUL byte in path')
        guard      = Vault__Path_Guard()
        bare_route = f'/api/vault/read/{config.vault_id}/bare/' if config.vault_id else None
        if bare_route and config.bare_dir and path.startswith(bare_route):
            rel = path[len(bare_route):]
            return guard.safe_join(str(config.bare_dir), rel)    # SP-8: virtual route is guarded
        rel = path.lstrip('/')
        if not rel:
            rel = 'index.html'
        full = guard.safe_join(str(config.root_dir), rel)
        if os.path.isdir(full):                                  # no directory listing, ever —
            return guard.safe_join(full, 'index.html')           # a dir resolves to its index only
        return full

    def _error(self, code: int, message: str) -> None:
        body = message.encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'text/plain; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        if self.command != 'HEAD':
            self.wfile.write(body)


class Vault__Static_Server(Type_Safe):
    root_dir : Safe_Str__Vault_Path   = None    # the published surface, served at /
    bare_dir : Safe_Str__Vault_Path   = None    # optional: .sg_vault/bare for the virtual route
    vault_id : Safe_Str__Vault_Id     = None    # optional: enables the virtual route
    bind     : Safe_Str__Bind_Address = None    # default 127.0.0.1
    port     : Safe_UInt__Port                  # 0 = pick a free port
    quiet    : bool                   = False
    httpd    : object                 = None

    def start(self) -> int:
        """Bind and start serving on a daemon thread; returns the actual port
        (--port 0 picks a free one, needed by tests)."""
        if not self.bind:
            self.bind = Safe_Str__Bind_Address('127.0.0.1')
        if not self.root_dir or not os.path.isdir(str(self.root_dir)):
            raise ValueError(f'not a directory: {self.root_dir!r}')
        handler = type('_Bound_Handler', (_Serve_Handler,),
                       dict(server_config=self, quiet=self.quiet))
        self.httpd = ThreadingHTTPServer((str(self.bind), int(self.port)), handler)
        self.port  = Safe_UInt__Port(self.httpd.server_address[1])
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        return int(self.port)

    def serve_forever(self) -> None:
        """Blocking variant for the CLI (Ctrl-C to stop)."""
        port = self.start()
        try:
            threading.Event().wait()
        except KeyboardInterrupt:
            pass
        finally:
            self.stop()

    def stop(self) -> None:
        if self.httpd is not None:
            self.httpd.shutdown()
            self.httpd.server_close()
            self.httpd = None

    def url(self) -> str:
        host = str(self.bind or '127.0.0.1')
        if host == '0.0.0.0':
            host = '127.0.0.1'
        return f'http://{host}:{int(self.port)}/'
