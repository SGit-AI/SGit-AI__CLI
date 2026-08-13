import os

from osbot_utils.type_safe.Type_Safe         import Type_Safe
from sgit_ai.crypto.Vault__Crypto            import Vault__Crypto
from sgit_ai.network.api.Vault__API          import Vault__API


class CLI__Merge(Type_Safe):
    crypto : Vault__Crypto
    api    : Vault__API
    vault  : object = None   # CLI__Vault instance (injected by CLI__Main) for read-only gating

    def _check_read_only(self, directory: str) -> None:
        if self.vault is not None:
            self.vault._check_read_only(directory)

    def cmd_merge_abort(self, args) -> None:
        from sgit_ai.core.actions.merge.Vault__Merge__Abort import Vault__Merge__Abort
        directory         = os.path.abspath(getattr(args, 'directory', None) or '.')
        self._check_read_only(directory)
        keep_conflict     = getattr(args, 'keep_conflict_files', False)
        result = Vault__Merge__Abort(crypto=self.crypto, api=self.api).abort(
            directory, keep_conflict_files=keep_conflict
        )
        print(f"Merge aborted. Working tree restored to {result['restored_to']}")

    def cmd_resolve(self, args) -> None:
        from sgit_ai.core.actions.merge.Vault__Merge__Resolve import Vault__Merge__Resolve
        directory = os.path.abspath(getattr(args, 'directory', None) or '.')
        self._check_read_only(directory)
        resolver  = Vault__Merge__Resolve()

        show      = getattr(args, 'show', False)
        all_flag  = getattr(args, 'all', False)
        ours      = getattr(args, 'ours', False)
        theirs    = getattr(args, 'theirs', False)
        file_path = getattr(args, 'file', None)

        strategy = 'ours' if ours else ('theirs' if theirs else None)

        if show:
            self._show_conflicts(directory, resolver)
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

    _VERDICT_LABELS = {
        'genuine'          : 'GENUINE — both sides changed vs base; choose --ours or --theirs',
        'identical'        : 'IDENTICAL — both sides made the SAME change; safe to take either',
        'one-sided-ours'   : 'ONE-SIDED (ours) — only your side changed; SUSPECT: stale merge base?',
        'one-sided-theirs' : 'ONE-SIDED (theirs) — only their side changed; SUSPECT: stale merge base?',
        'no-change'        : 'NO-CHANGE — neither side changed vs base; SUSPECT: stale merge base',
    }

    def _show_conflicts(self, directory: str, resolver) -> None:
        """`resolve --show`: render a 3-way (base/ours/theirs) verdict per conflict.

        Falls back to the plain path list when the merge base or objects can't be
        read (e.g. sparse clone), so --show never hard-fails.
        """
        from sgit_ai.core.actions.merge.Vault__Merge__State import Vault__Merge__State
        state = Vault__Merge__State().read(directory)
        if state is None:
            raise RuntimeError('No merge in progress.')
        conflict_paths = [str(p) for p in (state.conflict_paths or [])]
        resolved_paths = [str(p) for p in (state.resolved_paths or [])]
        if not conflict_paths:
            resolver.show(directory)
            return
        try:
            from sgit_ai.core.actions.diff.Vault__Diff import Vault__Diff
            rows = Vault__Diff(crypto=self.crypto).three_way_conflict_view(
                directory,
                str(state.lca_id or ''),
                str(state.ours_commit_id or ''),
                str(state.theirs_commit_id or ''),
                conflict_paths)
        except Exception as exc:
            print(f'(3-way view unavailable — {exc}; showing paths only)\n')
            resolver.show(directory)
            return
        self._print_conflict_rows(rows, resolved_paths)

    def _print_conflict_rows(self, rows: list, resolved_paths: list) -> None:
        import difflib
        genuine = sum(1 for r in rows if r['verdict'] == 'genuine')
        suspect = len(rows) - genuine
        print(f'Unresolved conflicts ({len(rows)}):\n')
        for r in rows:
            label = self._VERDICT_LABELS.get(r['verdict'], r['verdict'])
            print(f"  {r['path']}")
            print(f'      [{label}]')
            if r['is_binary']:
                print('      (binary file — no inline diff)\n')
                continue
            ours   = (r['ours_text']   or '').splitlines()
            theirs = (r['theirs_text'] or '').splitlines()
            diff = list(difflib.unified_diff(ours, theirs, fromfile='ours',
                                             tofile='theirs', lineterm=''))
            if diff:
                for line in diff:
                    print(f'      {line}')
            else:
                print('      (ours and theirs are identical)')
            print()
        if resolved_paths:
            print(f'Resolved ({len(resolved_paths)}):')
            for p in resolved_paths:
                print(f'  {p}')
        print(f'Verdict: {genuine} genuine, {suspect} suspect '
              '(one-sided / identical / no-change).')
        if suspect:
            print('  Suspect conflicts usually mean a stale merge base — the engine '
                  'auto-merges one-sided\n  changes, so these should not normally conflict. '
                  'Inspect before resolving.')

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
