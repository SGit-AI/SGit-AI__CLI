"""CLI__Serve — `sgit serve`: run a vault on this machine.

  sgit serve                     the vault UI + API (SG/Send image) on localhost, this clone copied in
  sgit serve stop|status|logs    manage it        sgit serve update   newest image, restart
  sgit serve push [--force]      send this clone's new commits to it
  sgit serve pull                bring work done in the browser back into this clone (then `sgit push`)
  sgit serve runtimes            container runtimes found on this machine
  sgit serve install [runtime]   install one (shows exactly what, then asks)
  sgit serve --static [DIR]      read-only file server for a *published* vault (was `sgit vault serve`)
"""
import json
import os
import sys

from osbot_utils.type_safe.Type_Safe               import Type_Safe
from sgit_ai.crypto.Vault__Crypto                  import Vault__Crypto
from sgit_ai.network.api.Vault__API                import Vault__API
from sgit_ai.core.Vault__Errors                    import Vault__Serve_Error
from sgit_ai.core.serve.Vault__Static_Server       import Vault__Static_Server
from sgit_ai.core.serve.Vault__Serve               import Vault__Serve, IMAGE_DEFAULT, PORT_DEFAULT, BIND_DEFAULT
from sgit_ai.core.actions.publish.Vault__Publish   import Vault__Publish
from sgit_ai.safe_types.Safe_UInt__Port            import Safe_UInt__Port

STATIC_PORT_DEFAULT = 8420


