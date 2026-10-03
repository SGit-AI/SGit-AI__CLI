"""CLI__Serve — the `sgit vault serve` command surface (P3).

Why the command exists: browsers give every file:// document an opaque
origin, so a loader opened by double-click cannot fetch the objects beside
it. Serving over 127.0.0.1 restores a real origin. It also covers the
unpacked-zip case, since unpacking yields a folder."""
import json
import os
import sys

from osbot_utils.type_safe.Type_Safe               import Type_Safe
from sgit_ai.crypto.Vault__Crypto                  import Vault__Crypto
from sgit_ai.network.api.Vault__API                import Vault__API
from sgit_ai.core.serve.Vault__Static_Server       import Vault__Static_Server
from sgit_ai.core.actions.publish.Vault__Publish   import Vault__Publish
from sgit_ai.safe_types.Safe_UInt__Port            import Safe_UInt__Port


class CLI__Serve(Type_Safe):
    block : bool = True        # False in tests: start, print, return the server

    def cmd_serve(self, args) -> Vault__Static_Server:
        directory = getattr(args, 'directory', None)
        port      = getattr(args, 'port', 8420) or 8420
        bind      = getattr(args, 'bind', '127.0.0.1') or '127.0.0.1'
        open_ui   = getattr(args, 'open', False)

        if directory:                                   # serving a folder someone else published
            root_dir = os.path.abspath(directory)
            if not os.path.isdir(root_dir):
                print(f'error: not a directory: {directory}', file=sys.stderr)
                sys.exit(1)
            vault_id, bare_dir = self._vault_context_for(root_dir)
        else:
            vault_root = self._find_vault_root()
            if not vault_root:
                print('error: not inside a vault — pass a directory to serve, or run inside '
                      'a vault work tree.', file=sys.stderr)
                sys.exit(1)
            publisher = Vault__Publish(crypto=Vault__Crypto(), api=Vault__API())
            root_dir  = os.path.join(vault_root, '.sg_vault', 'publish')
            if not os.path.isdir(root_dir):
                print('  No published folder yet — running `sgit publish` first.')
                publisher.publish(vault_root)
            elif publisher.is_stale(vault_root):
                print('  Published folder is stale (store moved on) — running `sgit publish` first.')
                publisher.publish(vault_root)
            vault_id, bare_dir = self._vault_context_for(root_dir)
            bare_dir = bare_dir or os.path.join(vault_root, '.sg_vault', 'bare')

        server = Vault__Static_Server(root_dir=root_dir, bare_dir=bare_dir,
                                      vault_id=vault_id, bind=bind,
                                      port=Safe_UInt__Port(int(port)))
        actual_port = server.start()
        self._print_banner(server, root_dir, vault_id, bind, actual_port)

        if open_ui:
            import webbrowser
            webbrowser.open(server.url() + 'index.html')    # the loader is the product
        if self.block:
            try:
                import threading
                threading.Event().wait()
            except KeyboardInterrupt:
                pass
            finally:
                server.stop()
        return server

    def _print_banner(self, server, root_dir, vault_id, bind, port):
        url = server.url()
        print()
        print(f'  Serving   {self._display_path(root_dir)}')
        if vault_id:
            print(f'  Vault     {vault_id}')
        print(f'  URL       {url}')
        print(f'  Loader    {url}index.html')
        if os.path.isfile(os.path.join(root_dir, 'api', 'docs', 'index.html')):
            print(f'  API docs  {url}api/docs/')
        print()
        print('  Why this command exists: browsers give local files an opaque origin, so')
        print('  opening index.html directly cannot fetch the objects next to it.')
        print()
        if str(bind) == '0.0.0.0':
            print('  ⚠ WARNING: bound to 0.0.0.0 — every machine on your network can now read')
            print('    this vault\'s published folder AND its encrypted store, read-key-free.')
            print('    Use the default 127.0.0.1 unless you mean to expose it.')
        else:
            print(f'  Read-only. Bound to {bind} (use --bind 0.0.0.0 to expose on the LAN).')
        print('  Objects served from .sg_vault/bare/ directly (virtual api/ route — no copies).')
        print('  Ctrl-C to stop.')
        print()

    def _display_path(self, root_dir: str) -> str:
        cwd = os.getcwd()
        if root_dir.startswith(cwd + os.sep):
            return root_dir[len(cwd) + 1:] + '/'
        return root_dir

    def _vault_context_for(self, root_dir: str):
        """(vault_id, bare_dir) from a published folder's manifest, when present."""
        manifest_path = os.path.join(root_dir, 'manifest.json')
        vault_id      = None
        bare_dir      = None
        if os.path.isfile(manifest_path):
            try:
                with open(manifest_path) as f:
                    vault_id = json.load(f).get('vault_id') or None
            except Exception:
                vault_id = None
        sibling_bare = os.path.abspath(os.path.join(root_dir, '..', 'bare'))
        if os.path.isdir(sibling_bare):
            bare_dir = sibling_bare
        return vault_id, bare_dir

    def _find_vault_root(self) -> str:
        current = os.path.abspath('.')
        while True:
            if os.path.isdir(os.path.join(current, '.sg_vault')):
                return current
            parent = os.path.dirname(current)
            if parent == current:
                return None
            current = parent
