"""CLI__Inspect — `sgit inspect <…>` namespace (vault, tree, object, stats, diff-state)."""
import argparse

from osbot_utils.type_safe.Type_Safe import Type_Safe


class CLI__Inspect(Type_Safe):
    vault : object = None   # CLI__Vault instance (injected by CLI__Main)
    dump  : object = None   # CLI__Dump  instance

    def register(self, subparsers: argparse._SubParsersAction):
        insp_p   = subparsers.add_parser('inspect', help='Read-only vault inspection tools')
        insp_sub = insp_p.add_subparsers(dest='inspect_command')
        insp_p.set_defaults(func=lambda a: insp_p.print_help())

        # inspect vault  (was top-level `inspect`)
        vi_p = insp_sub.add_parser('vault', help='Show vault state overview')
        vi_p.add_argument('directory', nargs='?', default='.', help='Vault directory (default: .)')
        vi_p.set_defaults(func=self.vault.cmd_inspect)

        # inspect tree  (was `inspect-tree`)
        tree_p = insp_sub.add_parser('tree', help='Show current tree entries')
        tree_p.add_argument('--vault-key', default=None,
                            help='Vault key (auto-read from .sg_vault/local/vault_key if omitted)')
        tree_p.add_argument('directory', nargs='?', default='.', help='Vault directory (default: .)')
        tree_p.set_defaults(func=self.vault.cmd_inspect_tree)

        # inspect object  (was `inspect-object`)
        obj_p = insp_sub.add_parser('object', help='Show object details')
        obj_p.add_argument('object_id', help='Object ID (12-char hex)')
        obj_p.add_argument('directory', nargs='?', default='.', help='Vault directory (default: .)')
        obj_p.set_defaults(func=self.vault.cmd_inspect_object)

        # inspect stats  (was `inspect-stats`)
        stats_p = insp_sub.add_parser('stats', help='Show object store statistics')
        stats_p.add_argument('directory', nargs='?', default='.', help='Vault directory (default: .)')
        stats_p.set_defaults(func=self.vault.cmd_inspect_stats)

        # inspect diff-state  (was `diff-state`)
        ds_p = insp_sub.add_parser('diff-state', help='Compare two vault dumps and report divergences')
        ds_p.add_argument('dump_a',   nargs='?', default=None, help='Path to first dump JSON file')
        ds_p.add_argument('dump_b',   nargs='?', default=None, help='Path to second dump JSON file')
        ds_p.add_argument('--local',  action='store_true', default=False,
                          help='Produce local dump on the fly')
        ds_p.add_argument('--remote', action='store_true', default=False,
                          help='Produce remote dump on the fly')
        ds_p.add_argument('directory', nargs='?', default='.',
                          help='Vault directory for on-the-fly dump (default: .)')
        ds_p.set_defaults(func=self.dump.cmd_dump_diff)

        return insp_p
