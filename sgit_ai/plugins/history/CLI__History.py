"""CLI__History — `sgit history <…>` namespace (log, diff, show, revert, reset)."""
import argparse
import os

from osbot_utils.type_safe.Type_Safe import Type_Safe


def _is_range_spec(arg: str) -> bool:
    """True if arg looks like a commit range (contains '..' but no '/')."""
    return bool(arg and '..' in arg and '/' not in arg)


class CLI__History(Type_Safe):
    vault  : object = None   # CLI__Vault instance (injected by CLI__Main)
    diff   : object = None   # CLI__Diff  instance
    revert : object = None   # CLI__Revert instance

    def _dispatch_log(self, args):
        range_spec    = getattr(args, 'range_spec', '') or ''
        # --files / --patch / --json need per-commit file deltas, which only the
        # range machinery computes. With no explicit range they mean "full history".
        # --graph is rendered only by the plain inspector log — it wins over details
        # (the previous behaviour silently dropped the graph in details mode).
        wants_details = (getattr(args, 'files',    False)
                         or getattr(args, 'patch',    False)
                         or getattr(args, 'json_out', False))
        if getattr(args, 'graph', False):
            wants_details = False                          # graph beats details (F2)
        filtering = any(getattr(args, k, None) for k in ('grep', 'since', 'until', 'author'))
        if filtering and (_is_range_spec(range_spec) or wants_details or getattr(args, 'file_path', None)):
            import sys                                     # never silently ignore a filter (review S5)
            print('error: --grep/--since/--until/--author work with the plain log only, not with a range, '
                  '--files, --patch, --json or --file', file=sys.stderr)
            sys.exit(1)
        if _is_range_spec(range_spec):
            args.directory = getattr(args, 'directory', '.') or '.'
            self.diff.cmd_log_range(args)
        elif range_spec and not os.path.isdir(range_spec):
            # A revision, not a folder: `history log HEAD~1` printed "(no commits)" (it looked
            # for a vault in a folder named HEAD~1). The history up to that revision.
            if filtering:
                import sys
                print('error: --grep/--since/--until/--author work with the plain log only, not with a revision',
                      file=sys.stderr)
                sys.exit(1)
            args.directory  = getattr(args, 'directory', '.') or '.'
            args.range_spec = f'..{range_spec}'
            if not getattr(args, 'graph', False) and not wants_details:
                args.oneline = True
            self.diff.cmd_log_range(args)
        elif range_spec:
            # Positional was a plain directory path, not a range
            if not getattr(args, 'directory', None) or args.directory == '.':
                args.directory = range_spec
            args.range_spec = ''
            if getattr(args, 'file_path', None):
                self.diff.cmd_log_file(args)
            elif wants_details:
                self.diff.cmd_log_range(args)        # full history with --files/--patch/--json
            else:
                self.vault.cmd_log(args)
        elif getattr(args, 'file_path', None):
            self.diff.cmd_log_file(args)
        elif wants_details:
            args.range_spec = ''                     # full history with --files/--patch/--json
            self.diff.cmd_log_range(args)
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
        log_p.add_argument('-n', '--max-count', dest='limit', type=int, default=None,
                           metavar='N', help='Limit output to the last N commits')
        log_p.add_argument('--file', dest='file_path', default=None, metavar='PATH',
                           help='Show only commits that touched this file')
        log_p.add_argument('--files',  action='store_true', default=False,
                           help='Include files changed per commit (range mode)')
        log_p.add_argument('--patch',  action='store_true', default=False,
                           help='Include full diff per commit (range mode)')
        log_p.add_argument('--json',   dest='json_out', action='store_true', default=False,
                           help='Structured JSON output for agents (range mode)')
        log_p.add_argument('--grep',   default=None, metavar='REGEX',
                           help='Only commits whose message matches (case-insensitive regular expression)')
        log_p.add_argument('--since',  default=None, metavar='WHEN',
                           help='Only commits at or after WHEN (2026-10-08, 2026-10-08T14:30, 3d, 12h, "2 weeks ago")')
        log_p.add_argument('--until',  default=None, metavar='WHEN', help='Only commits before WHEN (same forms)')
        log_p.add_argument('--author', default=None, metavar='WHO',
                           help="Only commits by WHO: part of a signing key id, branch id or branch name")
        log_p.add_argument('--stat',   action='store_true', default=False,
                           help='List the files each commit added (A), modified (M), deleted (D) or renamed (R)')
        log_p.add_argument('range_spec', nargs='?', default='', metavar='[<from>..<to>]',
                           help='Commit range (e.g. abc..def); omit for full history')
        log_p.add_argument('directory', nargs='?', default='.', help='Vault directory (default: .)')
        log_p.set_defaults(func=self._dispatch_log)

        # history reflog
        reflog_p = hist_sub.add_parser('reflog', help="Where this clone's head has pointed (local, newest first)")
        reflog_p.add_argument('--all', dest='all_refs', action='store_true', help='Every local ref, not just this clone\'s head')
        reflog_p.add_argument('-n', '--max-count', dest='limit', type=int, default=20, metavar='N',
                              help='Show the last N moves (default 20, 0 = all)')
        reflog_p.add_argument('directory', nargs='?', default='.', help='Vault directory (default: .)')
        reflog_p.set_defaults(func=lambda a: self.vault.cmd_reflog(a))

        # history diff
        diff_p = hist_sub.add_parser('diff', help='Show file-level and content-level diff')
        diff_p.add_argument('range_spec', nargs='?', default='', metavar='[<from>..<to>]',
                            help='Commit range (e.g. abc..def); synonym for --commit A --commit2 B')
        diff_p.add_argument('directory',    nargs='?', default='.', help='Vault directory (default: .)')
        diff_p.add_argument('--remote',     action='store_true', default=False,
                            help='Compare working copy vs named branch HEAD')
        diff_p.add_argument('--commit',     default=None, metavar='COMMIT_ID',
                            help='Compare working copy vs specific commit')
        diff_p.add_argument('--commit2',    default=None, metavar='COMMIT_ID',
                            help='Second commit for commit-to-commit diff (requires --commit)')
        diff_p.add_argument('--files-only', action='store_true', default=False,
                            help='Show file names only (no inline diff)')
        diff_p.add_argument('--json',       dest='json_out', action='store_true', default=False,
                            help='Structured JSON output for agents')
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
        rev_p.add_argument('--as-commit', dest='as_commit', action='store_true', default=False,
                           help='Make a NEW commit that inverts --commit (git revert); push it to undo a pushed change for everyone')
        rev_p.add_argument('-m', '--message', default='', help='Message for --as-commit (default: Revert "<original>")')
        rev_p.set_defaults(func=self.revert.cmd_revert)

        # history undo
        undo_p = hist_sub.add_parser('undo', help="Move this clone's head back to where it was before its last move (local)")
        undo_p.add_argument('directory', nargs='?', default='.', help='Vault directory (default: .)')
        undo_p.add_argument('--force', action='store_true', default=False,
                            help='Undo even when the head is already on the server (this clone only)')
        undo_p.set_defaults(func=lambda a: self.vault.cmd_undo(a))

        # history reset
        reset_p = hist_sub.add_parser('reset',
                                       help='Reset local branch HEAD to a specific commit (git reset --hard)')
        reset_p.add_argument('commit_id', nargs='?', default=None,
                             help='Target commit ID (full or prefix); omit to discard working-copy changes')
        reset_p.add_argument('directory',  nargs='?', default='.', help='Vault directory (default: .)')
        reset_p.set_defaults(func=self.vault.cmd_reset)

        return hist_p
