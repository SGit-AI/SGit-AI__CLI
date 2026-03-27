import argparse
import os
import platform
import subprocess
import sys
from osbot_utils.type_safe.Type_Safe          import Type_Safe
from sgit_ai.cli.CLI__Vault               import CLI__Vault
from sgit_ai.cli.CLI__PKI                 import CLI__PKI
from sgit_ai.cli.CLI__Share               import CLI__Share
from sgit_ai.cli.CLI__Diff                import CLI__Diff
from sgit_ai.cli.CLI__Publish             import CLI__Publish
from sgit_ai.cli.CLI__Export              import CLI__Export


class CLI__Main(Type_Safe):
    vault   : CLI__Vault
    pki     : CLI__PKI
    share   : CLI__Share
    diff    : CLI__Diff
    publish : CLI__Publish
    export  : CLI__Export

    def _check_ssl_error(self, error: Exception) -> str:
        """Detect SSL certificate errors and return a helpful fix message, or empty string."""
        from urllib.error import URLError
        error_chain = [error]
        cause = error
        while cause.__cause__ or cause.__context__:
            cause = cause.__cause__ or cause.__context__
            error_chain.append(cause)

        is_ssl = False
        for err in error_chain:
            if isinstance(err, URLError) and 'CERTIFICATE_VERIFY_FAILED' in str(err):
                is_ssl = True
                break
            err_type = type(err).__name__
            if err_type in ('SSLCertVerificationError', 'SSLError'):
                is_ssl = True
                break

        if not is_ssl:
            return ''

        lines = ['SSL Error: certificate verification failed.',
                 '',
                 'This usually means Python cannot find your system SSL certificates.',
                 'To fix this:']
        if platform.system() == 'Darwin':
            py_ver = f'{sys.version_info.major}.{sys.version_info.minor}'
            lines.append(f'  Run:  /Applications/Python\\ {py_ver}/Install\\ Certificates.command')
            lines.append(f'  Or:   pip install certifi')
        else:
            lines.append('  Run:  pip install certifi')
            lines.append('  Or install your OS CA certificates package:')
            lines.append('    Debian/Ubuntu: sudo apt install ca-certificates')
            lines.append('    Fedora/RHEL:   sudo dnf install ca-certificates')
        return '\n'.join(lines)

    def _read_version(self) -> str:
        version_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'version')
        if os.path.isfile(version_file):
            with open(version_file, 'r') as f:
                return f.read().strip()
        return 'unknown'

    def cmd_update(self, args):
        print(f'Current version: {self._read_version()}')
        print('Updating sgit-ai...')
        result = subprocess.run([sys.executable, '-m', 'pip', 'install', '--upgrade', 'sgit-ai'],
                                capture_output=False)
        if result.returncode != 0:
            print('Update failed', file=sys.stderr)
            sys.exit(result.returncode)

    def build_parser(self) -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser(prog='sgit-ai',
                                         description='CLI tool for syncing encrypted vaults with SG/Send')
        parser.add_argument('--version', action='version', version=f'sgit-ai {self._read_version()}')
        parser.add_argument('--base-url', default=None, help='API base URL (default: https://dev.send.sgraph.ai)')
        parser.add_argument('--token',    default=None, help='SG/Send access token')
        parser.add_argument('--debug',    action='store_true', default=False,
                            help='Enable debug mode (show network traffic with timing)')

        subparsers = parser.add_subparsers(dest='command', help='Available commands')

        version_parser = subparsers.add_parser('version', help='Show sgit-ai version')
        version_parser.set_defaults(func=lambda args: print(f'sgit-ai {self._read_version()}'))

        update_parser = subparsers.add_parser('update', help='Update sgit-ai to the latest version')
        update_parser.set_defaults(func=self.cmd_update)

        # --- Core vault commands ---

        clone_parser = subparsers.add_parser('clone', help='Clone a vault from the remote server')
        clone_parser.add_argument('vault_key',   help='Vault key ({passphrase}:{vault_id})')
        clone_parser.add_argument('directory',   nargs='?', default=None, help='Directory to clone into (default: vault ID)')
        clone_parser.set_defaults(func=self.vault.cmd_clone)

        init_parser = subparsers.add_parser('init', help='Create a new empty vault and register it on the server')
        init_parser.add_argument('directory',   nargs='?', default='.', help='Directory to create the vault in (default: current directory)')
        init_parser.add_argument('--vault-key', default=None, help='Vault key ({passphrase}:{vault_id}). Generated randomly if omitted.')
        init_parser.add_argument('--existing',  action='store_true', default=False,
                                 help='Allow initialising into a non-empty directory without prompting')
        init_parser.add_argument('--restore',   action='store_true', default=False,
                                 help='Restore vault from a .vault__*.zip backup in the target directory')
        init_parser.set_defaults(func=self.vault.cmd_init)

        uninit_parser = subparsers.add_parser('uninit', help='Remove vault metadata (.sg_vault/), creating an auto-backup zip first')
        uninit_parser.add_argument('directory', nargs='?', default='.', help='Vault directory (default: .)')
        uninit_parser.set_defaults(func=self.vault.cmd_uninit)

        commit_parser = subparsers.add_parser('commit', help='Commit local changes to the clone branch')
        commit_parser.add_argument('message', nargs='?', default='', help='Commit message (auto-generated if omitted)')
        commit_parser.add_argument('-d', '--directory', default='.', help='Vault directory (default: .)')
        commit_parser.set_defaults(func=self.vault.cmd_commit)

        status_parser = subparsers.add_parser('status', help='Show uncommitted changes in working directory')
        status_parser.add_argument('directory', nargs='?', default='.', help='Vault directory (default: .)')
        status_parser.set_defaults(func=self.vault.cmd_status)

        diff_parser = subparsers.add_parser('diff', help='Show file-level and content-level diff')
        diff_parser.add_argument('directory',    nargs='?', default='.', help='Vault directory (default: .)')
        diff_parser.add_argument('--remote',     action='store_true',    default=False,
                                 help='Compare working copy vs named branch HEAD')
        diff_parser.add_argument('--commit',     default=None,           metavar='COMMIT_ID',
                                 help='Compare working copy vs specific commit')
        diff_parser.add_argument('--files-only', action='store_true',    default=False,
                                 help='Show file names only (no inline diff)')
        diff_parser.set_defaults(func=self.diff.cmd_diff)

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
        inspect_tree_parser.add_argument('--vault-key', default=None, help='Vault key (auto-read from .sg_vault/local/vault_key if omitted)')
        inspect_tree_parser.add_argument('directory', nargs='?', default='.', help='Vault directory (default: .)')
        inspect_tree_parser.set_defaults(func=self.vault.cmd_inspect_tree)

        inspect_log_parser = subparsers.add_parser('inspect-log', help='Show commit chain (dev tool)')
        inspect_log_parser.add_argument('--vault-key', default=None, help='Vault key (auto-read from .sg_vault/local/vault_key if omitted)')
        inspect_log_parser.add_argument('--oneline', action='store_true', help='Compact one-line-per-commit format')
        inspect_log_parser.add_argument('--graph', action='store_true', help='Show graph with connectors')
        inspect_log_parser.add_argument('directory', nargs='?', default='.', help='Vault directory (default: .)')
        inspect_log_parser.set_defaults(func=self.vault.cmd_inspect_log)

        cat_obj_parser = subparsers.add_parser('cat-object', help='Decrypt and display object contents (dev tool)')
        cat_obj_parser.add_argument('object_id', help='Object ID (12-char hex)')
        cat_obj_parser.add_argument('--vault-key', default=None, help='Vault key (auto-read from .sg_vault/local/vault_key if omitted)')
        cat_obj_parser.add_argument('--directory', '-d', default='.', help='Vault directory (default: .)')
        cat_obj_parser.set_defaults(func=self.vault.cmd_cat_object)

        inspect_stats_parser = subparsers.add_parser('inspect-stats', help='Show object store statistics (dev tool)')
        inspect_stats_parser.add_argument('directory', nargs='?', default='.', help='Vault directory (default: .)')
        inspect_stats_parser.set_defaults(func=self.vault.cmd_inspect_stats)

        log_parser = subparsers.add_parser('log', help='Show commit history (alias for inspect-log)')
        log_parser.add_argument('--vault-key', default=None, help='Vault key (auto-read from .sg_vault/local/vault_key if omitted)')
        log_parser.add_argument('--oneline', action='store_true', help='Compact one-line-per-commit format')
        log_parser.add_argument('--graph', action='store_true', help='Show graph with connectors')
        log_parser.add_argument('directory', nargs='?', default='.', help='Vault directory (default: .)')
        log_parser.set_defaults(func=self.vault.cmd_log)

        # --- Debug mode commands ---

        debug_parser     = subparsers.add_parser('debug', help='Enable or disable debug mode for a vault')
        debug_subparsers = debug_parser.add_subparsers(dest='debug_command', help='Debug subcommands')

        debug_on = debug_subparsers.add_parser('on',  help='Enable debug mode (persisted in .sg_vault/local/debug)')
        debug_on.add_argument('directory', nargs='?', default='.', help='Vault directory (default: .)')
        debug_on.set_defaults(func=self._cmd_debug_on)

        debug_off = debug_subparsers.add_parser('off', help='Disable debug mode')
        debug_off.add_argument('directory', nargs='?', default='.', help='Vault directory (default: .)')
        debug_off.set_defaults(func=self._cmd_debug_off)

        debug_status = debug_subparsers.add_parser('status', help='Show current debug mode state')
        debug_status.add_argument('directory', nargs='?', default='.', help='Vault directory (default: .)')
        debug_status.set_defaults(func=self._cmd_debug_status)

        # --- Bare vault commands ---

        checkout_parser = subparsers.add_parser('checkout', help='Extract working copy from bare vault')
        checkout_parser.add_argument('directory',   nargs='?', default='.', help='Vault directory (default: .)')
        checkout_parser.add_argument('--vault-key', default=None, help='Vault key (required for bare vaults)')
        checkout_parser.set_defaults(func=self.vault.cmd_checkout)

        clean_parser = subparsers.add_parser('clean', help='Remove working copy, keeping bare vault')
        clean_parser.add_argument('directory', nargs='?', default='.', help='Vault directory (default: .)')
        clean_parser.set_defaults(func=self.vault.cmd_clean)

        fsck_parser = subparsers.add_parser('fsck', help='Verify vault integrity and repair missing objects')
        fsck_parser.add_argument('directory', nargs='?', default='.', help='Vault directory (default: .)')
        fsck_parser.add_argument('--repair', action='store_true', help='Download missing objects from remote')
        fsck_parser.set_defaults(func=self.vault.cmd_fsck)

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

        # --- Share command ---

        share_parser = subparsers.add_parser('share', help='Share a vault snapshot via a Simple Token')
        share_parser.add_argument('directory', nargs='?', default='.', help='Vault directory (default: .)')
        share_parser.add_argument('--token', default=None,
                                  help='Use a specific token (format: word-word-NNNN). Generated randomly if omitted.')
        share_parser.set_defaults(func=self.share.cmd_share)

        # --- Publish command (multi-level encrypted zip, uploaded to Transfer API) ---

        publish_parser = subparsers.add_parser('publish',
                                               help='Publish vault snapshot as multi-level encrypted zip (sgit publish)')
        publish_parser.add_argument('directory', nargs='?', default='.',
                                    help='Vault directory (default: .)')
        publish_parser.add_argument('--token', default=None,
                                    help='Use a specific token (format: word-word-NNNN). Generated randomly if omitted.')
        publish_parser.add_argument('--no-inner-encrypt', dest='no_inner_encrypt',
                                    action='store_true', default=False,
                                    help='Skip inner encryption (inner_key_type=none)')
        publish_parser.set_defaults(func=self.publish.cmd_publish)

        # --- Export command (multi-level encrypted zip, saved locally) ---

        export_parser = subparsers.add_parser('export',
                                              help='Export vault snapshot as a local encrypted zip file (sgit export)')
        export_parser.add_argument('directory', nargs='?', default='.',
                                   help='Vault directory (default: .)')
        export_parser.add_argument('--output', default=None,
                                   help='Output filename (auto-generated if omitted)')
        export_parser.add_argument('--token', default=None,
                                   help='Use a specific token (format: word-word-NNNN). Generated randomly if omitted.')
        export_parser.add_argument('--no-inner-encrypt', dest='no_inner_encrypt',
                                   action='store_true', default=False,
                                   help='Skip inner encryption (inner_key_type=none)')
        export_parser.set_defaults(func=self.export.cmd_export)

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

        if args.command == 'debug':
            if not getattr(args, 'debug_command', None):
                parser.parse_args([args.command, '--help'])

        if args.command == 'remote':
            if not getattr(args, 'remote_command', None):
                parser.parse_args([args.command, '--help'])

        if args.command == 'pki':
            if not getattr(args, 'pki_command', None):
                parser.parse_args([args.command, '--help'])
            self.pki.setup()

        try:
            debug_log = self._setup_debug(args)
        except Exception:
            debug_log = None

        try:
            args.func(args)
        except KeyboardInterrupt:
            print('\nInterrupted.', file=sys.stderr)
            sys.exit(130)
        except RuntimeError as e:
            print(f'error: {e}', file=sys.stderr)
            sys.exit(1)
        except Exception as e:
            ssl_hint = self._check_ssl_error(e)
            if ssl_hint:
                print(ssl_hint, file=sys.stderr)
                sys.exit(1)
            if debug_log:
                raise                                       # full traceback in debug mode
            self._print_friendly_error(e, args)
            sys.exit(1)
        finally:
            if debug_log:
                debug_log.print_summary()

    def _print_friendly_error(self, error: Exception, args):
        """Print a user-friendly error message instead of a raw traceback."""
        import traceback
        error_type = type(error).__name__
        command    = getattr(args, 'command', 'unknown')
        message    = str(error)

        # Map common exceptions to helpful messages
        directory = getattr(args, 'directory', '.')
        if isinstance(error, FileNotFoundError):
            print(f'error: missing file — {message}', file=sys.stderr)
            print(f'  hint: the vault may be corrupted or incomplete', file=sys.stderr)
            print(f'  hint: try "sgit fsck {directory}" to check and repair', file=sys.stderr)
        elif isinstance(error, PermissionError):
            print(f'error: permission denied — {message}', file=sys.stderr)
        elif isinstance(error, (ConnectionError, OSError)):
            print(f'error: network or I/O failure — {message}', file=sys.stderr)
        elif isinstance(error, ValueError) and 'does not match required pattern' in message:
            print(f'error: incompatible vault data — {message}', file=sys.stderr)
            print(f'  hint: this vault was likely created with an older CLI version', file=sys.stderr)
            print(f'  hint: re-clone the vault with the current CLI:', file=sys.stderr)
            print(f'          sgit clone <vault-key> <directory>', file=sys.stderr)
        else:
            print(f'error: {error_type} in "{command}" — {message}', file=sys.stderr)

        # Always show short traceback context for debugging
        tb = traceback.extract_tb(error.__traceback__)
        if tb:
            last = tb[-1]
            print(f'  at {last.filename}:{last.lineno} in {last.name}', file=sys.stderr)
        print(f'  run with --debug for full details', file=sys.stderr)

    def _setup_debug(self, args):
        directory = getattr(args, 'directory', None) or '.'
        debug_on  = getattr(args, 'debug', False) or self._load_debug_flag(directory)
        if not debug_on:
            return None
        from sgit_ai.cli.CLI__Debug_Log import CLI__Debug_Log
        debug_log = CLI__Debug_Log(enabled=True)
        self.vault.debug_log = debug_log
        debug_log.print_header()
        return debug_log

    def _load_debug_flag(self, directory: str) -> bool:
        debug_path = os.path.join(directory, '.sg_vault', 'local', 'debug')
        if os.path.isfile(debug_path):
            with open(debug_path, 'r') as f:
                return f.read().strip() == 'on'
        return False

    def _save_debug_flag(self, directory: str, enabled: bool):
        debug_path = os.path.join(directory, '.sg_vault', 'local', 'debug')
        local_dir  = os.path.dirname(debug_path)
        if not os.path.isdir(local_dir):
            raise RuntimeError(f'Not a vault directory: {directory} (no .sg_vault/local/ found)')
        with open(debug_path, 'w') as f:
            f.write('on' if enabled else 'off')

    def _cmd_debug_on(self, args):
        self._save_debug_flag(args.directory, True)
        print(f'Debug mode enabled for {args.directory}')

    def _cmd_debug_off(self, args):
        self._save_debug_flag(args.directory, False)
        print(f'Debug mode disabled for {args.directory}')

    def _cmd_debug_status(self, args):
        enabled = self._load_debug_flag(args.directory)
        state   = 'on' if enabled else 'off'
        print(f'Debug mode: {state}')
