"""CLI__File — `sgit file <…>` namespace (cat, ls, write)."""
import argparse

from osbot_utils.type_safe.Type_Safe import Type_Safe


class CLI__File(Type_Safe):
    vault : object = None   # CLI__Vault instance (injected by CLI__Main)

    def register(self, subparsers: argparse._SubParsersAction):
        file_p   = subparsers.add_parser('file', help='File operations (cat, ls, write)')
        file_sub = file_p.add_subparsers(dest='file_command')
        file_p.set_defaults(func=lambda a: file_p.print_help())

        # file cat
        cat_p = file_sub.add_parser('cat', help='Decrypt and print a vault file to stdout')
        cat_p.add_argument('path',      help='File path inside the vault')
        cat_p.add_argument('directory', nargs='?', default='.', help='Vault directory (default: .)')
        cat_p.add_argument('--id',   action='store_true', default=False,
                           help='Print only the blob ID (zero network calls)')
        cat_p.add_argument('--json', action='store_true', default=False,
                           help='Print file metadata as JSON (path, blob_id, size, content_type, fetched)')
        cat_p.set_defaults(func=self.vault.cmd_cat)

        # file ls
        ls_p = file_sub.add_parser('ls', help='List vault files with fetch status')
        ls_p.add_argument('path',      nargs='?', default=None, help='Subdirectory or file path (default: root)')
        ls_p.add_argument('directory', nargs='?', default='.', help='Vault directory (default: .)')
        ls_p.add_argument('--ids',  action='store_true', default=False,
                          help='Include blob IDs in output')
        ls_p.add_argument('--json', action='store_true', default=False,
                          help='Output full entry metadata as JSON array')
        ls_p.set_defaults(func=self.vault.cmd_ls)

        # file write
        write_p = file_sub.add_parser('write',
                                       help='Write a file directly to vault HEAD (agent/programmatic workflow)')
        write_p.add_argument('path',      help='Vault-relative file path to write')
        write_p.add_argument('directory', nargs='?', default='.', help='Vault directory (default: .)')
        write_p.add_argument('--file',    default=None, metavar='LOCAL_FILE',
                             help='Read content from LOCAL_FILE instead of stdin')
        write_p.add_argument('--message', default='', metavar='MSG',
                             help='Commit message (auto-generated if omitted)')
        write_p.add_argument('--also',    action='append', default=[], metavar='VAULT_PATH:LOCAL_FILE',
                             help='Additional files to include atomically (repeatable)')
        write_p.add_argument('--push',    action='store_true', default=False,
                             help='Push immediately after writing; stdout contains only the blob ID')
        write_p.add_argument('--json',    action='store_true', default=False,
                             help='Print result as JSON instead of plain text')
        write_p.set_defaults(func=self.vault.cmd_write)

        return file_p
