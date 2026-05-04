"""CLI__Dev — wires the sgit dev <…> subcommands into argparse."""
import argparse

from osbot_utils.type_safe.Type_Safe                           import Type_Safe
from sgit_ai.plugins.dev.Dev__Profile__Clone                       import Dev__Profile__Clone
from sgit_ai.plugins.dev.Dev__Tree__Graph                          import Dev__Tree__Graph
from sgit_ai.plugins.dev.Dev__Server__Objects                      import Dev__Server__Objects
from sgit_ai.plugins.dev.Dev__Step__Clone                          import Dev__Step__Clone
from sgit_ai.plugins.dev.Dev__Replay                               import Dev__Replay
from sgit_ai.plugins.dev.workflow.CLI__Dev__Workflow               import CLI__Dev__Workflow
from sgit_ai.crypto.Vault__Crypto                              import Vault__Crypto


class CLI__Dev(Type_Safe):
    """Container for all `sgit dev` sub-tools."""

    crypto    : Vault__Crypto
    vault_ref : object           = None   # CLI__Vault instance (injected by CLI__Main)
    dump_ref  : object           = None   # CLI__Dump  instance
    main_ref  : object           = None   # CLI__Main  instance (for debug flag helpers)
    workflow  : CLI__Dev__Workflow

    # ------------------------------------------------------------------
    # Tool factories (use real API when api=None)
    # ------------------------------------------------------------------

    def _profile(self):
        from sgit_ai.core.Vault__Sync import Vault__Sync
        return Dev__Profile__Clone(crypto=self.crypto,
                                   sync=Vault__Sync(crypto=self.crypto))

    def _tree_graph(self):
        from sgit_ai.core.Vault__Sync import Vault__Sync
        return Dev__Tree__Graph(crypto=self.crypto,
                                sync=Vault__Sync(crypto=self.crypto))

    def _server_objects(self):
        from sgit_ai.core.Vault__Sync import Vault__Sync
        return Dev__Server__Objects(crypto=self.crypto,
                                    sync=Vault__Sync(crypto=self.crypto))

    def _step_clone(self):
        from sgit_ai.core.Vault__Sync import Vault__Sync
        return Dev__Step__Clone(crypto=self.crypto,
                                sync=Vault__Sync(crypto=self.crypto))

    # ------------------------------------------------------------------
    # Command handlers
    # ------------------------------------------------------------------

    def cmd_profile_clone(self, args):
        t = self._profile()
        t.setup()
        t.cmd_profile_clone(args)

    def cmd_tree_graph(self, args):
        t = self._tree_graph()
        t.setup()
        t.cmd_tree_graph(args)

    def cmd_server_objects(self, args):
        t = self._server_objects()
        t.setup()
        t.cmd_server_objects(args)

    def cmd_step_clone(self, args):
        t = self._step_clone()
        t.setup()
        t.cmd_step_clone(args)

    def cmd_replay(self, args):
        Dev__Replay().cmd_replay(args)

    def cmd_derive_keys(self, args):
        self.vault_ref.cmd_derive_keys(args)

    def cmd_dump(self, args):
        self.dump_ref.cmd_dump(args)

    def cmd_debug_on(self, args):
        self.main_ref._cmd_debug_on(args)

    def cmd_debug_off(self, args):
        self.main_ref._cmd_debug_off(args)

    def cmd_debug_status(self, args):
        self.main_ref._cmd_debug_status(args)

    def cmd_cat_object(self, args):
        self.vault_ref.cmd_cat_object(args)

    def cmd_plugins_list(self, args):
        from sgit_ai.plugins._base.Plugin__Loader import Plugin__Loader
        import json
        import sys
        loader = Plugin__Loader()
        items  = loader.list_all()
        if getattr(args, 'json', False):
            print(json.dumps(items, indent=2))
        else:
            for item in items:
                state = 'enabled' if item['enabled'] else 'disabled'
                print(f"  {item['name']:12s}  v{item['version']:8s}  {item['stability']:12s}  {state}")

    def cmd_plugins_show(self, args):
        from sgit_ai.plugins._base.Plugin__Loader import Plugin__Loader
        import json
        import sys
        loader = Plugin__Loader()
        for name, path in loader.discover():
            if name == args.name:
                manifest = loader.load_manifest(path)
                print(json.dumps(manifest.json(), indent=2))
                return
        print(f"Plugin '{args.name}' not found.", file=sys.stderr)
        sys.exit(1)

    def cmd_plugins_enable(self, args):
        from sgit_ai.plugins._base.Plugin__Loader import Plugin__Loader
        import sys
        loader = Plugin__Loader()
        known  = [n for n, _ in loader.discover()]
        if args.name not in known:
            print(f"Plugin '{args.name}' not found.", file=sys.stderr)
            sys.exit(1)
        loader.set_enabled(args.name, True)
        print(f"Plugin '{args.name}' enabled.")

    def cmd_plugins_disable(self, args):
        from sgit_ai.plugins._base.Plugin__Loader import Plugin__Loader
        import sys
        loader = Plugin__Loader()
        known  = [n for n, _ in loader.discover()]
        if args.name not in known:
            print(f"Plugin '{args.name}' not found.", file=sys.stderr)
            sys.exit(1)
        loader.set_enabled(args.name, False)
        print(f"Plugin '{args.name}' disabled.")

    # ------------------------------------------------------------------
    # Argparse registration
    # ------------------------------------------------------------------

    def register(self, subparsers: argparse._SubParsersAction):
        """Add `dev` sub-parser tree to an existing subparsers action."""
        dev_parser     = subparsers.add_parser('dev', help='Dev/perf instrumentation tools (sgit dev <tool>)')
        dev_subparsers = dev_parser.add_subparsers(dest='dev_command', help='Dev tool subcommands')
        dev_parser.set_defaults(func=lambda args: dev_parser.print_help())

        # sgit dev profile clone <vault-key> <directory>
        profile_p = dev_subparsers.add_parser('profile',
                                               help='Profile a vault operation')
        profile_sub = profile_p.add_subparsers(dest='profile_command')
        profile_p.set_defaults(func=lambda args: profile_p.print_help())

        pc = profile_sub.add_parser('clone', help='Profile the clone pipeline with per-phase timing')
        pc.add_argument('vault_key',  help='Vault key ({passphrase}:{vault_id})')
        pc.add_argument('directory',  help='Directory to clone into')
        pc.add_argument('--sparse',   action='store_true', default=False,
                        help='Sparse clone (no blob download)')
        pc.add_argument('--json',     action='store_true', default=False,
                        help='Output machine-readable JSON')
        pc.add_argument('--output', '-o', default=None, metavar='FILE',
                        help='Write JSON to FILE instead of stdout')
        pc.set_defaults(func=self.cmd_profile_clone)

        # sgit dev tree-graph <vault-key>
        tg = dev_subparsers.add_parser('tree-graph',
                                        help='Visualise tree DAG from vault metadata')
        tg.add_argument('vault_key', help='Vault key')
        tg.add_argument('--json',   action='store_true', default=False, help='JSON output')
        tg.add_argument('--output', '-o', default=None, metavar='FILE', help='Write JSON to FILE')
        tg.add_argument('--dot',    default=None, metavar='FILE', help='Write Graphviz DOT to FILE')
        tg.set_defaults(func=self.cmd_tree_graph)

        # sgit dev server-objects <vault-key>
        so = dev_subparsers.add_parser('server-objects',
                                        help='Inventory remote objects by type')
        so.add_argument('vault_key', help='Vault key')
        so.add_argument('--json',    action='store_true', default=False, help='JSON output')
        so.add_argument('--output', '-o', default=None, metavar='FILE', help='Write JSON to FILE')
        so.set_defaults(func=self.cmd_server_objects)

        # sgit dev step-clone <vault-key> <directory>
        sc = dev_subparsers.add_parser('step-clone',
                                        help='Pausable clone with per-phase progress')
        sc.add_argument('vault_key',   help='Vault key')
        sc.add_argument('directory',   help='Directory to clone into')
        sc.add_argument('--no-pause',  dest='no_pause', action='store_true', default=False,
                        help='Non-interactive; do not pause between steps')
        sc.add_argument('--json',      action='store_true', default=False, help='JSON output')
        sc.set_defaults(func=self.cmd_step_clone)

        # sgit dev replay <trace.json> [--diff other.json]
        rp = dev_subparsers.add_parser('replay',
                                        help='Replay / diff a clone trace JSON offline')
        rp.add_argument('trace', help='Path to trace JSON (from sgit dev profile clone --json)')
        rp.add_argument('--diff',   default=None, metavar='OTHER',
                        help='Compare against a second trace JSON')
        rp.add_argument('--json',   action='store_true', default=False, help='JSON output')
        rp.set_defaults(func=self.cmd_replay)

        # sgit dev derive-keys  (was top-level `derive-keys`)
        dk = dev_subparsers.add_parser('derive-keys', help='Derive and display vault keys')
        dk.add_argument('vault_key', help='Vault key ({passphrase}:{vault_id})')
        dk.set_defaults(func=self.cmd_derive_keys)

        # sgit dev dump  (was top-level `dump`)
        dump_p = dev_subparsers.add_parser('dump',
                                            help='Dump complete internal vault state as JSON')
        dump_p.add_argument('directory',        nargs='?', default='.', help='Vault directory (default: .)')
        dump_p.add_argument('--remote',         action='store_true', default=False,
                            help='Dump remote server state instead of local')
        dump_p.add_argument('--structure-key',  default=None, metavar='HEX',
                            help='Use structure key (hex) for metadata-only dump')
        dump_p.add_argument('--output', '-o',   default=None, metavar='FILE',
                            help='Write dump JSON to FILE instead of stdout')
        dump_p.set_defaults(func=self.cmd_dump)

        # sgit dev cat-object <id>  (was top-level `cat-object`)
        co = dev_subparsers.add_parser('cat-object', help='Decrypt and display object contents')
        co.add_argument('object_id', help='Object ID (12-char hex)')
        co.add_argument('--vault-key', default=None,
                        help='Vault key (auto-read from .sg_vault/local/vault_key if omitted)')
        co.add_argument('--directory', '-d', default='.', help='Vault directory (default: .)')
        co.set_defaults(func=self.cmd_cat_object)

        # sgit dev debug  (was top-level `debug`)
        debug_p   = dev_subparsers.add_parser('debug', help='Enable or disable debug mode for a vault')
        debug_sub = debug_p.add_subparsers(dest='debug_command')
        debug_p.set_defaults(func=lambda a: debug_p.print_help())

        debug_on = debug_sub.add_parser('on',  help='Enable debug mode')
        debug_on.add_argument('directory', nargs='?', default='.', help='Vault directory (default: .)')
        debug_on.set_defaults(func=self.cmd_debug_on)

        debug_off = debug_sub.add_parser('off', help='Disable debug mode')
        debug_off.add_argument('directory', nargs='?', default='.', help='Vault directory (default: .)')
        debug_off.set_defaults(func=self.cmd_debug_off)

        debug_st = debug_sub.add_parser('status', help='Show current debug mode state')
        debug_st.add_argument('directory', nargs='?', default='.', help='Vault directory (default: .)')
        debug_st.set_defaults(func=self.cmd_debug_status)

        # sgit dev workflow <…>
        self.workflow.register(dev_subparsers)

        # sgit dev plugins list / show / enable / disable
        plugins_p   = dev_subparsers.add_parser('plugins', help='Manage sgit-ai plugins')
        plugins_sub = plugins_p.add_subparsers(dest='plugins_command')
        plugins_p.set_defaults(func=lambda a: plugins_p.print_help())

        pl_list = plugins_sub.add_parser('list', help='List all plugins with status')
        pl_list.add_argument('--json', action='store_true', default=False, help='Output as JSON')
        pl_list.set_defaults(func=self.cmd_plugins_list)

        pl_show = plugins_sub.add_parser('show', help='Show a plugin manifest')
        pl_show.add_argument('name', help='Plugin name')
        pl_show.set_defaults(func=self.cmd_plugins_show)

        pl_enable = plugins_sub.add_parser('enable', help='Enable a plugin')
        pl_enable.add_argument('name', help='Plugin name')
        pl_enable.set_defaults(func=self.cmd_plugins_enable)

        pl_disable = plugins_sub.add_parser('disable', help='Disable a plugin')
        pl_disable.add_argument('name', help='Plugin name')
        pl_disable.set_defaults(func=self.cmd_plugins_disable)

        return dev_parser
