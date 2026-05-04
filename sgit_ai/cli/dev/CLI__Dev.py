"""CLI__Dev — wires the sgit dev <…> subcommands into argparse."""
import argparse

from osbot_utils.type_safe.Type_Safe           import Type_Safe
from sgit_ai.cli.dev.Dev__Profile__Clone       import Dev__Profile__Clone
from sgit_ai.cli.dev.Dev__Tree__Graph          import Dev__Tree__Graph
from sgit_ai.cli.dev.Dev__Server__Objects      import Dev__Server__Objects
from sgit_ai.cli.dev.Dev__Step__Clone          import Dev__Step__Clone
from sgit_ai.cli.dev.Dev__Replay               import Dev__Replay
from sgit_ai.crypto.Vault__Crypto              import Vault__Crypto


class CLI__Dev(Type_Safe):
    """Container for all `sgit dev` sub-tools."""

    crypto : Vault__Crypto

    # ------------------------------------------------------------------
    # Tool factories (use real API when api=None)
    # ------------------------------------------------------------------

    def _profile(self):
        from sgit_ai.sync.Vault__Sync import Vault__Sync
        return Dev__Profile__Clone(crypto=self.crypto,
                                   sync=Vault__Sync(crypto=self.crypto))

    def _tree_graph(self):
        from sgit_ai.sync.Vault__Sync import Vault__Sync
        return Dev__Tree__Graph(crypto=self.crypto,
                                sync=Vault__Sync(crypto=self.crypto))

    def _server_objects(self):
        from sgit_ai.sync.Vault__Sync import Vault__Sync
        return Dev__Server__Objects(crypto=self.crypto,
                                    sync=Vault__Sync(crypto=self.crypto))

    def _step_clone(self):
        from sgit_ai.sync.Vault__Sync import Vault__Sync
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

        return dev_parser
