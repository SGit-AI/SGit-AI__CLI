"""CLI__History — `sgit history <…>` namespace (log, diff, show, revert, reset)."""
import argparse

from osbot_utils.type_safe.Type_Safe import Type_Safe


class CLI__History(Type_Safe):
    vault  : object = None   # CLI__Vault instance (injected by CLI__Main)
    diff   : object = None   # CLI__Diff  instance
    revert : object = None   # CLI__Revert instance

    def _dispatch_log(self, args):
        if getattr(args, 'file_path', None):
            self.diff.cmd_log_file(args)
        else:
            self.vault.cmd_log(args)

    def register(self, subparsers: argparse._SubParsersAction):
        hist_p   = subparsers.add_parser('history', help='Commit history and diffs')
        hist_sub = hist_p.add_subparsers(dest='history_command')
        hist_p.set_defaults(func=lambda a: hist_p.print_help())

        # history log
        log_p = hist_sub.add_parser('log', help='Show commit history')
        log_p.add_argument('--vault-key', default=None,
                           help='Vault key (auto-read from .sg_vault/local/vault_key if omitted)')
        log_p.add_argument('--oneline', action='store_true', help='Compact one-line-per-commit format')
        log_p.add_argument('--graph',   action='store_true', help='Show graph with connectors')
        log_p.add_argument('--file', dest='file_path', default=None, metavar='PATH',
                           help='Show only commits that touched this file')
        log_p.add_argument('directory', nargs='?', default='.', help='Vault directory (default: .)')
        log_p.set_defaults(func=self._dispatch_log)

        # history diff
        diff_p = hist_sub.add_parser('diff', help='Show file-level and content-level diff')
        diff_p.add_argument('directory',    nargs='?', default='.', help='Vault directory (default: .)')
        diff_p.add_argument('--remote',     action='store_true', default=False,
                            help='Compare working copy vs named branch HEAD')
        diff_p.add_argument('--commit',     default=None, metavar='COMMIT_ID',
                            help='Compare working copy vs specific commit')
        diff_p.add_argument('--commit2',    default=None, metavar='COMMIT_ID',
                            help='Second commit for commit-to-commit diff (requires --commit)')
        diff_p.add_argument('--files-only', action='store_true', default=False,
                            help='Show file names only (no inline diff)')
        diff_p.set_defaults(func=self.diff.cmd_diff)

        # history show
        show_p = hist_sub.add_parser('show', help='Show changes introduced by a commit')
        show_p.add_argument('commit_id',    help='Commit ID to inspect')
        show_p.add_argument('directory',    nargs='?', default='.', help='Vault directory (default: .)')
        show_p.add_argument('--files-only', action='store_true', default=False,
                            help='Show file names only (no inline diff)')
        show_p.set_defaults(func=self.diff.cmd_show)

        # history revert
        rev_p = hist_sub.add_parser('revert', help='Restore working copy files to a past commit')
        rev_p.add_argument('directory', nargs='?', default='.', help='Vault directory (default: .)')
        rev_p.add_argument('files',     nargs='*', default=[],  help='Specific files to revert (default: all)')
        rev_p.add_argument('--commit',  default=None, metavar='COMMIT_ID',
                           help='Revert to a specific commit (default: HEAD)')
        rev_p.add_argument('--force',   action='store_true', default=False,
                           help='Skip confirmation prompt when reverting all files')
        rev_p.set_defaults(func=self.revert.cmd_revert)

        # history reset
        reset_p = hist_sub.add_parser('reset',
                                       help='Reset local branch HEAD to a specific commit (git reset --hard)')
        reset_p.add_argument('commit_id', nargs='?', default=None,
                             help='Target commit ID (full or prefix); omit to discard working-copy changes')
        reset_p.add_argument('directory',  nargs='?', default='.', help='Vault directory (default: .)')
        reset_p.set_defaults(func=self.vault.cmd_reset)

        return hist_p
