import argparse
import sys
from osbot_utils.type_safe.Type_Safe          import Type_Safe
from sg_send_cli.cli.CLI__Vault               import CLI__Vault
from sg_send_cli.sync.Vault__Legacy_Guard     import Legacy_Vault_Error


class CLI__Main(Type_Safe):
    vault : CLI__Vault

    def build_parser(self) -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser(prog='sg-send-cli',
                                         description='CLI tool for syncing encrypted vaults with SG/Send')
        parser.add_argument('--base-url', default=None, help='API base URL (default: https://send.sgraph.ai)')
        parser.add_argument('--token',    default=None, help='SG/Send access token')

        subparsers = parser.add_subparsers(dest='command', help='Available commands')

        init_parser = subparsers.add_parser('init', help='Create a new empty vault and register it on the server')
        init_parser.add_argument('directory',   help='Directory to create the vault in (must be empty or non-existent)')
        init_parser.add_argument('--vault-key', default=None, help='Vault key ({passphrase}:{vault_id}). Generated randomly if omitted.')
        init_parser.set_defaults(func=self.vault.cmd_init)

        clone_parser = subparsers.add_parser('clone', help='Clone a remote vault to a local directory')
        clone_parser.add_argument('vault_key',  help='Vault key ({passphrase}:{vault_id})')
        clone_parser.add_argument('directory',  nargs='?', default=None, help='Target directory (default: vault_id)')
        clone_parser.set_defaults(func=self.vault.cmd_clone)

        pull_parser = subparsers.add_parser('pull', help='Pull remote changes to local directory')
        pull_parser.add_argument('directory', nargs='?', default='.', help='Vault directory (default: .)')
        pull_parser.set_defaults(func=self.vault.cmd_pull)

        push_parser = subparsers.add_parser('push', help='Push local changes to the remote vault')
        push_parser.add_argument('directory', nargs='?', default='.', help='Vault directory (default: .)')
        push_parser.set_defaults(func=self.vault.cmd_push)

        status_parser = subparsers.add_parser('status', help='Show local changes vs vault tree')
        status_parser.add_argument('directory', nargs='?', default='.', help='Vault directory (default: .)')
        status_parser.set_defaults(func=self.vault.cmd_status)

        remote_status_parser = subparsers.add_parser('remote-status', help='Compare local vault against remote')
        remote_status_parser.add_argument('directory', nargs='?', default='.', help='Vault directory (default: .)')
        remote_status_parser.set_defaults(func=self.vault.cmd_remote_status)

        keys_parser = subparsers.add_parser('derive-keys', help='Derive and display vault keys (debug)')
        keys_parser.add_argument('vault_key', help='Vault key ({passphrase}:{vault_id})')
        keys_parser.set_defaults(func=self.vault.cmd_derive_keys)

        inspect_parser = subparsers.add_parser('inspect', help='Show vault state overview (dev tool)')
        inspect_parser.add_argument('directory', nargs='?', default='.', help='Vault directory (default: .)')
        inspect_parser.set_defaults(func=self.vault.cmd_inspect)

        inspect_obj_parser = subparsers.add_parser('inspect-object', help='Show object details (dev tool)')
        inspect_obj_parser.add_argument('object_id', help='Object ID (12-char hex)')
        inspect_obj_parser.add_argument('directory', nargs='?', default='.', help='Vault directory (default: .)')
        inspect_obj_parser.set_defaults(func=self.vault.cmd_inspect_object)

        inspect_tree_parser = subparsers.add_parser('inspect-tree', help='Show current tree entries (dev tool)')
        inspect_tree_parser.add_argument('--vault-key', default=None, help='Vault key (auto-read from .sg_vault/VAULT-KEY if omitted)')
        inspect_tree_parser.add_argument('directory', nargs='?', default='.', help='Vault directory (default: .)')
        inspect_tree_parser.set_defaults(func=self.vault.cmd_inspect_tree)

        inspect_log_parser = subparsers.add_parser('inspect-log', help='Show commit chain (dev tool)')
        inspect_log_parser.add_argument('--vault-key', default=None, help='Vault key (auto-read from .sg_vault/VAULT-KEY if omitted)')
        inspect_log_parser.add_argument('--oneline', action='store_true', help='Compact one-line-per-commit format')
        inspect_log_parser.add_argument('--graph', action='store_true', help='Show graph with connectors')
        inspect_log_parser.add_argument('directory', nargs='?', default='.', help='Vault directory (default: .)')
        inspect_log_parser.set_defaults(func=self.vault.cmd_inspect_log)

        cat_obj_parser = subparsers.add_parser('cat-object', help='Decrypt and display object contents (dev tool)')
        cat_obj_parser.add_argument('object_id', help='Object ID (12-char hex)')
        cat_obj_parser.add_argument('--vault-key', default=None, help='Vault key (auto-read from .sg_vault/VAULT-KEY if omitted)')
        cat_obj_parser.add_argument('--directory', '-d', default='.', help='Vault directory (default: .)')
        cat_obj_parser.set_defaults(func=self.vault.cmd_cat_object)

        inspect_stats_parser = subparsers.add_parser('inspect-stats', help='Show object store statistics (dev tool)')
        inspect_stats_parser.add_argument('directory', nargs='?', default='.', help='Vault directory (default: .)')
        inspect_stats_parser.set_defaults(func=self.vault.cmd_inspect_stats)

        return parser

    def run(self, argv=None):
        parser = self.build_parser()
        args   = parser.parse_args(argv)
        if not args.command:
            parser.print_help()
            sys.exit(1)
        try:
            args.func(args)
        except Legacy_Vault_Error as e:
            print(f'Error: {e}', file=sys.stderr)
            sys.exit(2)
        except RuntimeError as e:
            print(str(e), file=sys.stderr)
            sys.exit(1)
