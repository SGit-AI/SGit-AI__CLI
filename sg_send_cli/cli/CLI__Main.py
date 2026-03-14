import argparse
import os
import sys
from osbot_utils.type_safe.Type_Safe          import Type_Safe
from sg_send_cli.cli.CLI__Vault               import CLI__Vault
from sg_send_cli.cli.CLI__PKI                 import CLI__PKI


class CLI__Main(Type_Safe):
    vault : CLI__Vault
    pki   : CLI__PKI

    def _read_version(self) -> str:
        version_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'version')
        if os.path.isfile(version_file):
            with open(version_file, 'r') as f:
                return f.read().strip()
        return 'unknown'

    def build_parser(self) -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser(prog='sg-send-cli',
                                         description='CLI tool for syncing encrypted vaults with SG/Send')
        parser.add_argument('--version', action='version', version=f'sg-send-cli {self._read_version()}')
        parser.add_argument('--base-url', default=None, help='API base URL (default: https://send.sgraph.ai)')
        parser.add_argument('--token',    default=None, help='SG/Send access token')

        subparsers = parser.add_subparsers(dest='command', help='Available commands')

        # --- Core vault commands ---

        init_parser = subparsers.add_parser('init', help='Create a new empty vault and register it on the server')
        init_parser.add_argument('directory',   help='Directory to create the vault in (must be empty or non-existent)')
        init_parser.add_argument('--vault-key', default=None, help='Vault key ({passphrase}:{vault_id}). Generated randomly if omitted.')
        init_parser.set_defaults(func=self.vault.cmd_init)

        commit_parser = subparsers.add_parser('commit', help='Commit local changes to the clone branch')
        commit_parser.add_argument('-m', '--message', default='', help='Commit message (auto-generated if omitted)')
        commit_parser.add_argument('directory', nargs='?', default='.', help='Vault directory (default: .)')
        commit_parser.set_defaults(func=self.vault.cmd_commit)

        status_parser = subparsers.add_parser('status', help='Show uncommitted changes in working directory')
        status_parser.add_argument('directory', nargs='?', default='.', help='Vault directory (default: .)')
        status_parser.set_defaults(func=self.vault.cmd_status)

        pull_parser = subparsers.add_parser('pull', help='Pull named branch changes and merge into clone branch')
        pull_parser.add_argument('directory', nargs='?', default='.', help='Vault directory (default: .)')
        pull_parser.set_defaults(func=self.vault.cmd_pull)

        push_parser = subparsers.add_parser('push', help='Push clone branch to the named branch')
        push_parser.add_argument('directory', nargs='?', default='.', help='Vault directory (default: .)')
        push_parser.add_argument('--branch-only', action='store_true',
                                 help='Push clone branch objects and ref without updating named branch')
        push_parser.set_defaults(func=self.vault.cmd_push)

        branches_parser = subparsers.add_parser('branches', help='List all branches in the vault')
        branches_parser.add_argument('directory', nargs='?', default='.', help='Vault directory (default: .)')
        branches_parser.set_defaults(func=self.vault.cmd_branches)

        merge_abort_parser = subparsers.add_parser('merge-abort', help='Abort an in-progress merge')
        merge_abort_parser.add_argument('directory', nargs='?', default='.', help='Vault directory (default: .)')
        merge_abort_parser.set_defaults(func=self.vault.cmd_merge_abort)

        # --- Remote management commands ---

        remote_parser     = subparsers.add_parser('remote', help='Manage vault remotes')
        remote_subparsers = remote_parser.add_subparsers(dest='remote_command', help='Remote subcommands')

        remote_add = remote_subparsers.add_parser('add', help='Add a remote')
        remote_add.add_argument('name',            help='Remote name (e.g. origin)')
        remote_add.add_argument('url',             help='Remote API URL')
        remote_add.add_argument('remote_vault_id', help='Remote vault ID')
        remote_add.add_argument('--directory', '-d', default='.', help='Vault directory (default: .)')
        remote_add.set_defaults(func=self.vault.cmd_remote_add)

        remote_remove = remote_subparsers.add_parser('remove', help='Remove a remote')
        remote_remove.add_argument('name',          help='Remote name to remove')
        remote_remove.add_argument('--directory', '-d', default='.', help='Vault directory (default: .)')
        remote_remove.set_defaults(func=self.vault.cmd_remote_remove)

        remote_list = remote_subparsers.add_parser('list', help='List configured remotes')
        remote_list.add_argument('--directory', '-d', default='.', help='Vault directory (default: .)')
        remote_list.set_defaults(func=self.vault.cmd_remote_list)

        # --- Debug/inspection commands ---

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

        log_parser = subparsers.add_parser('log', help='Show commit history (alias for inspect-log)')
        log_parser.add_argument('--vault-key', default=None, help='Vault key (auto-read from .sg_vault/VAULT-KEY if omitted)')
        log_parser.add_argument('--oneline', action='store_true', help='Compact one-line-per-commit format')
        log_parser.add_argument('--graph', action='store_true', help='Show graph with connectors')
        log_parser.add_argument('directory', nargs='?', default='.', help='Vault directory (default: .)')
        log_parser.set_defaults(func=self.vault.cmd_log)

        # --- Bare vault commands ---

        checkout_parser = subparsers.add_parser('checkout', help='Extract working copy from bare vault')
        checkout_parser.add_argument('directory',   nargs='?', default='.', help='Vault directory (default: .)')
        checkout_parser.add_argument('--vault-key', default=None, help='Vault key (required for bare vaults)')
        checkout_parser.set_defaults(func=self.vault.cmd_checkout)

        clean_parser = subparsers.add_parser('clean', help='Remove working copy, keeping bare vault')
        clean_parser.add_argument('directory', nargs='?', default='.', help='Vault directory (default: .)')
        clean_parser.set_defaults(func=self.vault.cmd_clean)

        # --- Vault credential store commands ---

        vault_parser     = subparsers.add_parser('vault', help='Manage stored vault credentials')
        vault_subparsers = vault_parser.add_subparsers(dest='vault_command', help='Vault subcommands')

        vault_add = vault_subparsers.add_parser('add', help='Store a vault key under an alias')
        vault_add.add_argument('alias', help='Human-friendly name for this vault')
        vault_add.add_argument('--vault-key', default=None, help='Vault key (prompted if omitted)')
        vault_add.set_defaults(func=self.vault.cmd_vault_add)

        vault_list = vault_subparsers.add_parser('list', help='List stored vault aliases')
        vault_list.set_defaults(func=self.vault.cmd_vault_list)

        vault_remove = vault_subparsers.add_parser('remove', help='Remove a stored vault key')
        vault_remove.add_argument('alias', help='Vault alias to remove')
        vault_remove.set_defaults(func=self.vault.cmd_vault_remove)

        vault_show = vault_subparsers.add_parser('show', help='Show vault key for an alias')
        vault_show.add_argument('alias', help='Vault alias')
        vault_show.set_defaults(func=self.vault.cmd_vault_show)

        # --- PKI commands ---

        pki_parser     = subparsers.add_parser('pki', help='PKI key management and encryption')
        pki_subparsers = pki_parser.add_subparsers(dest='pki_command', help='PKI subcommands')

        pki_keygen = pki_subparsers.add_parser('keygen', help='Generate encryption + signing key pair')
        pki_keygen.add_argument('--label', default='', help='Label for the key pair')
        pki_keygen.set_defaults(func=self.pki.cmd_keygen)

        pki_list = pki_subparsers.add_parser('list', help='List local key pairs')
        pki_list.set_defaults(func=self.pki.cmd_list)

        pki_export = pki_subparsers.add_parser('export', help='Export public key bundle (JSON)')
        pki_export.add_argument('fingerprint', help='Encryption key fingerprint')
        pki_export.set_defaults(func=self.pki.cmd_export)

        pki_delete = pki_subparsers.add_parser('delete', help='Delete key pair')
        pki_delete.add_argument('fingerprint', help='Encryption key fingerprint')
        pki_delete.set_defaults(func=self.pki.cmd_delete)

        pki_import = pki_subparsers.add_parser('import', help='Import contact public key')
        pki_import.add_argument('file', help='Path to public key bundle JSON (or - for stdin)')
        pki_import.set_defaults(func=self.pki.cmd_import_contact)

        pki_contacts = pki_subparsers.add_parser('contacts', help='List imported contacts')
        pki_contacts.set_defaults(func=self.pki.cmd_contacts)

        pki_sign = pki_subparsers.add_parser('sign', help='Sign a file (detached signature)')
        pki_sign.add_argument('file', help='File to sign')
        pki_sign.add_argument('--fingerprint', required=True, help='Signing key fingerprint')
        pki_sign.set_defaults(func=self.pki.cmd_sign)

        pki_verify = pki_subparsers.add_parser('verify', help='Verify a detached signature')
        pki_verify.add_argument('file', help='File to verify')
        pki_verify.add_argument('signature', help='Signature file (.sig)')
        pki_verify.set_defaults(func=self.pki.cmd_verify)

        pki_encrypt = pki_subparsers.add_parser('encrypt', help='Encrypt a file for a recipient')
        pki_encrypt.add_argument('file', help='File to encrypt')
        pki_encrypt.add_argument('--recipient', required=True, help='Recipient fingerprint')
        pki_encrypt.add_argument('--fingerprint', default=None, help='Your key fingerprint (for signing)')
        pki_encrypt.set_defaults(func=self.pki.cmd_encrypt)

        pki_decrypt = pki_subparsers.add_parser('decrypt', help='Decrypt a file with local key')
        pki_decrypt.add_argument('file', help='Encrypted file (.enc)')
        pki_decrypt.add_argument('--fingerprint', required=True, help='Your encryption key fingerprint')
        pki_decrypt.set_defaults(func=self.pki.cmd_decrypt)

        return parser

    def run(self, argv=None):
        parser = self.build_parser()
        args   = parser.parse_args(argv)
        if not args.command:
            parser.print_help()
            sys.exit(1)

        if args.command == 'vault':
            if not getattr(args, 'vault_command', None):
                parser.parse_args([args.command, '--help'])
            self.vault.setup_credential_store()

        if args.command == 'remote':
            if not getattr(args, 'remote_command', None):
                parser.parse_args([args.command, '--help'])

        if args.command == 'pki':
            if not getattr(args, 'pki_command', None):
                parser.parse_args([args.command, '--help'])
            self.pki.setup()

        try:
            args.func(args)
        except RuntimeError as e:
            print(str(e), file=sys.stderr)
            sys.exit(1)
