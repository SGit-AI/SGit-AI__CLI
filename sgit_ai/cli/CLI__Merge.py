import os

from osbot_utils.type_safe.Type_Safe         import Type_Safe
from sgit_ai.crypto.Vault__Crypto            import Vault__Crypto
from sgit_ai.network.api.Vault__API          import Vault__API


class CLI__Merge(Type_Safe):
    crypto : Vault__Crypto
    api    : Vault__API

    def cmd_merge_abort(self, args) -> None:
        from sgit_ai.core.actions.merge.Vault__Merge__Abort import Vault__Merge__Abort
        directory         = os.path.abspath(getattr(args, 'directory', None) or '.')
        keep_conflict     = getattr(args, 'keep_conflict_files', False)
        result = Vault__Merge__Abort(crypto=self.crypto, api=self.api).abort(
            directory, keep_conflict_files=keep_conflict
        )
        print(f"Merge aborted. Working tree restored to {result['restored_to']}")

    def cmd_resolve(self, args) -> None:
        from sgit_ai.core.actions.merge.Vault__Merge__Resolve import Vault__Merge__Resolve
        directory = os.path.abspath(getattr(args, 'directory', None) or '.')
        resolver  = Vault__Merge__Resolve()

        show      = getattr(args, 'show', False)
        all_flag  = getattr(args, 'all', False)
        ours      = getattr(args, 'ours', False)
        theirs    = getattr(args, 'theirs', False)
        file_path = getattr(args, 'file', None)

        strategy = 'ours' if ours else ('theirs' if theirs else None)

        if show:
            resolver.show(directory)
            return

        if not strategy:
            print('error: specify --ours or --theirs')
            return

        if all_flag:
            resolver.resolve_all(directory, strategy)
        elif file_path:
            resolver.resolve_file(directory, file_path, strategy)
        else:
            print('error: specify a <file> or --all')

    def register(self, subparsers) -> None:
        abort_p = subparsers.add_parser('merge-abort',
                                        help='Abort an in-progress merge and restore working tree')
        abort_p.add_argument('directory', nargs='?', default='.',
                             help='Vault directory (default: current)')
        abort_p.add_argument('--keep-conflict-files', action='store_true',
                             help='Leave .conflict files in place (debug only)')
        abort_p.set_defaults(func=self.cmd_merge_abort)

        resolve_p = subparsers.add_parser('resolve',
                                          help='Resolve merge conflicts per file or all at once')
        resolve_p.add_argument('file', nargs='?', default=None,
                               help='Relative path of the conflicted file')
        resolve_p.add_argument('--ours',   action='store_true', help='Keep local version')
        resolve_p.add_argument('--theirs', action='store_true', help='Take remote version')
        resolve_p.add_argument('--all',    action='store_true', help='Resolve all conflicts')
        resolve_p.add_argument('--show',   action='store_true', help='List unresolved conflicts')
        resolve_p.add_argument('--directory', default='.', help='Vault directory')
        resolve_p.set_defaults(func=self.cmd_resolve)