class CLI__Serve(Type_Safe):
    block : bool = True        # False in tests: start, print, return the server

    # ---------------------------------------------------------- registration
    def register(self, subparsers):
        serve_p = subparsers.add_parser('serve', help='Run this vault on your machine: the vault UI + API in a '
                                                      'container (Docker, Podman, Apple container), or --static')
        serve_p.add_argument('--static', nargs='?', const='', default=None, metavar='DIR',
                             help='Read-only server for a published vault (default: this vault\'s '
                                  '.sg_vault/publish/, publishing first if needed)')
        serve_p.add_argument('--port',    type=int, default=None, help=f'Port on this machine (default {PORT_DEFAULT}; '
                                                                     f'the next free one if taken)')
        serve_p.add_argument('--bind',    default=BIND_DEFAULT, help='Address to bind (default 127.0.0.1; 0.0.0.0 '
                                                                     'exposes it to your network)')
        serve_p.add_argument('--open',    action='store_true', default=False, help='Open the UI in a browser')
        serve_p.add_argument('--data',    default=None, metavar='DIR',
                             help='Data folder for the server (default: .sg_vault/serve/data in this clone)')
        serve_p.add_argument('--runtime', default=None, metavar='NAME',
                             help='container | docker | podman | nerdctl | finch | uv (default: the first found)')
        serve_p.add_argument('--image',   default=IMAGE_DEFAULT, help=f'Image to run (default {IMAGE_DEFAULT})')
        serve_p.add_argument('--no-pull', action='store_true', default=False,
                             help='Do not check for a newer image; use the one already here')
        serve_p.add_argument('--ui-dir',  default=None, metavar='DIR', help='Built vault UI folder (uv engine only)')
        serve_p.set_defaults(func=self.cmd_serve)

        sub = serve_p.add_subparsers(dest='serve_command')
        sub.add_parser('stop',     help='Stop the local server').set_defaults(func=self.cmd_stop)
        sub.add_parser('status',   help='Is it running, where, which image').set_defaults(func=self.cmd_status)
        logs_p = sub.add_parser('logs', help='Server output')
        logs_p.add_argument('-f', '--follow', action='store_true', default=False)
        logs_p.set_defaults(func=self.cmd_logs)
        sub.add_parser('update',   help='Get the newest image and restart (same data)').set_defaults(func=self.cmd_update)
        push_p = sub.add_parser('push', help='Send this clone\'s commits to the local server')
        push_p.add_argument('--force', action='store_true', default=False,
                            help='Overwrite commits that exist only on the local server')
        push_p.set_defaults(func=self.cmd_push)
        sub.add_parser('pull',     help='Bring work done in the browser into this clone (fast-forward)'
                                        ).set_defaults(func=self.cmd_pull)
        sub.add_parser('runtimes', help='Container runtimes on this machine').set_defaults(func=self.cmd_runtimes)
        install_p = sub.add_parser('install', help='Install a container runtime (shows what, then asks)')
        install_p.add_argument('runtime', nargs='?', default=None,
                               help='container | podman | docker | uv (default: the one recommended here)')
        install_p.add_argument('--yes', action='store_true', default=False, help='Do not ask')
        install_p.set_defaults(func=self.cmd_install)
        return serve_p

    def register_moved(self, vault_sub):
        """`sgit vault serve` moved to `sgit serve --static` (rule 9): say so, run nothing."""
        moved = vault_sub.add_parser('serve', help='Moved: sgit serve --static')
        moved.add_argument('rest', nargs='*')
        moved.set_defaults(func=self.cmd_moved)

    # ------------------------------------------------------------- helpers
    def vault_serve(self) -> Vault__Serve:
        return Vault__Serve().setup()

    def directory(self, args) -> str:
        return getattr(args, 'vault', None) or '.'

    def progress(self, kind: str, text: str) -> None:
        labels = {'runtime': 'Runtime', 'pull': 'Image', 'start': 'Run', 'wait': 'Waiting', 'warn': 'warning'}
        print(f'  {labels.get(kind, kind):<9} {text}', file=sys.stderr if kind == 'warn' else sys.stdout)

    def fail(self, error: Exception) -> None:
        print(f'error: {error}', file=sys.stderr)
        sys.exit(1)

    def mirror(self, url: str):
        from sgit_ai.core.serve.Vault__Serve__Mirror import Vault__Serve__Mirror
        return Vault__Serve__Mirror(crypto=Vault__Crypto(), api=Vault__API(base_url=url, access_token=''))   # nosec B106: no token; the local server sgit serve started has no auth

    def sent_path(self, places: dict) -> str:
        return os.path.join(places['data_dir'], '.sgit-sent.json')         # goes when the data goes

    def running_url(self, args) -> tuple:
        info = self.vault_serve().status(self.directory(args), getattr(args, 'data', None))
        if info['status'] != 'running':
            raise Vault__Serve_Error('the local server is not running here: sgit serve')
        return info['url'], info['places']

    # ------------------------------------------------------------ commands
    def cmd_moved(self, args):
        print("sgit: 'vault serve' is now 'sgit serve --static' (and `sgit serve` runs the full vault locally)",
              file=sys.stderr)
        sys.exit(2)

    def cmd_serve(self, args):
        if getattr(args, 'static', None) is not None:
            return self.cmd_serve_static(args)
        serve = self.vault_serve()
        try:
            info = serve.start(self.directory(args), data=args.data, port=args.port or PORT_DEFAULT, bind=args.bind,
                               runtime_name=args.runtime, image=args.image, pull=not args.no_pull,
                               ui_dir=args.ui_dir, on_progress=self.progress)
        except Vault__Serve_Error as error:
            self.fail(error)
        url, places, state = info['url'], info['places'], info['state']
        copied = None
        if places['vault_root']:
            try:
                copied = self.mirror(url).push(places['vault_root'], record_path=self.sent_path(places))
            except Vault__Serve_Error as error:
                print(f'  warning: {error}', file=sys.stderr)
        self.print_banner(info, copied)
        if args.open:
            import webbrowser
            webbrowser.open(self.ui_url(url, str(state.runtime)))
        return info

    def ui_url(self, url: str, runtime: str) -> str:
        return url + '/' if runtime == 'uv' else url + '/en-gb/vault/'

    def print_banner(self, info: dict, copied) -> None:
        state, url = info['state'], info['url']
        versions   = info.get('versions') or {}
        server     = versions.get('sgraph_ai_app_send', '')
        print()
        print('  Local vault server ' + ('already running' if info['status'] == 'already_running' else 'running'))
        print(f'  UI        {self.ui_url(url, str(state.runtime))}')
        print(f'  API       {url}/api/   (docs {url}/api/docs)')
        print(f'  Runtime   {state.runtime}' + (f'   image {state.image_digest or state.image}' if str(state.runtime) != 'uv' else '')
              + (f'   SG/Send {server}' if server else ''))
        print(f'  Data      {info["places"]["data_dir"]}')
        if str(state.runtime) == 'uv':
            print(f'  No container runtime, so no bundled UI: open https://vault.sgraph.ai and set "Server" to {url}')
            print('  (or install one for the local UI: sgit serve install)')
        if copied is not None:
            print(f'  This clone was copied in ({copied["uploaded"]} new objects).')
            print('  In the browser: "Full Vault Key" = this vault\'s key (sgit vault show-key); to edit, put any')
            print('  text in "Access Key" (the local server has no auth).')
            print('  Bring browser edits back:  sgit serve pull   then  sgit push')
            print('  Send new commits to it:    sgit serve push')
        if str(state.bind) == '0.0.0.0':
            print('  ⚠ bound to 0.0.0.0: every machine on your network can reach this server.')
        print('  Stop: sgit serve stop    Logs: sgit serve logs    Status: sgit serve status')
        print()

    def cmd_stop(self, args):
        try:
            info = self.vault_serve().stop(self.directory(args), getattr(args, 'data', None))
        except Vault__Serve_Error as error:
            self.fail(error)
        print('  Stopped.' if info['status'] == 'stopped' else '  No local server was started here.')

    def cmd_status(self, args):
        try:
            info = self.vault_serve().status(self.directory(args), getattr(args, 'data', None))
        except Vault__Serve_Error as error:
            self.fail(error)
        if info['status'] == 'not_started':
            print('  No local server here (start one: sgit serve)')
            return info
        state = info['state']
        print(f'  Status    {info["status"]}')
        print(f'  URL       {info["url"]}')
        print(f'  Runtime   {state.runtime}   container {state.container_name}')
        if str(state.runtime) != 'uv':
            print(f'  Image     {state.image}   ({state.image_digest or "digest unknown"})')
        server = (info.get('versions') or {}).get('sgraph_ai_app_send')
        if server:
            print(f'  SG/Send   {server}')
        print(f'  Data      {state.data_dir}')
        return info

    def cmd_logs(self, args):
        try:
            sys.exit(self.vault_serve().logs(self.directory(args), getattr(args, 'data', None), args.follow) or 0)
        except Vault__Serve_Error as error:
            self.fail(error)

    def cmd_update(self, args):
        serve = self.vault_serve()
        try:
            before = serve.status(self.directory(args), getattr(args, 'data', None))
            state  = before.get('state')
            serve.stop(self.directory(args), getattr(args, 'data', None))
            args.port    = int(state.host_port) if state is not None else (args.port or PORT_DEFAULT)
            args.runtime = str(state.runtime) if state is not None else args.runtime
            args.no_pull = False
        except Vault__Serve_Error as error:
            self.fail(error)
        return self.cmd_serve(args)

    def cmd_push(self, args):
        try:
            url, places = self.running_url(args)
            if not places['vault_root']:
                raise Vault__Serve_Error('run this inside the clone you are serving')
            result = self.mirror(url).push(places['vault_root'], force=args.force, record_path=self.sent_path(places))
        except Vault__Serve_Error as error:
            self.fail(error)
        print(f'  Sent {result["uploaded"]} new objects; the local server is ' +
              ('now at this clone\'s head.' if result['moved'] else 'already up to date.'))

    def cmd_pull(self, args):
        try:
            url, places = self.running_url(args)
            if not places['vault_root']:
                raise Vault__Serve_Error('run this inside the clone you are serving')
            result = self.mirror(url).pull(places['vault_root'])
        except Vault__Serve_Error as error:
            self.fail(error)
        if result['status'] == 'up_to_date':
            print('  Nothing new on the local server.')
        else:
            print(f'  This clone now has the local server\'s work ({result["to"][:24]}…). '
                  f'Send it to the real server with: sgit push')

    def cmd_runtimes(self, args):
        serve = self.vault_serve()
        rows  = serve.runtimes().report()
        print(f'  This machine: {serve.host.system} {serve.host.machine} {serve.host.os_version}')
        for row in rows:
            mark = 'ready' if row['ready'] else ('installed, not running' if row['installed'] else 'not installed')
            print(f'  {row["name"]:<10} {mark:<24} {row["describe"]}')
        if not any(row['ready'] for row in rows):
            print(f'  Install one: sgit serve install {serve.installer().recommended()[0]}')
        return rows

    def cmd_install(self, args):
        from sgit_ai.cli.CLI__Input import CLI__Input
        serve = self.vault_serve()
        try:
            plan = serve.installer().plan(args.runtime)
        except ValueError as error:
            self.fail(error)
        for line in serve.installer().describe(plan):
            print(line)
        print()
        if not args.yes:
            answer = CLI__Input().prompt('  Install it now? [y/N] ')
            if (answer or '').strip().lower() not in ('y', 'yes'):
                print('  Nothing was installed.')
                return
        code = serve.installer().execute(plan)
        if code != 0:
            print(f'error: an install step failed (exit {code}); nothing after it was run', file=sys.stderr)
            sys.exit(1)
        print()
        print(f'  Installed. Next: {plan["after"][-1]}')

    # ------------------------------------------------------- static mode
    def cmd_serve_static(self, args) -> Vault__Static_Server:
        directory = getattr(args, 'static', None) or None
        port      = getattr(args, 'port', None) or STATIC_PORT_DEFAULT
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
        self._print_static_banner(server, root_dir, vault_id, bind, actual_port)

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

    def _print_static_banner(self, server, root_dir, vault_id, bind, port):
        url = server.url()
        print()
        print(f'  Serving   {self._display_path(root_dir)}   (static, read-only)')
        if vault_id:
            print(f'  Vault     {vault_id}')
        print(f'  URL       {url}')
        print(f'  Loader    {url}index.html')
        if os.path.isfile(os.path.join(root_dir, 'api', 'docs', 'index.html')):
            print(f'  API docs  {url}api/docs/')
        print()
        print('  Why this command exists: browsers give local files an opaque origin, so')
        print('  opening index.html directly cannot fetch the objects next to it.')
        print('  For the full vault (UI + API, editable) run: sgit serve')
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
