import argparse
import os
import stat
import platform
import subprocess
import sys
from osbot_utils.type_safe.Type_Safe          import Type_Safe
from sgit_ai.cli.CLI__Vault                    import CLI__Vault
from sgit_ai.cli.CLI__PKI                      import CLI__PKI
from sgit_ai.cli.CLI__Share                    import CLI__Share
from sgit_ai.cli.CLI__Diff                     import CLI__Diff
from sgit_ai.cli.CLI__Dump                     import CLI__Dump
from sgit_ai.cli.CLI__Publish                  import CLI__Publish
from sgit_ai.cli.CLI__Export                   import CLI__Export
from sgit_ai.cli.CLI__Revert                   import CLI__Revert
from sgit_ai.cli.CLI__Stash                    import CLI__Stash
from sgit_ai.cli.CLI__Branch                   import CLI__Branch
from sgit_ai.cli.CLI__Create                   import CLI__Create
from sgit_ai.cli.CLI__Migrate                  import CLI__Migrate
from sgit_ai.plugins._base.Plugin__Loader      import Plugin__Loader




class CLI__Main(Type_Safe):
    vault   : CLI__Vault
    pki           : CLI__PKI
    share         : CLI__Share
    diff          : CLI__Diff
    dump          : CLI__Dump
    publish       : CLI__Publish
    export        : CLI__Export
    revert        : CLI__Revert
    stash         : CLI__Stash
    branch        : CLI__Branch
    create        : CLI__Create
    migrate       : CLI__Migrate
    plugin_loader : Plugin__Loader

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
        self.branch.vault = self.vault

        self.create.vault_ref   = self.vault
        self.create.token_store = self.vault.token_store

        parser = argparse.ArgumentParser(prog='sgit-ai',
                                         description='CLI tool for syncing encrypted vaults with SG/Send')
        parser.add_argument('--version', action='version', version=f'sgit-ai {self._read_version()}')
        parser.add_argument('--base-url', default=None, help='API base URL (default: https://dev.send.sgraph.ai)')
        parser.add_argument('--token',    default=None, help='SG/Send access token')
        parser.add_argument('--debug',    action='store_true', default=False,
                            help='Enable debug mode (show network traffic with timing)')
        parser.add_argument('--vault',    default=None, metavar='PATH',
                            help='Override context detection: treat PATH as the vault root')

        subparsers = parser.add_subparsers(dest='command', help='Available commands')

        # ------------------------------------------------------------------
        # Top-level primitives
        # ------------------------------------------------------------------

        version_parser = subparsers.add_parser('version', help='Show sgit-ai version')
        version_parser.set_defaults(func=lambda args: print(f'sgit-ai {self._read_version()}'))

        update_parser = subparsers.add_parser('update', help='Update sgit-ai to the latest version')
        update_parser.set_defaults(func=self.cmd_update)

        # sgit help [command|all]
        help_p = subparsers.add_parser('help', help='Show help (use `sgit help all` for full surface)')
        help_p.add_argument('topic', nargs='?', default=None,
                            help='Command name or "all" to show the full command surface')
        help_p.set_defaults(func=lambda a: self._cmd_help(a, parser))

        clone_parser = subparsers.add_parser('clone', help='Clone a vault from the remote server')
        clone_parser.add_argument('vault_key',   help='Vault key ({passphrase}:{vault_id})')
        clone_parser.add_argument('directory',   nargs='?', default=None, help='Directory to clone into (default: vault ID)')
        clone_parser.add_argument('--force',     action='store_true', default=False,
                                  help='Delete existing directory and re-clone from scratch')
        clone_parser.add_argument('--sparse',    action='store_true', default=False,
                                  help='Download only structure (commits + trees); fetch file content on demand')
        clone_parser.add_argument('--read-key',  default=None, metavar='HEX',
                                  help='Clone using a read-only key (hex). Creates a read-only clone that cannot push.')
        clone_parser.add_argument('--bare',      action='store_true', default=False,
                                  help='Clone vault structure only — no working-copy files extracted '
                                       '(full implementation in B09; currently stubs)')
        clone_parser.set_defaults(func=self.vault.cmd_clone)

        init_parser = subparsers.add_parser('init', help='Create a new empty vault and register it on the server')
        init_parser.add_argument('directory',   nargs='?', default='.', help='Directory to create the vault in (default: current directory)')
        init_parser.add_argument('--vault-key', default=None, help='Vault key ({passphrase}:{vault_id}). Generated randomly if omitted.')
        init_parser.add_argument('--existing',  action='store_true', default=False,
                                 help='Allow initialising into a non-empty directory without prompting')
        init_parser.add_argument('--restore',   action='store_true', default=False,
                                 help='Restore vault from a .vault__*.zip backup in the target directory')
        init_parser.set_defaults(func=self.vault.cmd_init)

        # sgit create <vault-name>  — one-shot init + commit + push
        create_parser = subparsers.add_parser('create',
                                               help='Create a new vault and push it to the server in one step')
        create_parser.add_argument('vault_name', help='Vault name / directory to create')
        create_parser.add_argument('--vault-key', dest='vault_key', default=None,
                                   help='Vault key ({passphrase}:{vault_id}). Auto-generated if omitted.')
        create_parser.add_argument('--no-push',  dest='no_push',  action='store_true', default=False,
                                   help='Initialise locally but skip the initial push')
        create_parser.set_defaults(func=self.create.cmd_create)

        # sgit clone-branch <vault-key> <directory>
        cb_parser = subparsers.add_parser('clone-branch',
                                           help='Thin clone: full commit history + HEAD trees/blobs only. '
                                                'Note: only HEAD is fully fetched — run '
                                                "'sgit fetch <path>' or 'sgit pull' to access older history.")
        cb_parser.add_argument('vault_key',  help='Vault key ({passphrase}:{vault_id})')
        cb_parser.add_argument('directory',  nargs='?', default=None,
                               help='Directory to clone into (default: vault ID)')
        cb_parser.add_argument('--bare',     action='store_true', default=False,
                               help='No working-copy extraction (structure only)')
        cb_parser.set_defaults(func=self._cmd_clone_branch)

        # sgit clone-headless <vault-key> [directory]
        ch_parser = subparsers.add_parser('clone-headless',
                                           help='Credentials-only clone: derive keys, write config, no data')
        ch_parser.add_argument('vault_key', help='Vault key ({passphrase}:{vault_id})')
        ch_parser.add_argument('directory', nargs='?', default=None,
                               help='Cache directory (optional)')
        ch_parser.set_defaults(func=self._cmd_clone_headless)

        # sgit clone-range <vault-key> <directory>
        cr_parser = subparsers.add_parser('clone-range',
                                           help='Clone a specific commit range (range_from..range_to)')
        cr_parser.add_argument('vault_key',  help='Vault key ({passphrase}:{vault_id})')
        cr_parser.add_argument('range',      help='Commit range (e.g. abc123..def456)')
        cr_parser.add_argument('directory',  nargs='?', default=None,
                               help='Directory to clone into (default: vault ID)')
        cr_parser.add_argument('--bare',     action='store_true', default=False,
                               help='No working-copy extraction (structure only)')
        cr_parser.set_defaults(func=self._cmd_clone_range)

        commit_parser = subparsers.add_parser('commit', help='Commit local changes to the clone branch')
        commit_parser.add_argument('message', nargs='?', default='', help='Commit message (auto-generated if omitted)')
        commit_parser.add_argument('-d', '--directory', default='.', help='Vault directory (default: .)')
        commit_parser.add_argument('--allow-deletions', action='store_true', default=False,
                                   help='In sparse clones, allow files absent from disk to be deleted '
                                        '(default: preserve unfetched entries)')
        commit_parser.set_defaults(func=self.vault.cmd_commit)

        status_parser = subparsers.add_parser('status', help='Show uncommitted changes in working directory')
        status_parser.add_argument('directory', nargs='?', default='.', help='Vault directory (default: .)')
        status_parser.add_argument('--explain', action='store_true', default=False,
                                   help='Print a longer explanation of the two-branch model')
        status_parser.set_defaults(func=self.vault.cmd_status)

        pull_parser = subparsers.add_parser('pull', help='Pull named branch changes and merge into clone branch')
        pull_parser.add_argument('directory', nargs='?', default='.', help='Vault directory (default: .)')
        pull_parser.set_defaults(func=self.vault.cmd_pull)

        push_parser = subparsers.add_parser('push', help='Push clone branch to the named branch')
        push_parser.add_argument('directory', nargs='?', default='.', help='Vault directory (default: .)')
        push_parser.add_argument('--branch-only', action='store_true',
                                 help='Push clone branch objects and ref without updating named branch')
        push_parser.add_argument('--force', action='store_true', default=False,
                                 help='Overwrite remote ref unconditionally (no CAS check). '
                                      'Use after sgit history reset <commit> to rewind a branch.')
        push_parser.set_defaults(func=self.vault.cmd_push)

        fetch_parser = subparsers.add_parser('fetch', help='Fetch file content on demand (sparse clone)')
        fetch_parser.add_argument('path',      nargs='?', default=None,
                                  help='File or directory path to fetch (default: all)')
        fetch_parser.add_argument('directory', nargs='?', default='.', help='Vault directory (default: .)')
        fetch_parser.add_argument('--all',     action='store_true', default=False,
                                  help='Fetch all unfetched files (convert sparse clone to full)')
        fetch_parser.set_defaults(func=self.vault.cmd_fetch)

        # ------------------------------------------------------------------
        # Namespaces
        # ------------------------------------------------------------------

        # branch  (register() creates the full namespace including switch/checkout/merge-abort)
        self.branch.register(subparsers)

        # vault  (credential store + operational commands + stash + remote + export)
        self._register_vault_ns(subparsers)

        # share  (send / receive / publish)
        self._register_share_ns(subparsers)

        # migrate
        self._register_migrate(subparsers)

        # pki  (already namespaced — unchanged)
        self._register_pki(subparsers)

        # plugins  (history, inspect, file, check, dev — loaded dynamically)
        _plugin_context = {
            'vault'  : self.vault,
            'diff'   : self.diff,
            'dump'   : self.dump,
            'revert' : self.revert,
            'main'   : self,
        }
        for _plugin in self.plugin_loader.load_enabled(_plugin_context):
            _plugin.register_subparsers(subparsers, _plugin_context)

        return parser

    # ------------------------------------------------------------------
    # Namespace registration helpers (vault, share, pki)
    # ------------------------------------------------------------------

    def _register_vault_ns(self, subparsers):
        vault_p   = subparsers.add_parser('vault', help='Vault management and credential store')
        vault_sub = vault_p.add_subparsers(dest='vault_command')
        vault_p.set_defaults(func=lambda a: vault_p.print_help())

        # --- Operational commands ---

        info_p = vault_sub.add_parser('info', help='Show vault identity, remote, branch, and web URL')
        info_p.add_argument('directory', nargs='?', default='.', help='Vault directory (default: .)')
        info_p.add_argument('--token',    default=None, help='Access token')
        info_p.add_argument('--base-url', default=None, help='API base URL')
        info_p.set_defaults(func=self.vault.cmd_info)

        probe_p = vault_sub.add_parser('probe',
                                        help='Identify a simple token as a vault or share (no clone)')
        probe_p.add_argument('token', help='Simple token (word-word-NNNN) or vault:// URL')
        probe_p.add_argument('--json', action='store_true', default=False, help='Output result as JSON')
        probe_p.set_defaults(func=self.vault.cmd_probe)

        dor_p = vault_sub.add_parser('delete-on-remote',
                                      help='Hard-delete this vault from the server, keep local clone intact')
        dor_p.add_argument('directory', nargs='?', default='.', help='Vault directory (default: .)')
        dor_p.add_argument('--yes', action='store_true', default=False, help='Skip confirmation prompt')
        dor_p.add_argument('--json', action='store_true', default=False, help='Output result as JSON')
        dor_p.set_defaults(func=self.vault.cmd_delete_on_remote)

        rekey_p = vault_sub.add_parser('rekey', help='Replace the vault key and re-encrypt all content')
        rekey_p.add_argument('--new-key', default=None, help='New vault key to use (generated if omitted)')
        rekey_p.add_argument('--yes', action='store_true', default=False, help='Skip confirmation prompts')
        rekey_p.add_argument('--json', action='store_true', default=False, help='Output result as JSON')
        rekey_p.set_defaults(func=self.vault.cmd_rekey, directory='.', rekey_subcommand=None)

        rekey_sub = rekey_p.add_subparsers(dest='rekey_subcommand')
        rk_check = rekey_sub.add_parser('check', help='Show vault state without making changes')
        rk_check.add_argument('directory', nargs='?', default='.')
        rk_check.set_defaults(func=self.vault.cmd_rekey_check)

        rk_wipe = rekey_sub.add_parser('wipe',
                                        help='Wipe local encrypted store only (.sg_vault/ removed, files kept)')
        rk_wipe.add_argument('directory', nargs='?', default='.')
        rk_wipe.add_argument('--yes', action='store_true', default=False, help='Skip confirmation prompt')
        rk_wipe.set_defaults(func=self.vault.cmd_rekey_wipe)

        rk_init = rekey_sub.add_parser('init', help='Re-initialise vault with a new key (run after wipe)')
        rk_init.add_argument('directory', nargs='?', default='.')
        rk_init.add_argument('--new-key', default=None, help='Key to use (generated if omitted)')
        rk_init.set_defaults(func=self.vault.cmd_rekey_init)

        rk_commit = rekey_sub.add_parser('commit',
                                          help='Commit all files under the current key (run after init)')
        rk_commit.add_argument('directory', nargs='?', default='.')
        rk_commit.set_defaults(func=self.vault.cmd_rekey_commit)

        uninit_p = vault_sub.add_parser('uninit',
                                         help='Remove vault metadata (.sg_vault/), creating an auto-backup zip first')
        uninit_p.add_argument('directory', nargs='?', default='.', help='Vault directory (default: .)')
        uninit_p.set_defaults(func=self.vault.cmd_uninit)

        clean_p = vault_sub.add_parser('clean',
                                        help='Remove working copy, keeping bare vault; or prune empty dirs')
        clean_p.add_argument('directory',    nargs='?', default='.', help='Vault directory (default: .)')
        clean_p.add_argument('--empty-dirs', action='store_true', default=False,
                             help='Remove empty directories left after file deletions (normal vault)')
        clean_p.set_defaults(func=self.vault.cmd_clean)

        share_p = vault_sub.add_parser('share', help='Share a vault snapshot via a Simple Token')
        share_p.add_argument('directory', nargs='?', default='.', help='Vault directory (default: .)')
        share_p.add_argument('--token', default=None,
                             help='Use a specific token (format: word-word-NNNN). Generated randomly if omitted.')
        share_p.add_argument('--rotate', action='store_true', default=False,
                             help='Generate a new share token (rotates the share URL)')
        share_p.set_defaults(func=self.share.cmd_share)

        # --- Credential store ---

        vault_add = vault_sub.add_parser('add', help='Store a vault key under an alias')
        vault_add.add_argument('alias', help='Human-friendly name for this vault')
        vault_add.add_argument('--vault-key', default=None, help='Vault key (prompted if omitted)')
        vault_add.set_defaults(func=self.vault.cmd_vault_add)

        vault_list = vault_sub.add_parser('list', help='List stored vault aliases')
        vault_list.set_defaults(func=self.vault.cmd_vault_list)

        vault_remove = vault_sub.add_parser('remove', help='Remove a stored vault key')
        vault_remove.add_argument('alias', help='Vault alias to remove')
        vault_remove.set_defaults(func=self.vault.cmd_vault_remove)

        vault_show = vault_sub.add_parser('show', help='Show vault key for an alias')
        vault_show.add_argument('alias', help='Vault alias')
        vault_show.set_defaults(func=self.vault.cmd_vault_show)

        vault_show_key = vault_sub.add_parser('show-key', help='Show the vault key for the current directory')
        vault_show_key.add_argument('directory', nargs='?', default='.', help='Vault directory (default: .)')
        vault_show_key.set_defaults(func=self.vault.cmd_vault_show_key)

        # --- remote (moved from top-level) ---

        remote_p   = vault_sub.add_parser('remote', help='Manage vault remotes')
        remote_sub = remote_p.add_subparsers(dest='remote_command')

        remote_add = remote_sub.add_parser('add', help='Add a remote')
        remote_add.add_argument('name',            help='Remote name (e.g. origin)')
        remote_add.add_argument('url',             help='Remote API URL')
        remote_add.add_argument('remote_vault_id', help='Remote vault ID')
        remote_add.add_argument('--directory', '-d', default='.', help='Vault directory (default: .)')
        remote_add.set_defaults(func=self.vault.cmd_remote_add)

        remote_remove = remote_sub.add_parser('remove', help='Remove a remote')
        remote_remove.add_argument('name',          help='Remote name to remove')
        remote_remove.add_argument('--directory', '-d', default='.', help='Vault directory (default: .)')
        remote_remove.set_defaults(func=self.vault.cmd_remote_remove)

        remote_list = remote_sub.add_parser('list', help='List configured remotes')
        remote_list.add_argument('--directory', '-d', default='.', help='Vault directory (default: .)')
        remote_list.set_defaults(func=self.vault.cmd_remote_list)

        # --- stash (moved from top-level) ---

        stash_p   = vault_sub.add_parser('stash', help='Stash uncommitted changes')
        stash_sub = stash_p.add_subparsers(dest='stash_command')
        stash_p.add_argument('directory', nargs='?', default='.', help='Vault directory (default: .)')
        stash_p.set_defaults(func=self.stash.cmd_stash)

        stash_pop = stash_sub.add_parser('pop', help='Restore last stash')
        stash_pop.add_argument('directory', nargs='?', default='.', help='Vault directory (default: .)')
        stash_pop.set_defaults(func=self.stash.cmd_stash_pop)

        stash_list_p = stash_sub.add_parser('list', help='List stashes')
        stash_list_p.add_argument('directory', nargs='?', default='.', help='Vault directory (default: .)')
        stash_list_p.set_defaults(func=self.stash.cmd_stash_list)

        stash_drop = stash_sub.add_parser('drop', help='Drop last stash without applying')
        stash_drop.add_argument('directory', nargs='?', default='.', help='Vault directory (default: .)')
        stash_drop.set_defaults(func=self.stash.cmd_stash_drop)

        # --- export (moved from top-level) ---

        export_p = vault_sub.add_parser('export', help='Export vault snapshot as a local encrypted zip file')
        export_p.add_argument('directory', nargs='?', default='.', help='Vault directory (default: .)')
        export_p.add_argument('--output', default=None, help='Output filename (auto-generated if omitted)')
        export_p.add_argument('--token', default=None,
                              help='Use a specific token (format: word-word-NNNN). Generated randomly if omitted.')
        export_p.add_argument('--no-inner-encrypt', dest='no_inner_encrypt',
                              action='store_true', default=False,
                              help='Skip inner encryption (inner_key_type=none)')
        export_p.set_defaults(func=self.export.cmd_export)

    def _register_migrate(self, subparsers):
        migrate_p   = subparsers.add_parser('migrate', help='Run vault data migrations')
        migrate_sub = migrate_p.add_subparsers(dest='migrate_command')
        migrate_p.set_defaults(func=lambda a: migrate_p.print_help())

        plan_p = migrate_sub.add_parser('plan', help='Show pending migrations')
        plan_p.add_argument('directory', nargs='?', default='.', help='Vault directory (default: .)')
        plan_p.set_defaults(func=self.migrate.cmd_migrate_plan)

        apply_p = migrate_sub.add_parser('apply', help='Apply pending migrations')
        apply_p.add_argument('directory', nargs='?', default='.', help='Vault directory (default: .)')
        apply_p.set_defaults(func=self.migrate.cmd_migrate_apply)

        status_p = migrate_sub.add_parser('status', help='Show applied migrations')
        status_p.add_argument('directory', nargs='?', default='.', help='Vault directory (default: .)')
        status_p.set_defaults(func=self.migrate.cmd_migrate_status)

    def _register_share_ns(self, subparsers):
        share_p   = subparsers.add_parser('share', help='SG/Send sharing — send, receive, publish')
        share_sub = share_p.add_subparsers(dest='share_command')
        share_p.set_defaults(func=lambda a: share_p.print_help())

        send_p = share_sub.add_parser('send', help='Encrypt and send text or a file via SG/Send')
        send_g = send_p.add_mutually_exclusive_group()
        send_g.add_argument('--text', default=None, metavar='TEXT', help='Text to encrypt and send')
        send_g.add_argument('--file', default=None, metavar='PATH', help='File to encrypt and send')
        send_p.set_defaults(func=self.share.cmd_send)

        receive_p = share_sub.add_parser('receive', help='Download and decrypt a SG/Send transfer')
        receive_p.add_argument('token', help='Simple Token (word-word-NNNN or hex transfer ID)')
        receive_p.add_argument('--output-dir', default=None, metavar='DIR',
                               help='Directory to extract files into (default: current directory)')
        receive_p.set_defaults(func=self.share.cmd_receive)

        publish_p = share_sub.add_parser('publish',
                                          help='Publish vault snapshot as multi-level encrypted zip')
        publish_p.add_argument('directory', nargs='?', default='.', help='Vault directory (default: .)')
        publish_p.add_argument('--token', default=None,
                               help='Use a specific token (format: word-word-NNNN). Generated randomly if omitted.')
        publish_p.add_argument('--no-inner-encrypt', dest='no_inner_encrypt',
                               action='store_true', default=False,
                               help='Skip inner encryption (inner_key_type=none)')
        publish_p.set_defaults(func=self.publish.cmd_publish)

    def _register_pki(self, subparsers):
        pki_p   = subparsers.add_parser('pki', help='PKI key management and encryption')
        pki_sub = pki_p.add_subparsers(dest='pki_command')

        pki_keygen = pki_sub.add_parser('keygen', help='Generate encryption + signing key pair')
        pki_keygen.add_argument('--label', default='', help='Label for the key pair')
        pki_keygen.set_defaults(func=self.pki.cmd_keygen)

        pki_list = pki_sub.add_parser('list', help='List local key pairs')
        pki_list.set_defaults(func=self.pki.cmd_list)

        pki_export = pki_sub.add_parser('export', help='Export public key bundle (JSON)')
        pki_export.add_argument('fingerprint', help='Encryption key fingerprint')
        pki_export.set_defaults(func=self.pki.cmd_export)

        pki_delete = pki_sub.add_parser('delete', help='Delete key pair')
        pki_delete.add_argument('fingerprint', help='Encryption key fingerprint')
        pki_delete.set_defaults(func=self.pki.cmd_delete)

        pki_import = pki_sub.add_parser('import', help='Import contact public key')
        pki_import.add_argument('file', help='Path to public key bundle JSON (or - for stdin)')
        pki_import.set_defaults(func=self.pki.cmd_import_contact)

        pki_contacts = pki_sub.add_parser('contacts', help='List imported contacts')
        pki_contacts.set_defaults(func=self.pki.cmd_contacts)

        pki_sign = pki_sub.add_parser('sign', help='Sign a file (detached signature)')
        pki_sign.add_argument('file', help='File to sign')
        pki_sign.add_argument('--fingerprint', required=True, help='Signing key fingerprint')
        pki_sign.set_defaults(func=self.pki.cmd_sign)

        pki_verify = pki_sub.add_parser('verify', help='Verify a detached signature')
        pki_verify.add_argument('file', help='File to verify')
        pki_verify.add_argument('signature', help='Signature file (.sig)')
        pki_verify.set_defaults(func=self.pki.cmd_verify)

        pki_encrypt = pki_sub.add_parser('encrypt', help='Encrypt a file for a recipient')
        pki_encrypt.add_argument('file', help='File to encrypt')
        pki_encrypt.add_argument('--recipient', required=True, help='Recipient fingerprint')
        pki_encrypt.add_argument('--fingerprint', default=None, help='Your key fingerprint (for signing)')
        pki_encrypt.set_defaults(func=self.pki.cmd_encrypt)

        pki_decrypt = pki_sub.add_parser('decrypt', help='Decrypt a file with local key')
        pki_decrypt.add_argument('file', help='Encrypted file (.enc)')
        pki_decrypt.add_argument('--fingerprint', required=True, help='Your encryption key fingerprint')
        pki_decrypt.set_defaults(func=self.pki.cmd_decrypt)

    # ------------------------------------------------------------------
    # run()
    # ------------------------------------------------------------------

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

        if args.command == 'pki':
            if not getattr(args, 'pki_command', None):
                parser.parse_args([args.command, '--help'])
            self.pki.setup()

        if args.command == 'branch':
            sub = getattr(args, 'branch_command', None)
            if not sub:
                parser.parse_args([args.command, '--help'])

        if args.command == 'migrate':
            sub = getattr(args, 'migrate_command', None)
            if sub == 'plan':
                args.func = self.migrate.cmd_migrate_plan
            elif sub == 'apply':
                args.func = self.migrate.cmd_migrate_apply
            elif sub == 'status':
                args.func = self.migrate.cmd_migrate_status

        self._resolve_vault_dir(args)

        command = getattr(args, 'command', None) or ''
        context = self._detect_context(args)
        if command in self._INSIDE_ONLY and context.is_outside():
            self._cmd_wrong_context(command, context)
        if command in self._OUTSIDE_ONLY and context.is_inside():
            self._cmd_wrong_context(command, context)

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
            self._print_friendly_error(e, args)
            if debug_log:
                raise
            sys.exit(1)
        finally:
            if debug_log:
                debug_log.print_summary()

    _NO_WALK_UP = frozenset({
        'init', 'clone', 'clone-branch', 'clone-headless', 'clone-range', 'create',
        'probe', 'version', 'update', 'vault', 'pki', 'share', 'dev',
        'history', 'file', 'inspect', 'check', 'branch',
    })

    # Commands that are only meaningful outside a vault ('outside' context).
    _OUTSIDE_ONLY = frozenset({
        'init', 'clone', 'clone-branch', 'clone-headless', 'clone-range', 'create',
    })

    # Commands that require being inside a vault.
    _INSIDE_ONLY = frozenset({
        'commit', 'status', 'pull', 'push', 'fetch',
        'history', 'file', 'branch', 'vault', 'check', 'migrate',
    })

    # Universal commands (work in any context).
    _UNIVERSAL = frozenset({
        'version', 'help', 'update', 'pki', 'dev', 'share', 'inspect',
    })

    def _resolve_vault_dir(self, args):
        """Walk up from args.directory to find the nearest vault root when not already at one."""
        command = getattr(args, 'command', '')
        if command in self._NO_WALK_UP:
            return
        directory = getattr(args, 'directory', None)
        if not directory:
            return
        from sgit_ai.storage.Vault__Storage import Vault__Storage, SG_VAULT_DIR
        abs_dir = os.path.abspath(directory)
        if not os.path.isdir(os.path.join(abs_dir, SG_VAULT_DIR)):
            root = Vault__Storage.find_vault_root(abs_dir)
            if root != abs_dir:
                args.directory = root

    def _print_friendly_error(self, error: Exception, args):
        """Print a user-friendly error message instead of a raw traceback."""
        import traceback
        error_type = type(error).__name__
        command    = getattr(args, 'command', 'unknown')
        message    = str(error)

        directory = getattr(args, 'directory', '.')
        if isinstance(error, FileNotFoundError):
            print(f'error: missing file — {message}', file=sys.stderr)
            print(f'  hint: the vault may be corrupted or incomplete', file=sys.stderr)
            print(f'  hint: try "sgit check fsck {directory}" to check and repair', file=sys.stderr)
        elif isinstance(error, PermissionError):
            print(f'error: permission denied — {message}', file=sys.stderr)
        elif isinstance(error, (ConnectionError, OSError)):
            print(f'error: network or I/O failure — {message}', file=sys.stderr)
        elif isinstance(error, ValueError) and 'does not match required pattern' in message:
            lines = message.splitlines()
            print(f'error: incompatible vault data — {lines[0]}', file=sys.stderr)
            for extra in lines[1:]:
                print(f'  {extra.strip()}', file=sys.stderr)
            print(f'  hint: this vault may have been written by the web UI or an older CLI version', file=sys.stderr)
            print(f'  hint: re-clone the vault with the current CLI:', file=sys.stderr)
            print(f'          sgit clone <vault-key> <directory>', file=sys.stderr)
        else:
            print(f'error: {error_type} in "{command}" — {message}', file=sys.stderr)

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
        self.vault.debug_log   = debug_log
        self.share.debug_log   = debug_log
        self.publish.debug_log = debug_log
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
        try:
            os.chmod(debug_path, stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            pass

    def _cmd_log_dispatch(self, args):
        """Kept for backward compat with tests; delegates to history namespace."""
        from sgit_ai.plugins.history.CLI__History import CLI__History
        ns        = CLI__History()
        ns.diff   = self.diff
        ns.vault  = self.vault
        ns.revert = self.revert
        ns._dispatch_log(args)

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

    # ------------------------------------------------------------------
    # Clone-family stubs  (full implementation in brief B09)
    # ------------------------------------------------------------------

    def _cmd_clone_branch(self, args):
        from sgit_ai.core.Vault__Crypto import Vault__Crypto
        from sgit_ai.network.api.Vault__API import Vault__API
        from sgit_ai.core.Vault__Sync import Vault__Sync
        from sgit_ai.crypto.simple_token.Simple_Token import Simple_Token

        vault_key = args.vault_key
        bare      = getattr(args, 'bare', False)
        directory = args.directory
        if not directory:
            token_str = vault_key.removeprefix('vault://')
            if Simple_Token.is_simple_token(token_str):
                directory = token_str
            else:
                parts     = vault_key.split(':')
                directory = parts[-1] if len(parts) == 2 else 'vault'

        sync   = Vault__Sync(crypto=Vault__Crypto(), api=Vault__API())
        mode   = 'Bare branch-cloning' if bare else 'Branch-cloning'
        print(f'{mode} into \'{directory}\'...')
        result = sync.clone_branch(vault_key, directory, bare=bare)
        print(f'Branch clone ready: {result["directory"]}/')
        print(f'  Vault ID: {result["vault_id"]}')
        if result.get('commit_id'):
            print(f'  HEAD:     {result["commit_id"]}')
        if bare:
            print('  Mode:     bare (no working copy)')

    def _cmd_clone_headless(self, args):
        if getattr(args, 'bare', False):
            print('clone-headless: --bare is redundant for headless mode (no working copy is ever created).',
                  file=sys.stderr)
            sys.exit(1)

        from sgit_ai.core.Vault__Crypto import Vault__Crypto
        from sgit_ai.network.api.Vault__API import Vault__API
        from sgit_ai.core.Vault__Sync import Vault__Sync
        from sgit_ai.crypto.simple_token.Simple_Token import Simple_Token

        vault_key = args.vault_key
        directory = args.directory
        if not directory:
            token_str = vault_key.removeprefix('vault://')
            if Simple_Token.is_simple_token(token_str):
                directory = token_str
            else:
                parts     = vault_key.split(':')
                directory = parts[-1] if len(parts) == 2 else 'vault'

        sync   = Vault__Sync(crypto=Vault__Crypto(), api=Vault__API())
        print(f'Headless-cloning credentials into \'{directory}\'...')
        result = sync.clone_headless(vault_key, directory)
        print(f'Headless clone ready: {result["directory"]}/')
        print(f'  Vault ID: {result["vault_id"]}')
        print('  Mode:     headless (credentials only — use sgit fetch <path> to access files)')

    def _cmd_clone_range(self, args):
        from sgit_ai.core.Vault__Crypto import Vault__Crypto
        from sgit_ai.network.api.Vault__API import Vault__API
        from sgit_ai.core.Vault__Sync import Vault__Sync
        from sgit_ai.crypto.simple_token.Simple_Token import Simple_Token

        vault_key  = args.vault_key
        range_spec = getattr(args, 'range', '')
        bare       = getattr(args, 'bare', False)
        directory  = args.directory

        range_from, range_to = '', ''
        if '..' in range_spec:
            parts      = range_spec.split('..', 1)
            range_from = parts[0].strip()
            range_to   = parts[1].strip()
        else:
            range_to = range_spec.strip()

        if not directory:
            token_str = vault_key.removeprefix('vault://')
            if Simple_Token.is_simple_token(token_str):
                directory = token_str
            else:
                parts     = vault_key.split(':')
                directory = parts[-1] if len(parts) == 2 else 'vault'

        sync   = Vault__Sync(crypto=Vault__Crypto(), api=Vault__API())
        mode   = 'Bare range-cloning' if bare else 'Range-cloning'
        print(f'{mode} \'{range_spec}\' into \'{directory}\'...')
        result = sync.clone_range(vault_key, directory, range_from=range_from,
                                  range_to=range_to, bare=bare)
        print(f'Range clone ready: {result["directory"]}/')
        print(f'  Vault ID:   {result["vault_id"]}')
        if result.get('commit_id'):
            print(f'  HEAD:       {result["commit_id"]}')
        if bare:
            print('  Mode:       bare (no working copy)')

    # ------------------------------------------------------------------
    # Context-aware help + wrong-context friendly errors  (B04)
    # ------------------------------------------------------------------

    def _detect_context(self, args):
        """Return Vault__Context for the current invocation."""
        from sgit_ai.core.Vault__Context import Vault__Context
        vault_override = getattr(args, 'vault', None)
        return Vault__Context.detect_with_override(os.getcwd(), vault_override)

    def _cmd_wrong_context(self, command: str, context):
        """Print a friendly error for a wrong-context invocation and exit 1."""
        from sgit_ai.core.Vault__Context import Enum__Vault_Context
        if context.is_outside() and command in self._INSIDE_ONLY:
            print(f"sgit: '{command}' is only available inside a vault.", file=sys.stderr)
            print('You are not inside a vault directory.', file=sys.stderr)
            print('', file=sys.stderr)
            print('Did you mean to:', file=sys.stderr)
            print('  - create one:    sgit init   (or  sgit create)', file=sys.stderr)
            print('  - clone one:     sgit clone <vault-key>', file=sys.stderr)
            print(f'  - operate on one elsewhere:  sgit {command} --vault PATH', file=sys.stderr)
        elif context.is_inside() and command in self._OUTSIDE_ONLY:
            vault_name = str(context.vault_id) if context.vault_id else 'this vault'
            print(f"sgit: '{command}' is only available outside a vault.", file=sys.stderr)
            print(f'You are inside vault: {vault_name}  ({context.vault_path})', file=sys.stderr)
            print('', file=sys.stderr)
            print('Did you mean to:', file=sys.stderr)
            print('  - clone into a different directory:  cd .. && sgit clone <key>', file=sys.stderr)
            print('  - operate on the current vault:      sgit pull   /  sgit status', file=sys.stderr)
        else:
            print(f"sgit: '{command}' is not available in this context.", file=sys.stderr)
        sys.exit(1)

    def _cmd_help(self, args, parser):
        """sgit help [command|all]"""
        topic = getattr(args, 'topic', None)
        if topic == 'all':
            print('sgit-ai — full command surface:', file=sys.stdout)
            print('', file=sys.stdout)
            print('  Outside a vault:', file=sys.stdout)
            for cmd in sorted(self._OUTSIDE_ONLY):
                print(f'    {cmd}', file=sys.stdout)
            print('', file=sys.stdout)
            print('  Inside a vault:', file=sys.stdout)
            for cmd in sorted(self._INSIDE_ONLY):
                print(f'    {cmd}', file=sys.stdout)
            print('', file=sys.stdout)
            print('  Universal (any context):', file=sys.stdout)
            for cmd in sorted(self._UNIVERSAL):
                print(f'    {cmd}', file=sys.stdout)
        else:
            parser.print_help()
